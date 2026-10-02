"""Durable Telegram inbox: ingest is independent from incoming event handlers."""
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from app.db import SessionLocal
from app.models import RadarInbox, Source, SourceCursor
from app.services.ingest import ingest_url
from app.services.settings_store import load_runtime_settings
from app.services.redis_store import distributed_lock


def enqueue_message(db, source, message_id, urls, posted_at=None):
    added = 0
    for url in urls:
        if len(url) > 2000:
            continue
        try:
            with db.begin_nested():
                db.add(RadarInbox(source_ref=source.chat_ref, message_id=str(message_id), url=url, created_at=posted_at.replace(tzinfo=None) if posted_at else datetime.utcnow()))
                db.flush()
            added += 1
        except IntegrityError:
            pass
    db.commit()
    return added


async def drain_once(db):
    now = datetime.utcnow()
    runtime = load_runtime_settings(db)
    rows = db.query(RadarInbox).filter(RadarInbox.status == 'pending',
        or_(RadarInbox.next_retry_at.is_(None), RadarInbox.next_retry_at <= now)).order_by(RadarInbox.id).limit(20).all()
    completed = 0
    for row in rows:
        source = db.query(Source).filter_by(chat_ref=row.source_ref, active=True).first()
        if not source:
            row.status, row.error = 'skipped', 'fonte removida ou pausada'
            db.commit(); continue
        if row.created_at < now - timedelta(hours=runtime.max_offer_age_hours):
            row.status, row.error = 'expired', 'link expirou na fila de coleta'
            db.commit(); continue
        try:
            await ingest_url(db, row.url, 'telegram', row.source_ref, row.message_id, source.weight, detected_at=row.created_at)
            row.status, row.error = 'done', None
            completed += 1
        except Exception:
            db.rollback()
            row.attempts += 1
            row.error = 'Falha consultando oferta; veja os serviços Shopee e Telegram'
            row.status = 'failed' if row.attempts >= 5 else 'pending'
            row.next_retry_at = datetime.utcnow() + timedelta(seconds=min(3600, 30 * 2 ** row.attempts))
        db.commit()
    return completed


async def inbox_loop():
    while True:
        try:
            with distributed_lock('telegram-inbox', timeout=1800, blocking_timeout=1) as locked:
                if locked:
                    with SessionLocal() as db:
                        await drain_once(db)
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Falha na fila de coleta')
        await asyncio.sleep(3)


async def catchup_once(client, source, resolve_entity, message_urls):
    """Ordered cursor catches messages missed during downtime; bootstrap only recent history."""
    entity = await resolve_entity(client, source.chat_ref)
    with SessionLocal() as db:
        cursor = db.get(SourceCursor, source.chat_ref)
        last_id = cursor.last_message_id if cursor else 0
        runtime = load_runtime_settings(db)
    cutoff = datetime.utcnow() - timedelta(hours=runtime.max_offer_age_hours)
    kwargs = {'limit': 200, 'min_id': last_id, 'reverse': True} if last_id else {'limit': 200}
    messages = [m async for m in client.iter_messages(entity, **kwargs)]
    for msg in sorted(messages, key=lambda m: m.id):
        with SessionLocal() as db:
            active = db.query(Source).filter_by(chat_ref=source.chat_ref, active=True).first()
            if not active:
                return
            stamp = getattr(msg, 'date', None)
            if stamp and stamp.replace(tzinfo=None) >= cutoff:
                enqueue_message(db, source, msg.id, message_urls(msg), posted_at=stamp)
            cursor = db.get(SourceCursor, source.chat_ref)
            if not cursor:
                cursor = SourceCursor(source_ref=source.chat_ref, last_message_id=0)
                db.add(cursor)
            cursor.last_message_id = max(cursor.last_message_id, msg.id)
            db.commit()


async def catchup_loop(client, resolve_entity, message_urls):
    from telethon.errors import FloodWaitError
    while True:
        with SessionLocal() as db:
            sources = db.query(Source).filter_by(active=True).all()
        for source in sources:
            try:
                await catchup_once(client, source, resolve_entity, message_urls)
            except FloodWaitError as exc:
                await asyncio.sleep(exc.seconds + 1)
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Falha ao recuperar fonte %s', source.chat_ref)
        await asyncio.sleep(60)
