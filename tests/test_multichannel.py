import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.config import settings
from app.models import Product, OfferEvent, Publication, PriceSnapshot, Source, RadarInbox
from app.schemas import RuntimeSettings
from app.services.settings_store import save_runtime_settings, load_runtime_settings
from app.services.ingest import ingest_node, _trend_metrics
from app.services.quality import price_evidence
from app.services.collector import enqueue_message, drain_once
from app.services import publisher as pubmod
from app.services.whatsapp import WhatsAppPublisher, DeliveryUncertain
from app.services.message_builder import build_offer_caption

@pytest.fixture
def db():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as db:
        yield db
    engine.dispose()


def product(db):
    p=Product(shop_id='1',item_id='2',name='Fone original',price=80,rating=4.9,sales=8000,
              discount_rate=40,commission_rate=15,commission=12,product_url='https://shopee.com.br/product/1/2')
    db.add(p);db.commit();return p


def event(db):
    p=product(db)
    e=OfferEvent(product_id=p.id,source_type='manual',status='queued',final_score=90,source_weight_snapshot=1)
    db.add(e);db.commit();return e,p


def test_default_paused_whatsapp_off():
    s=RuntimeSettings()
    assert not s.auto_publish and not s.whatsapp_enabled
    assert s.require_quality_data


def test_trend_distinct_source_no_repeated_boost(db):
    p=product(db)
    db.add_all([OfferEvent(product_id=p.id,source_type='telegram',source_ref='group1') for _ in range(10)])
    db.add(OfferEvent(product_id=p.id,source_type='shopee_radar',source_ref='keyword'))
    db.commit()
    assert _trend_metrics(db,p.id,'group1') == (1,1,1,1)
    assert _trend_metrics(db,p.id,'group2') == (2,2,2,2)


def test_price_reference_needs_three_distinct_days(db):
    p=product(db)
    db.add_all([PriceSnapshot(product_id=p.id,price=100,captured_at=datetime.utcnow()-timedelta(days=1)) for _ in range(8)])
    db.commit()
    assert price_evidence(db,p)['reference'] is None
    for day in [2,3]:
        db.add(PriceSnapshot(product_id=p.id,price=100,captured_at=datetime.utcnow()-timedelta(days=day)))
    db.commit()
    q=price_evidence(db,p)
    assert q['reference']==100 and q['drop_pct']==20 and q['score_adjustment']>0
    p.price=150
    assert price_evidence(db,p)['score_adjustment']<0


def test_ingest_same_message_is_idempotent_and_one_active_offer(db):
    node={'shopId':'1','itemId':'2','productName':'Fone','priceMin':80,'priceDiscountRate':40,
          'ratingStar':4.9,'sales':8000,'commissionRate':0.15,'productLink':'https://shopee.com.br/product/1/2'}
    e=asyncio.run(ingest_node(db,node,'telegram','group','1'))
    same=asyncio.run(ingest_node(db,node,'telegram','group','1'))
    second=asyncio.run(ingest_node(db,node,'telegram','group','2'))
    assert e.id==same.id
    assert second.status=='duplicate'
    assert db.query(OfferEvent).filter_by(status='queued').count()==1
    assert db.query(PriceSnapshot).count()==2


def test_inbox_survives_duplicate_and_preserves_two_urls(db, monkeypatch):
    src=Source(name='group',chat_ref='group');db.add(src);db.commit()
    urls=['https://shopee.com.br/product/1/2','https://shopee.com.br/product/1/3']
    assert enqueue_message(db,src,1,urls)==2
    assert enqueue_message(db,src,1,urls)==0
    seen=[]
    async def fake_ingest(db,url,*args,**kwargs): seen.append(url)
    monkeypatch.setattr('app.services.collector.ingest_url',fake_ingest)
    assert asyncio.run(drain_once(db))==2
    assert set(seen)==set(urls)
    assert db.query(RadarInbox).filter_by(status='done').count()==2


def test_inbox_retry_and_paused_source(db, monkeypatch):
    src=Source(name='group',chat_ref='group');db.add(src);db.commit()
    enqueue_message(db,src,1,['https://shopee.com.br/product/1/2'])
    async def failure(*args,**kwargs): raise RuntimeError('offline')
    monkeypatch.setattr('app.services.collector.ingest_url',failure)
    asyncio.run(drain_once(db));row=db.query(RadarInbox).one()
    assert row.status=='pending' and row.attempts==1 and row.next_retry_at>datetime.utcnow()
    row.next_retry_at=None;src.active=False;db.commit()
    asyncio.run(drain_once(db));assert row.status=='skipped'


def setup_dispatch(db,monkeypatch):
    e,p=event(db)
    runtime=RuntimeSettings(telegram_publish_enabled=False,whatsapp_enabled=True,
        whatsapp_groups=['1@g.us','2@g.us'],min_score=0)
    save_runtime_settings(db,runtime)
    async def revalidate(db,event):return p,p.price
    async def short(*args):return 'https://s.shopee.com.br/myaffiliate'
    async def sleep(*args):pass
    monkeypatch.setattr(pubmod,'_revalidate',revalidate)
    monkeypatch.setattr(pubmod.ShopeeAffiliateClient,'generate_short_link',short)
    monkeypatch.setattr(pubmod.asyncio,'sleep',sleep)
    return e,p


def test_partial_delivery_retry_skips_already_sent_group(db,monkeypatch):
    e,p=setup_dispatch(db,monkeypatch)
    seen=[];checks=[]
    async def state(self):
        checks.append(1)
        return {'state':'close' if len(checks)==2 else 'open'}
    async def send(self,group,*args):seen.append(group);return {'message_id':group}
    monkeypatch.setattr(WhatsAppPublisher,'status',state)
    monkeypatch.setattr(WhatsAppPublisher,'publish',send)
    with pytest.raises(RuntimeError):asyncio.run(pubmod.publish_event(db,e,force=True))
    assert seen==['1@g.us'] and e.status=='queued'
    assert not pubmod.is_in_cooldown(db,p.id,7,e.id)
    asyncio.run(pubmod.publish_event(db,e,force=True))
    assert seen==['1@g.us','2@g.us'] and e.status=='published'
    assert db.query(Publication).filter_by(status='published').count()==2


def test_uncertain_send_blocks_automatic_retry(db,monkeypatch):
    e,p=setup_dispatch(db,monkeypatch)
    async def state(self):return {'state':'open'}
    seen=[]
    async def send(self,*args):seen.append(1);raise DeliveryUncertain('timeout')
    monkeypatch.setattr(WhatsAppPublisher,'status',state)
    monkeypatch.setattr(WhatsAppPublisher,'publish',send)
    with pytest.raises(DeliveryUncertain):asyncio.run(pubmod.publish_event(db,e,force=True))
    assert e.status=='failed'
    e.status='queued';db.commit()
    with pytest.raises(DeliveryUncertain):asyncio.run(pubmod.publish_event(db,e,force=True))
    assert len(seen)==1
    assert db.query(Publication).one().status=='uncertain'


def test_adapter_media_payload_and_group_validation(monkeypatch):
    calls=[]
    async def request(self,method,path,payload=None):
        calls.append((method,path,payload));return {'key':{'id':'abc'}}
    monkeypatch.setattr(WhatsAppPublisher,'request',request)
    result=asyncio.run(WhatsAppPublisher().publish('123@g.us','<b>Fone</b> &amp; promoção','https://s.shopee.com.br/x','https://img.example/x.jpg'))
    assert result['message_id']=='abc'
    assert calls[0][1].startswith('message/sendMedia/')
    assert calls[0][2]['number']=='123@g.us' and '<b>' not in calls[0][2]['caption']
    assert calls[0][2]['caption'].endswith('https://s.shopee.com.br/x')
    with pytest.raises(ValueError):asyncio.run(WhatsAppPublisher().publish('55119999','x','url'))


def test_adapter_no_retry_or_fallback_after_timeout(monkeypatch):
    calls=[]
    async def request(*args):calls.append(1);raise TimeoutError()
    monkeypatch.setattr(WhatsAppPublisher,'request',request)
    with pytest.raises(DeliveryUncertain):
        asyncio.run(WhatsAppPublisher().publish('1@g.us','x','https://s.shopee.com.br/x','https://img.example/x.jpg'))
    assert len(calls)==1


def test_caption_never_invents_previous_price():
    caption=build_offer_caption({'productName':'Fone','priceMin':50,'priceDiscountRate':50},'https://s.shopee.com.br/x',90,'manual')
    assert '<s>' not in caption


def test_resume_catchup_commits_cursor_after_durable_enqueue(db,monkeypatch):
    from app.services import collector
    from app.models import SourceCursor
    from sqlalchemy.orm import sessionmaker
    factory=sessionmaker(bind=db.get_bind(),expire_on_commit=False)
    monkeypatch.setattr(collector,'SessionLocal',factory)
    src=Source(name='big group',chat_ref='big');db.add(src);db.commit()
    calls=[]
    class Client:
        async def iter_messages(self,entity,**kw):
            calls.append(kw)
            for mid in ([2,1] if not kw.get('min_id') else [3]):
                yield SimpleNamespace(id=mid,date=datetime.utcnow(),raw_text='https://shopee.com.br/product/1/2')
    async def resolve(client,ref):return ref
    def urls(msg):return [msg.raw_text]
    asyncio.run(collector.catchup_once(Client(),src,resolve,urls))
    asyncio.run(collector.catchup_once(Client(),src,resolve,urls))
    db.expire_all()
    assert db.get(SourceCursor,'big').last_message_id==3
    assert db.query(RadarInbox).count()==3
    assert calls[1]['min_id']==2 and calls[1]['reverse']


def test_telegram_no_fallback_after_ambiguous_photo_failure(monkeypatch):
    from app.services.telegram_bot import TelegramPublisher
    monkeypatch.setattr(settings,'telegram_bot_token','test')
    monkeypatch.setattr(settings,'telegram_target_chat','test')
    calls=[]
    async def fail(self,method,payload):calls.append(method);raise TimeoutError()
    monkeypatch.setattr(TelegramPublisher,'_call',fail)
    with pytest.raises(TimeoutError):
        asyncio.run(TelegramPublisher().publish('offer','https://s.shopee.com.br/x','https://example.com/image.jpg'))
    assert calls==['sendPhoto']
