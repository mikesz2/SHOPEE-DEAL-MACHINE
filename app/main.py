import asyncio
import base64
import secrets
import hashlib
import hmac
import time
import json
import logging
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, text, or_
from app.db import Base, engine, get_db, SessionLocal
from app.models import Source, Product, OfferEvent, Publication, Conversion, AuditEvent, AppSetting
from app.schemas import SourceIn, RuntimeSettings, ManualIngest, BulkOfferAction
from app.config import settings
from app.services.settings_store import load_runtime_settings, save_runtime_settings
from app.services.ingest import ingest_url
from app.services.radar import run_shopee_radar
from app.services.publisher import publish_event
from app.services.shopee import ShopeeAffiliateClient
from app.services.telegram_bot import TelegramPublisher
from app.services.conversions import sync_conversions
from app.services.redis_store import health as redis_health, get_redis, heartbeat
from app.services.telegram_ipc import queue_command, read_result
from app.services.audit import safe_record

log = logging.getLogger('app')



def _session_secret() -> bytes:
    return hashlib.sha256((settings.app_session_secret or settings.admin_password or 'change-me').encode()).digest()


def _make_session(user: str) -> str:
    issued = int(time.time())
    payload = f'{user}|{issued}'
    sig = hmac.new(_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    raw = f'{payload}|{sig}'.encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def _valid_session(token: str | None) -> bool:
    if not token:
        return False
    try:
        raw = base64.urlsafe_b64decode(token + '=' * (-len(token) % 4)).decode()
        user, issued, sig = raw.rsplit('|', 2)
        if user != settings.admin_user:
            return False
        if int(time.time()) - int(issued) > settings.session_hours * 3600:
            return False
        payload = f'{user}|{issued}'
        expected = hmac.new(_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
        return secrets.compare_digest(sig, expected)
    except Exception:
        return False

def _authorized(request: Request) -> bool:
    if not settings.app_require_auth:
        return True
    if _valid_session(request.cookies.get('sdm_session')):
        return True
    header = request.headers.get('authorization', '')
    if not header.lower().startswith('basic '):
        return False
    try:
        raw = base64.b64decode(header.split(' ', 1)[1]).decode()
        user, password = raw.split(':', 1)
        return secrets.compare_digest(user, settings.admin_user) and secrets.compare_digest(password, settings.admin_password)
    except Exception:
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path('data').mkdir(exist_ok=True)
    if settings.is_production and settings.app_require_auth and not settings.admin_password:
        raise RuntimeError('ADMIN_PASSWORD é obrigatório em produção quando APP_REQUIRE_AUTH=true')
    Base.metadata.create_all(bind=engine)

    # One-time migration: older installations used auto_publish=false by default.
    # Enable automatic publishing once; after this migration the dashboard setting remains authoritative.
    db = SessionLocal()
    try:
        migration_key = 'auto_publish_default_migrated_v1'
        if not db.get(AppSetting, migration_key):
            row = db.get(AppSetting, 'auto_publish')
            if row:
                row.value = json.dumps(True)
            else:
                db.add(AppSetting(key='auto_publish', value=json.dumps(True)))
            db.add(AppSetting(key=migration_key, value=json.dumps(True)))
            db.commit()
            log.info('Publicação automática habilitada pela migração inicial')

        # Queue-drain migration: older installs used a 25-minute interval and
        # a 6-hour offer age, which could leave an already-built queue looking
        # stuck. Keep the normal cadence short enough to drain the queue and
        # allow queued offers to survive normal deployment/restart delays.
        queue_migration_key = 'automatic_queue_drain_migrated_v1'
        if not db.get(AppSetting, queue_migration_key):
            interval = db.get(AppSetting, 'post_interval_minutes')
            if interval is None or str(interval.value) in {'25', '25.0'}:
                if interval:
                    interval.value = json.dumps(5)
                else:
                    db.add(AppSetting(key='post_interval_minutes', value=json.dumps(5)))
            age = db.get(AppSetting, 'max_offer_age_hours')
            if age is None or str(age.value) in {'6', '6.0'}:
                if age:
                    age.value = json.dumps(24)
                else:
                    db.add(AppSetting(key='max_offer_age_hours', value=json.dumps(24)))
            db.add(AppSetting(key=queue_migration_key, value=json.dumps(True)))
            db.commit()
            log.info('Cadência automática ajustada para drenar a fila (5 min / 24h)')
    finally:
        db.close()

    # DisCloud/Docker starts only Uvicorn, so keep the automation worker
    # in the same process as the web app.
    worker_task = None
    try:
        from app.worker import run as run_worker
        worker_task = asyncio.create_task(run_worker(), name='sdm-worker')
        log.info('Worker de automação iniciado junto com a aplicação web')
    except Exception:
        log.exception('Falha ao iniciar o worker de automação')
        raise

    heartbeat('web', {'time': datetime.utcnow().isoformat() + 'Z'}, ttl=180)
    try:
        yield
    finally:
        if worker_task:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            log.info('Worker de automação encerrado')


app = FastAPI(title='Shopee Deal Machine Enterprise', version='8.0.0-discovery', lifespan=lifespan, docs_url=None, redoc_url=None)
app.mount('/static', StaticFiles(directory=Path(__file__).parent / 'static'), name='static')



_login_attempts: dict[str, deque[float]] = defaultdict(deque)

def _login_allowed(ip: str) -> tuple[bool, int]:
    now = time.time(); q = _login_attempts[ip]
    while q and now - q[0] > 900:
        q.popleft()
    if len(q) >= 10:
        retry = max(1, int(900 - (now - q[0])))
        return False, retry
    return True, 0

def _login_failed(ip: str):
    _login_attempts[ip].append(time.time())

@app.middleware('http')
async def admin_auth(request: Request, call_next):
    request_id = request.headers.get('X-Request-ID') or uuid.uuid4().hex[:16]
    public = {'/api/health', '/login', '/api/login'}
    if request.method in {'POST','PUT','PATCH','DELETE'}:
        origin = request.headers.get('origin')
        if origin:
            expected = f"{request.url.scheme}://{request.headers.get('host','')}"
            # Reverse proxies may terminate HTTPS; allow configured public base URL too.
            allowed = {expected.rstrip('/')}
            if settings.public_base_url:
                allowed.add(settings.public_base_url.rstrip('/'))
            if origin.rstrip('/') not in allowed:
                return JSONResponse({'detail':'Origem da requisição não permitida','request_id':request_id}, status_code=403)
    if request.url.path not in public and not request.url.path.startswith('/static/'):
        if not _authorized(request):
            if request.url.path.startswith('/api/') or request.url.path == '/metrics':
                return JSONResponse({'detail': 'Autenticação necessária'}, status_code=401,
                                    headers={'WWW-Authenticate': 'Basic realm="Shopee Deal Machine"'})
            return RedirectResponse('/login', status_code=302)
    response = await call_next(request)
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Request-ID', request_id)
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'no-referrer')
    response.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    response.headers.setdefault('Content-Security-Policy', "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
    if settings.is_production:
        response.headers.setdefault('Cache-Control', 'no-store')
    return response


@app.get('/login')
def login_page(request: Request):
    if _authorized(request):
        return RedirectResponse('/', status_code=302)
    return FileResponse(Path(__file__).parent / 'static' / 'login.html')


@app.post('/api/login')
async def login(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    ip = request.client.host if request.client else 'unknown'
    allowed, retry_after = _login_allowed(ip)
    if not allowed:
        raise HTTPException(429, f'Muitas tentativas. Tente novamente em {retry_after}s')
    user = str(body.get('username', ''))
    password = str(body.get('password', ''))
    if not (secrets.compare_digest(user, settings.admin_user) and secrets.compare_digest(password, settings.admin_password)):
        _login_failed(ip)
        raise HTTPException(401, 'Usuário ou senha inválidos')
    _login_attempts.pop(ip, None)
    response = JSONResponse({'ok': True})
    response.set_cookie('sdm_session', _make_session(user), httponly=True, samesite='strict', secure=settings.cookie_secure, max_age=settings.session_hours * 3600)
    return response


@app.post('/api/logout')
def logout():
    response = JSONResponse({'ok': True})
    response.delete_cookie('sdm_session')
    return response


@app.get('/')
def home():
    return FileResponse(Path(__file__).parent / 'static' / 'index.html')


@app.get('/api/health')
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text('SELECT 1'))
        db_ok = True
    except Exception:
        db_ok = False
    try:
        r = get_redis()
        redis_ok = bool(r and r.ping()) if r else not settings.redis_required
    except Exception:
        redis_ok = False
    ok = db_ok and redis_ok
    return JSONResponse({'ok': ok, 'database': db_ok, 'redis': redis_ok, 'time': datetime.utcnow().isoformat() + 'Z'}, status_code=200 if ok else 503)


@app.get('/api/system/health')
def system_health(db: Session = Depends(get_db)):
    return {
        'web': {'ok': True},
        'worker': redis_health('worker'),
        'listener': redis_health('listener'),
        'shopee_configured': ShopeeAffiliateClient().configured,
        'telegram_bot_configured': TelegramPublisher().configured,
        'telegram_reader_configured': bool(settings.telegram_api_id and settings.telegram_api_hash),
        'target_chat': settings.telegram_target_chat or None,
        'environment': settings.app_env,
    }


@app.get('/api/config-status')
def config_status():
    return {
        'shopee': ShopeeAffiliateClient().configured,
        'telegram_bot': TelegramPublisher().configured,
        'telegram_reader': bool(settings.telegram_api_id and settings.telegram_api_hash),
        'target_chat': settings.telegram_target_chat or None,
        'auth': settings.app_require_auth,
    }


@app.post('/api/integrations/test/shopee')
async def test_shopee():
    client = ShopeeAffiliateClient()
    if not client.configured:
        raise HTTPException(400, 'Credenciais da Shopee não configuradas')
    rows = await client.search_products('oferta', page=1, limit=1)
    return {'ok': True, 'message': 'Shopee conectada', 'sample_count': len(rows)}


@app.post('/api/integrations/test/telegram')
async def test_telegram():
    publisher = TelegramPublisher()
    if not publisher.configured:
        raise HTTPException(400, 'Bot ou canal do Telegram não configurado')
    me = await publisher.get_me()
    chat = await publisher.get_target_chat()
    return {'ok': True, 'bot': me.get('username') or me.get('first_name'), 'target': chat.get('title') or chat.get('username') or str(chat.get('id'))}


@app.get('/api/settings', response_model=RuntimeSettings)
def get_settings(db: Session = Depends(get_db)):
    return load_runtime_settings(db)


@app.put('/api/settings', response_model=RuntimeSettings)
def put_settings(payload: RuntimeSettings, db: Session = Depends(get_db)):
    # Channel changes must go through membership validation at /api/channels.
    current = load_runtime_settings(db)
    for key in ('telegram_publish_enabled', 'whatsapp_enabled', 'whatsapp_groups', 'whatsapp_interval_seconds'):
        setattr(payload, key, getattr(current, key))
    result = save_runtime_settings(db, payload)
    safe_record(db, 'settings.updated', 'Configurações de automação atualizadas', actor='admin')
    return result


@app.get('/api/sources')
def list_sources(db: Session = Depends(get_db)):
    rows = []
    for s in db.query(Source).order_by(Source.commission_total.desc(), Source.id.desc()).all():
        last_event = (db.query(OfferEvent).filter(
            OfferEvent.source_type == 'telegram', OfferEvent.source_ref == s.chat_ref
        ).order_by(OfferEvent.created_at.desc()).first())
        rows.append({
            'id': s.id, 'name': s.name, 'chat_ref': s.chat_ref, 'active': s.active,
            'weight': s.weight, 'learned_weight': s.learned_weight,
            'detected_count': s.detected_count, 'published_count': s.published_count,
            'converted_count': s.converted_count, 'commission_total': s.commission_total,
            'last_detected_at': last_event.created_at.isoformat() if last_event else None,
        })
    return rows


@app.post('/api/sources')
def add_source(payload: SourceIn, db: Session = Depends(get_db)):
    if db.query(Source).filter(Source.chat_ref == payload.chat_ref).first():
        raise HTTPException(409, 'Fonte já cadastrada')
    s = Source(**payload.model_dump())
    db.add(s); db.commit(); db.refresh(s)
    safe_record(db, 'source.added', f'Fonte Telegram adicionada: {s.name}', actor='admin', context={'source_id':s.id,'chat_ref':s.chat_ref})
    return {'id': s.id, 'name': s.name, 'chat_ref': s.chat_ref, 'active': s.active, 'weight': s.weight}


@app.put('/api/sources/{source_id}')
def update_source(source_id: int, payload: SourceIn, db: Session = Depends(get_db)):
    s = db.get(Source, source_id)
    if not s:
        raise HTTPException(404, 'Fonte não encontrada')
    duplicate = db.query(Source).filter(Source.chat_ref == payload.chat_ref, Source.id != source_id).first()
    if duplicate:
        raise HTTPException(409, 'chat_ref já usado em outra fonte')
    for k, v in payload.model_dump().items():
        setattr(s, k, v)
    db.commit(); db.refresh(s)
    return {'ok': True}


@app.delete('/api/sources/{source_id}')
def delete_source(source_id: int, db: Session = Depends(get_db)):
    s = db.get(Source, source_id)
    if not s:
        raise HTTPException(404, 'Fonte não encontrada')
    name, ref = s.name, s.chat_ref
    db.delete(s); db.commit()
    safe_record(db, 'source.deleted', f'Fonte Telegram removida: {name}', actor='admin', context={'chat_ref':ref})
    return {'ok': True}


@app.post('/api/sources/{source_id}/test')
def test_source(source_id: int, db: Session = Depends(get_db)):
    s = db.get(Source, source_id)
    if not s:
        raise HTTPException(404, 'Fonte não encontrada')
    if not redis_health('listener'):
        raise HTTPException(503, 'Radar Telegram está offline. Inicie ou reinicie o robô antes de testar a fonte.')
    return {'ok': True, 'job_id': queue_command('test_source', {'source_id': source_id, 'sample_limit': 50})}


@app.post('/api/sources/{source_id}/import-history')
async def import_source_history(source_id: int, request: Request, db: Session = Depends(get_db)):
    s = db.get(Source, source_id)
    if not s:
        raise HTTPException(404, 'Fonte não encontrada')
    if not redis_health('listener'):
        raise HTTPException(503, 'Radar Telegram está offline. Inicie ou reinicie o robô antes de importar histórico.')
    try:
        body = await request.json()
    except Exception:
        body = {}
    try:
        limit = int(body.get('message_limit', 100))
    except Exception:
        limit = 100
    if limit not in {20, 100, 500}:
        raise HTTPException(422, 'Escolha 20, 100 ou 500 mensagens')
    return {'ok': True, 'job_id': queue_command('import_history', {'source_id': source_id, 'message_limit': limit})}


@app.get('/api/telegram/jobs/{job_id}')
def telegram_job(job_id: str):
    return read_result(job_id)


@app.get('/api/offers')
def offers(limit: int = 100, offset: int = 0, status: str | None = None, source_type: str | None = None,
           q: str | None = None, min_score: float | None = None, db: Session = Depends(get_db)):
    query = db.query(OfferEvent).options(joinedload(OfferEvent.product)).join(Product, OfferEvent.product_id == Product.id)
    if status and status != 'all':
        query = query.filter(OfferEvent.status == status)
    if source_type and source_type != 'all':
        query = query.filter(OfferEvent.source_type == source_type)
    if min_score is not None:
        query = query.filter(OfferEvent.final_score >= min_score)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(or_(Product.name.ilike(term), Product.shop_name.ilike(term), OfferEvent.source_ref.ilike(term)))
    total = query.count()
    rows = query.order_by(OfferEvent.created_at.desc()).offset(max(0, offset)).limit(min(max(limit, 1), 300)).all()
    items = [{
        'id': e.id, 'status': e.status, 'deal_score': e.deal_score, 'trend_score': e.trend_score,
        'score': e.final_score, 'source_type': e.source_type, 'source_ref': e.source_ref,
        'reject_reason': e.reject_reason, 'attempts': e.attempts, 'created_at': e.created_at.isoformat(),
        'next_retry_at': e.next_retry_at.isoformat() if e.next_retry_at else None,
        'product': {
            'id': e.product.id, 'name': e.product.name, 'category': e.product.category,
            'price': e.product.price, 'original_price': e.product.original_price,
            'discount': e.product.discount_rate, 'rating': e.product.rating,
            'sales': e.product.sales, 'commission_rate': e.product.commission_rate,
            'commission': e.product.commission, 'image_url': e.product.image_url,
            'product_url': e.product.product_url, 'shop_name': e.product.shop_name,
        }
    } for e in rows]
    return {'items': items, 'total': total, 'limit': limit, 'offset': offset}


@app.post('/api/manual/ingest')
async def manual_ingest(payload: ManualIngest, db: Session = Depends(get_db)):
    try:
        e = await ingest_url(db, payload.url, 'manual', payload.source_ref)
        safe_record(db, 'offer.manual_ingest', f'Oferta manual analisada #{e.id}', actor='admin', context={'offer_id':e.id,'status':e.status})
        return {'ok': True, 'offer_id': e.id, 'score': e.final_score, 'status': e.status, 'reason': e.reject_reason}
    except Exception as ex:
        raise HTTPException(400, str(ex))


@app.get('/api/radar/status')
def radar_status(db: Session = Depends(get_db)):
    row = db.get(AppSetting, 'shopee_radar_paused')
    paused = bool(row and str(row.value).lower() == 'true')
    return {'paused': paused}


@app.post('/api/radar/pause')
def radar_pause(db: Session = Depends(get_db)):
    row = db.get(AppSetting, 'shopee_radar_paused')
    if not row:
        row = AppSetting(key='shopee_radar_paused', value='true')
        db.add(row)
    else:
        row.value = 'true'
    db.commit()
    safe_record(db, 'radar.paused', 'Radar Shopee pausado pelo administrador', actor='admin')
    return {'ok': True, 'paused': True}


@app.post('/api/radar/resume')
def radar_resume(db: Session = Depends(get_db)):
    row = db.get(AppSetting, 'shopee_radar_paused')
    if not row:
        row = AppSetting(key='shopee_radar_paused', value='false')
        db.add(row)
    else:
        row.value = 'false'
    db.commit()
    safe_record(db, 'radar.resumed', 'Radar Shopee retomado pelo administrador', actor='admin')
    return {'ok': True, 'paused': False}


@app.post('/api/radar/run')
async def radar_run(db: Session = Depends(get_db)):
    try:
        return await run_shopee_radar(db)
    except Exception as ex:
        raise HTTPException(400, str(ex))


@app.post('/api/conversions/sync')
async def conversions_sync(db: Session = Depends(get_db)):
    try:
        return await sync_conversions(db, 30)
    except Exception as ex:
        raise HTTPException(400, str(ex))


@app.post('/api/offers/queue/clear')
def clear_offer_queue(db: Session = Depends(get_db)):
    rows = db.query(OfferEvent).filter(OfferEvent.status == 'queued').all()
    changed = len(rows)
    for event in rows:
        event.status = 'rejected'
        event.reject_reason = 'Fila limpa manualmente pelo administrador'
        event.updated_at = datetime.utcnow()
    db.commit()
    safe_record(db, 'offers.queue_cleared', f'Fila de ofertas limpa: {changed} ofertas removidas da fila', actor='admin', context={'changed': changed})
    return {'ok': True, 'changed': changed}


@app.post('/api/offers/{offer_id}/publish')
async def publish_now(offer_id: int, db: Session = Depends(get_db)):
    e = db.get(OfferEvent, offer_id)
    if not e:
        raise HTTPException(404, 'Oferta não encontrada')
    try:
        p = await publish_event(db, e, force=False)
        safe_record(db, 'offer.published_manual', f'Oferta #{offer_id} publicada manualmente', actor='admin', context={'publication_id':p.id})
        return {'ok': True, 'publication_id': p.id, 'telegram_message_id': p.telegram_message_id}
    except Exception as ex:
        safe_record(db, 'offer.publish_manual_failed', f'Falha ao publicar oferta #{offer_id}: {ex}', 'error', actor='admin')
        raise HTTPException(400, str(ex))


@app.post('/api/offers/{offer_id}/retry')
def retry_offer(offer_id: int, db: Session = Depends(get_db)):
    e = db.get(OfferEvent, offer_id)
    if not e:
        raise HTTPException(404, 'Oferta não encontrada')
    if e.status not in {'failed', 'rejected', 'duplicate'}:
        raise HTTPException(400, f'Oferta em estado {e.status}')
    e.status = 'queued'; e.reject_reason = None; e.reserved_at = None; e.next_retry_at = None
    db.commit()
    safe_record(db, 'offer.retried', f'Oferta #{offer_id} reenfileirada', actor='admin')
    return {'ok': True}


@app.post('/api/offers/bulk')
def bulk_offers(payload: BulkOfferAction, db: Session = Depends(get_db)):
    rows = db.query(OfferEvent).filter(OfferEvent.id.in_(payload.offer_ids)).all()
    changed = 0
    for e in rows:
        if payload.action == 'retry' and e.status in {'failed','rejected','duplicate'}:
            e.status='queued'; e.reject_reason=None; e.reserved_at=None; e.next_retry_at=None; changed += 1
        elif payload.action == 'reject' and e.status in {'queued','failed','reserved'}:
            e.status='rejected'; e.reject_reason='rejeitada manualmente em lote'; e.reserved_at=None; changed += 1
    db.commit()
    safe_record(db, 'offers.bulk_action', f'Ação em lote: {payload.action} ({changed} ofertas)', actor='admin', context={'offer_ids':payload.offer_ids[:50]})
    return {'ok': True, 'changed': changed}


@app.get('/api/conversions/summary')
def conversion_summary(days: int = 30, db: Session = Depends(get_db)):
    cutoff_ts = int((datetime.utcnow() - timedelta(days=max(1, min(days, 90)))).timestamp())
    rows = db.query(Conversion).filter((Conversion.purchase_time.is_(None)) | (Conversion.purchase_time >= cutoff_ts)).all()
    commission = sum(float(x.total_commission or 0) for x in rows)
    orders = sum(int(x.orders_count or 0) for x in rows)
    completed = sum(int(x.completed_orders or 0) for x in rows)
    return {'configured': ShopeeAffiliateClient().configured, 'days': days, 'conversions': len(rows),
            'orders': orders, 'completed_orders': completed, 'commission': round(commission, 2)}


@app.get('/api/stats')
def stats(db: Session = Depends(get_db)):
    day = datetime.utcnow() - timedelta(hours=24)
    week = datetime.utcnow() - timedelta(days=7)
    return {
        'detected_24h': db.query(func.count(OfferEvent.id)).filter(OfferEvent.created_at >= day).scalar() or 0,
        'published_24h': db.query(func.count(Publication.id)).filter(Publication.status == 'published', Publication.published_at >= day).scalar() or 0,
        'telegram_24h': db.query(func.count(OfferEvent.id)).filter(OfferEvent.created_at >= day, OfferEvent.source_type == 'telegram').scalar() or 0,
        'queued': db.query(func.count(OfferEvent.id)).filter(OfferEvent.status == 'queued').scalar() or 0,
        'failed': db.query(func.count(OfferEvent.id)).filter(OfferEvent.status == 'failed').scalar() or 0,
        'sources': db.query(func.count(Source.id)).filter(Source.active.is_(True)).scalar() or 0,
        'commission_7d': round(float(db.query(func.coalesce(func.sum(Conversion.total_commission), 0)).filter(Conversion.synced_at >= week).scalar() or 0), 2),
    }


@app.get('/api/analytics/performance')
def analytics_performance(days: int = 30, db: Session = Depends(get_db)):
    days = max(1, min(days, 180))
    cutoff = datetime.utcnow() - timedelta(days=days)
    pubs = (db.query(Publication).options(joinedload(Publication.offer_event).joinedload(OfferEvent.product))
            .filter(Publication.status == 'published', Publication.published_at >= cutoff).all())
    by_template = {}
    by_source = {}
    by_category = {}
    for p in pubs:
        event = p.offer_event
        product = event.product if event else None
        template = p.template_variant or 'default'
        source = (event.source_ref or event.source_type) if event else 'unknown'
        category = product.category if product else 'outros'
        for bucket, key in ((by_template, template), (by_source, source), (by_category, category)):
            row = bucket.setdefault(key, {'posts': 0, 'converted_posts': 0, 'conversions': 0, 'commission': 0.0})
            row['posts'] += 1
            row['converted_posts'] += 1 if (p.conversion_count or 0) > 0 else 0
            row['conversions'] += int(p.conversion_count or 0)
            row['commission'] += float(p.commission_total or 0)
    def finish(bucket):
        out = []
        for key, row in bucket.items():
            posts = max(1, row['posts'])
            out.append({'key': key, **row,
                        'conversion_post_rate': round(row['converted_posts'] / posts * 100, 2),
                        'commission_per_post': round(row['commission'] / posts, 2),
                        'commission': round(row['commission'], 2)})
        return sorted(out, key=lambda x: (x['commission'], x['converted_posts']), reverse=True)
    return {'days': days, 'posts': len(pubs), 'templates': finish(by_template),
            'sources': finish(by_source), 'categories': finish(by_category)}


@app.get('/api/publications')
def publications(limit: int = 100, db: Session = Depends(get_db)):
    rows = (db.query(Publication).options(joinedload(Publication.offer_event).joinedload(OfferEvent.product))
            .order_by(Publication.created_at.desc()).limit(min(max(limit, 1), 300)).all())
    return [{
        'id': p.id, 'status': p.status, 'template': p.template_variant,
        'tracking_key': p.tracking_key, 'telegram_message_id': p.telegram_message_id,
        'price_at_publish': p.price_at_publish, 'conversion_count': p.conversion_count,
        'commission_total': p.commission_total, 'failure_reason': p.failure_reason,
        'published_at': p.published_at.isoformat() if p.published_at else None,
        'product_name': p.offer_event.product.name if p.offer_event and p.offer_event.product else None,
        'source': (p.offer_event.source_ref or p.offer_event.source_type) if p.offer_event else None,
    } for p in rows]


@app.get('/api/activity')
def activity(limit: int = 50, severity: str | None = None, db: Session = Depends(get_db)):
    q = db.query(AuditEvent)
    if severity and severity != 'all':
        q = q.filter(AuditEvent.severity == severity)
    rows = q.order_by(AuditEvent.created_at.desc()).limit(min(max(limit, 1), 200)).all()
    out=[]
    for a in rows:
        try: ctx=json.loads(a.context_json or '{}')
        except Exception: ctx={}
        out.append({'id':a.id,'type':a.event_type,'severity':a.severity,'actor':a.actor,'message':a.message,'context':ctx,'created_at':a.created_at.isoformat()})
    return out


@app.get('/api/dashboard')
def dashboard(days: int = 7, db: Session = Depends(get_db)):
    days=max(1,min(days,30)); now=datetime.utcnow(); cutoff=now-timedelta(days=days); day=now-timedelta(hours=24)
    events=db.query(OfferEvent).filter(OfferEvent.created_at>=cutoff).all()
    pubs=db.query(Publication).filter(Publication.created_at>=cutoff).all()
    convs=db.query(Conversion).filter(Conversion.synced_at>=cutoff).all()
    daily={}
    for i in range(days):
        d=(now-timedelta(days=days-1-i)).date().isoformat(); daily[d]={'date':d,'detected':0,'published':0,'commission':0.0}
    for e in events:
        k=e.created_at.date().isoformat()
        if k in daily: daily[k]['detected']+=1
    for p in pubs:
        dt=p.published_at or p.created_at; k=dt.date().isoformat()
        if k in daily and p.status=='published': daily[k]['published']+=1
    for c in convs:
        k=c.synced_at.date().isoformat()
        if k in daily: daily[k]['commission']+=float(c.total_commission or 0)
    statuses={}
    for st,count in db.query(OfferEvent.status,func.count(OfferEvent.id)).group_by(OfferEvent.status).all(): statuses[st]=int(count)
    source_rows=(db.query(Source).order_by(Source.commission_total.desc(),Source.converted_count.desc()).limit(6).all())
    top_sources=[{'name':x.name,'chat_ref':x.chat_ref,'detected':x.detected_count,'published':x.published_count,'converted':x.converted_count,'commission':round(float(x.commission_total or 0),2),'weight':round(float(x.learned_weight or 1),2)} for x in source_rows]
    published=[p for p in pubs if p.status=='published']
    total_commission=sum(float(c.total_commission or 0) for c in convs)
    converted_posts=sum(1 for p in published if (p.conversion_count or 0)>0)
    pub_attempts=max(1,len(pubs)); success=len(published)
    worker=redis_health('worker'); listener=redis_health('listener')
    runtime=load_runtime_settings(db)
    return {
      'period_days':days,
      'kpis':{
        'detected_24h':sum(1 for e in events if e.created_at>=day),
        'published_24h':sum(1 for p in published if p.published_at and p.published_at>=day),
        'queue':statuses.get('queued',0), 'failed':statuses.get('failed',0),
        'commission':round(total_commission,2),
        'publish_success_rate':round(success/pub_attempts*100,1),
        'conversion_post_rate':round(converted_posts/max(1,len(published))*100,1),
        'avg_score':round(sum(e.final_score for e in events)/max(1,len(events)),1),
      },
      'daily':list(daily.values()), 'queue_statuses':statuses, 'top_sources':top_sources,
      'services':{'web':True,'worker':bool(worker),'reader':bool(listener),'shopee':ShopeeAffiliateClient().configured,'telegram':TelegramPublisher().configured},
      'automation':{'enabled':runtime.auto_publish,'interval':runtime.post_interval_minutes,'quiet_hours':runtime.quiet_hours_enabled,'min_score':runtime.min_score},
    }


@app.get('/metrics', response_class=PlainTextResponse)
def metrics(db: Session = Depends(get_db)):
    queued = db.query(func.count(OfferEvent.id)).filter(OfferEvent.status == 'queued').scalar() or 0
    published = db.query(func.count(Publication.id)).filter(Publication.status == 'published').scalar() or 0
    failed = db.query(func.count(OfferEvent.id)).filter(OfferEvent.status == 'failed').scalar() or 0
    return f'sdm_queue_total {queued}\nsdm_publications_total {published}\nsdm_failed_total {failed}\nsdm_worker_up {1 if redis_health("worker") else 0}\nsdm_reader_up {1 if redis_health("listener") else 0}\n'

# V7: multichannel controls reuse the existing authentication and origin checks.
from pydantic import BaseModel, Field, field_validator
from app.services.whatsapp import WhatsAppPublisher
from app.models import RadarInbox, SourceCursor
from app.services.quality import price_evidence


class ChannelSettings(BaseModel):
    telegram_publish_enabled: bool = True
    whatsapp_enabled: bool = False
    whatsapp_groups: list[str] = Field(default_factory=list, max_length=30)
    whatsapp_interval_seconds: int = Field(default=30, ge=10, le=120)

    @field_validator('whatsapp_groups')
    @classmethod
    def valid_groups(cls, groups):
        import re
        if any(not re.fullmatch(r'[0-9-]+@g\.us', group) for group in groups):
            raise ValueError('Selecione apenas IDs de grupos WhatsApp')
        return list(dict.fromkeys(groups))


@app.get('/api/channels')
def channel_settings(db: Session = Depends(get_db)):
    runtime = load_runtime_settings(db)
    return ChannelSettings(**runtime.model_dump())


@app.put('/api/channels')
async def save_channels(payload: ChannelSettings, db: Session = Depends(get_db)):
    if payload.whatsapp_enabled and not payload.whatsapp_groups:
        raise HTTPException(422, 'Selecione pelo menos um grupo WhatsApp')
    if payload.whatsapp_enabled:
        try:
            groups = {g['id'] for g in await WhatsAppPublisher().groups()}
        except Exception as exc:
            raise HTTPException(502, str(exc))
        if any(g not in groups for g in payload.whatsapp_groups):
            raise HTTPException(422, 'Um grupo selecionado não está acessível nessa conta')
    runtime = load_runtime_settings(db)
    result = RuntimeSettings(**{**runtime.model_dump(), **payload.model_dump()})
    save_runtime_settings(db, result)
    safe_record(db, 'channels.updated', 'Destinos de publicação atualizados', actor='admin')
    return payload


@app.get('/api/whatsapp/status')
async def whatsapp_status():
    try:
        return await WhatsAppPublisher().status()
    except Exception as exc:
        raise HTTPException(502, str(exc))


@app.post('/api/whatsapp/connect')
async def whatsapp_connect():
    try:
        return await WhatsAppPublisher().connect()
    except Exception as exc:
        raise HTTPException(502, str(exc))


@app.get('/api/whatsapp/groups')
async def whatsapp_groups():
    try:
        return await WhatsAppPublisher().groups()
    except Exception as exc:
        raise HTTPException(502, str(exc))


@app.get('/api/deliveries')
def delivery_list(db: Session = Depends(get_db)):
    rows = db.query(Publication).order_by(Publication.id.desc()).limit(100).all()
    return [{'id':x.id, 'offer_id':x.offer_event_id, 'destination':x.telegram_chat,
             'status':x.status, 'error':x.failure_reason, 'date':x.published_at} for x in rows]


class ReconcileDelivery(BaseModel):
    delivered: bool


@app.post('/api/deliveries/{pub_id}/reconcile')
def reconcile_delivery(pub_id: int, payload: ReconcileDelivery, db: Session = Depends(get_db)):
    pub = db.get(Publication, pub_id)
    if not pub or pub.status not in {'uncertain', 'sending'}:
        raise HTTPException(409, 'Publicação não está aguardando conferência')
    event = db.get(OfferEvent, pub.offer_event_id)
    if event.status == 'reserved' and event.reserved_at and event.reserved_at > datetime.utcnow() - timedelta(minutes=125):
        raise HTTPException(409, 'Envio ainda em andamento; aguarde o worker concluir')
    pub.status = 'published' if payload.delivered else 'failed'
    pub.published_at = datetime.utcnow() if payload.delivered else None
    pub.failure_reason = None if payload.delivered else 'Administrador confirmou que não foi entregue'
    event.status, event.attempts, event.next_retry_at, event.reserved_at = 'queued', 0, None, None
    db.commit()
    safe_record(db, 'delivery.reconciled', f'Envio #{pub.id} conferido pelo administrador', actor='admin', context={'delivered':payload.delivered})
    return {'ok':True}


@app.get('/api/radar/quality')
def radar_quality(db: Session = Depends(get_db)):
    counts = dict(db.query(RadarInbox.status, func.count(RadarInbox.id)).group_by(RadarInbox.status).all())
    cursors = db.query(SourceCursor).all()
    return {'inbox':counts, 'sources':[{'source':x.source_ref, 'last_message_id':x.last_message_id,
            'updated_at':x.updated_at} for x in cursors]}


@app.get('/api/offers/{offer_id}/quality')
def offer_quality(offer_id: int, db: Session = Depends(get_db)):
    event = db.get(OfferEvent, offer_id)
    if not event:
        raise HTTPException(404, 'Oferta não encontrada')
    return price_evidence(db, db.get(Product, event.product_id))
