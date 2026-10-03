import asyncio
import time
from contextlib import contextmanager
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import OfferEvent
from app.schemas import RuntimeSettings
from app.services.discovery import query_plan, evaluate, diverse_order
from app.services.settings_store import save_runtime_settings
from app.services import radar


def node(item='1', shop='10', name='Fone bluetooth sem fio', **kwargs):
    return dict(shopId=shop, itemId=item, productName=name, priceMin=75,
                priceDiscountRate=30, ratingStar=4.8, sales=900, commissionRate=.12, **kwargs)


def test_plan_is_bounded_rotates_and_respects_disabled():
    assert query_plan('casa, casa, fone', False) == [('casa','casa'),('fone','fone')]
    assert query_plan('casa', True, 0) != query_plan('casa', True, 1)
    assert len(query_plan(','.join('termo'+str(i) for i in range(100)))) == 24


def test_relevance_quality_expiry_and_invalid_data():
    config=RuntimeSettings()
    assert evaluate(node(), 'fone bluetooth', config, time.time())[0] > 0
    assert evaluate(node(), 'eletrônicos', config, time.time())[0] > 0
    assert evaluate(node(), 'panela', config, time.time())[1]
    assert evaluate(node(periodEndTime=1), 'fone', config, time.time())[1]
    bad=node();bad['ratingStar']=None
    assert 'ausentes' in evaluate(bad,'fone',config,time.time())[1]
    bad=node();bad['priceMin']='NaN'
    assert 'inválidos' in evaluate(bad,'fone',config,time.time())[1]
    bad=node();bad['ratingStar']=3
    assert 'avaliação' in evaluate(bad,'fone',config,time.time())[1]


def test_round_robin_and_shop_cap():
    candidates=[dict(identity=(shop,str(i)),topic=topic,rank=rank) for i,(shop,topic,rank) in enumerate([
        ('a','fone',99),('a','fone',98),('b','fone',97),('c','panela',80)])]
    result=list(diverse_order(candidates,1))
    assert [c['topic'] for c in result][:2] == ['fone','panela']
    assert len(result)==3


@pytest.fixture
def db():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        save_runtime_settings(db,RuntimeSettings(radar_keywords='fone',radar_pages=2,max_products_per_keyword=2,discovery_max_candidates=2))
        yield db
    engine.dispose()


def configure(monkeypatch, search):
    class Client:
        configured=True
        search_products=staticmethod(search)
    @contextmanager
    def lock(*a,**kw):yield True
    monkeypatch.setattr(radar,'ShopeeAffiliateClient',Client)
    monkeypatch.setattr(radar,'distributed_lock',lock)


def test_radar_deduplicates_and_reports_new_only(db,monkeypatch):
    async def search(*a,page,**kw):return [node(),node('2','11')] if page==1 else [node()]
    configure(monkeypatch,search)
    first=asyncio.run(radar.run_shopee_radar(db))
    assert first['created']==2 and first['unique']==2 and first['duplicates']==1
    second=asyncio.run(radar.run_shopee_radar(db))
    assert second['created']==0
    assert db.query(OfferEvent).filter_by(status='queued').count()==2


def test_radar_partial_failure_keeps_success(db,monkeypatch):
    save_runtime_settings(db,RuntimeSettings(radar_keywords='fone,panela',radar_pages=1))
    async def search(keyword,**kw):
        if keyword=='panela':raise RuntimeError('private upstream error')
        return [node()]
    configure(monkeypatch,search)
    result=asyncio.run(radar.run_shopee_radar(db))
    assert not result['ok'] and result['created']==1
    assert 'private upstream' not in str(result)


def test_radar_rejects_before_ingestion(db,monkeypatch):
    async def search(*a,**kw):return [node(name='Panela de pressão')]
    configure(monkeypatch,search)
    result=asyncio.run(radar.run_shopee_radar(db))
    assert result['created']==0 and result['rejections']
    assert db.query(OfferEvent).count()==0
