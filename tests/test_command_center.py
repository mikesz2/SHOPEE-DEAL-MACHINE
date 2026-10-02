"""API contracts exercised by V6; no calls to external integrations."""
from datetime import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.db import Base, get_db
from app.main import app
from app.config import settings
from app.models import Product, OfferEvent, Conversion

@pytest.fixture
def client(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    def override():
        with factory() as session:
            yield session
    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(settings, 'app_require_auth', False)
    # Do not run production lifespan or background workers.
    client = TestClient(app)
    yield client, factory
    app.dependency_overrides.clear()
    engine.dispose()

def test_dashboard_empty_and_queue_contract(client):
    c, factory = client
    r = c.get('/api/dashboard?days=7')
    assert r.status_code == 200
    data = r.json()
    assert len(data['daily']) == 7
    assert data['kpis']['queue'] == data['kpis']['commission'] == 0
    with factory() as db:
        p = Product(shop_id='test', item_id='test', name='Oferta V6', price=45.5)
        db.add(p); db.flush()
        db.add(OfferEvent(product_id=p.id, source_type='manual', status='queued', final_score=89))
        db.commit()
    data = c.get('/api/offers?status=queued&limit=60').json()
    assert data['total'] == 1
    assert data['items'][0]['product']['price'] == 45.5
    assert data['items'][0]['score'] == 89
    assert c.get('/api/dashboard').json()['kpis']['queue'] == 1

def test_pause_preserves_policies_and_audits(client):
    c, _ = client
    policies = c.get('/api/settings').json()
    policies.update(auto_publish=False, min_score=84, post_interval_minutes=40)
    assert c.put('/api/settings', json=policies).status_code == 200
    saved = c.get('/api/settings').json()
    assert saved['auto_publish'] is False
    assert saved['min_score'] == 84
    assert saved['post_interval_minutes'] == 40
    saved['auto_publish'] = True
    assert c.put('/api/settings', json=saved).json()['auto_publish'] is True
    assert c.get('/api/settings').json()['min_score'] == 84
    assert c.get('/api/activity').json()[0]['type'] == 'settings.updated'

def test_conversion_period_and_auth(client, monkeypatch):
    c, factory = client
    with factory() as db:
        now = int(datetime.utcnow().timestamp())
        db.add_all([Conversion(conversion_id='recent', purchase_time=now, total_commission=20),
                    Conversion(conversion_id='older', purchase_time=now-20*86400, total_commission=30)])
        db.commit()
    assert c.get('/api/conversions/summary?days=7').json()['commission'] == 20
    assert c.get('/api/conversions/summary?days=30').json()['commission'] == 50
    monkeypatch.setattr(settings, 'app_require_auth', True)
    assert c.get('/api/dashboard').status_code == 401
    assert c.put('/api/settings', json={}).status_code == 401
