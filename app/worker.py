import asyncio
import logging
import random
from datetime import datetime, timedelta
from sqlalchemy import func
from app.config import settings
from app.db import SessionLocal
from app.models import OfferEvent
from app.services.settings_store import load_runtime_settings
from app.services.radar import run_shopee_radar
from app.services.publisher import publish_next_eligible, recover_stale_reservations
from app.services.conversions import sync_conversions
from app.services.redis_store import heartbeat
from app.services.telegram_bot import TelegramPublisher
from app.services.housekeeping import cleanup_old_data
from app.services.audit import safe_record

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                    format='%(asctime)s %(levelname)s %(name)s %(message)s')
log = logging.getLogger('worker')


async def run():
    last_radar = None
    last_conversion = None
    last_cleanup = None
    error_streak = 0
    breaker_until: datetime | None = None
    last_alerted_queue = 0
    last_published_id = None

    while True:
        db = SessionLocal()
        try:
            runtime = load_runtime_settings(db)
            now = datetime.utcnow()
            recover_stale_reservations(db)
            queued = int(db.query(func.count(OfferEvent.id)).filter(OfferEvent.status == 'queued').scalar() or 0)

            # Backpressure: if the queue is already very large, prioritize draining it instead of
            # continuously spending API quota on discovery.
            radar_allowed = queued < runtime.max_queue_depth
            if queued >= runtime.alert_queue_depth and queued >= last_alerted_queue + max(25, runtime.alert_queue_depth // 4):
                await TelegramPublisher().notify_admin(f'⚠️ Fila do Shopee Deal Machine está com {queued} ofertas aguardando.')
                safe_record(db, 'queue.high', f'Fila alta: {queued} ofertas', 'warning', context={'queued': queued})
                last_alerted_queue = queued

            if radar_allowed and (last_radar is None or now - last_radar >= timedelta(minutes=runtime.radar_interval_minutes)):
                try:
                    result = await run_shopee_radar(db)
                    log.info('radar=%s', result)
                    safe_record(db, 'radar.completed', f"Radar concluído: {result.get('created', 0)} novas ofertas", context=result)
                except Exception as exc:
                    log.exception('Erro no radar Shopee')
                    safe_record(db, 'radar.failed', str(exc), 'error')
                last_radar = now
            elif not radar_allowed:
                log.warning('Radar pausado por backpressure queue=%s max=%s', queued, runtime.max_queue_depth)

            if last_cleanup is None or now - last_cleanup >= timedelta(hours=6):
                try:
                    result = cleanup_old_data(db)
                    log.info('cleanup=%s', result)
                    safe_record(db, 'maintenance.cleanup', 'Limpeza periódica concluída', context=result)
                except Exception as exc:
                    log.exception('Erro na limpeza de dados antigos')
                    safe_record(db, 'maintenance.cleanup_failed', str(exc), 'warning')
                last_cleanup = now

            if last_conversion is None or now - last_conversion >= timedelta(minutes=runtime.conversion_sync_minutes):
                try:
                    result = await sync_conversions(db, days=30)
                    log.info('conversions=%s', result)
                except Exception as exc:
                    log.exception('Erro sincronizando conversões')
                    safe_record(db, 'conversions.failed', str(exc), 'warning')
                last_conversion = now

            if breaker_until and now >= breaker_until:
                safe_record(db, 'publisher.circuit_closed', 'Circuit breaker liberado; publicador retomado', 'info')
                breaker_until = None
            breaker_open = bool(breaker_until and now < breaker_until)
            if not breaker_open:
                try:
                    pub = await publish_next_eligible(db)
                    if pub:
                        last_published_id = pub.id
                        log.info('publicado publication_id=%s telegram_id=%s', pub.id, pub.telegram_message_id)
                        safe_record(db, 'publication.success', f'Publicação #{pub.id} enviada aos destinos configurados', context={'publication_id': pub.id, 'telegram_message_id': pub.telegram_message_id})
                except Exception as exc:
                    error_streak += 1
                    log.exception('Erro no publicador')
                    safe_record(db, 'publication.failed', str(exc), 'error', context={'error_streak': error_streak})
                    if error_streak in {3, runtime.circuit_breaker_failures}:
                        await TelegramPublisher().notify_admin(f'⚠️ Shopee Deal Machine: {error_streak} falhas consecutivas no publicador. Último erro: {exc}')
                    if error_streak >= runtime.circuit_breaker_failures:
                        breaker_until = now + timedelta(minutes=runtime.circuit_breaker_cooldown_minutes)
                        safe_record(db, 'publisher.circuit_open', f'Circuit breaker aberto por {runtime.circuit_breaker_cooldown_minutes} min', 'critical')
                else:
                    if error_streak:
                        safe_record(db, 'publisher.recovered', 'Publicador se recuperou após falhas', 'info', context={'previous_streak': error_streak})
                    error_streak = 0

            heartbeat('worker', {
                'time': datetime.utcnow().isoformat() + 'Z',
                'error_streak': error_streak,
                'queue_depth': queued,
                'radar_backpressure': not radar_allowed,
                'circuit_breaker_until': breaker_until.isoformat() + 'Z' if breaker_until else None,
                'last_published_id': last_published_id,
            }, ttl=max(60, settings.worker_poll_seconds * 5))
        except Exception as exc:
            error_streak += 1
            log.exception('Erro geral no worker')
            safe_record(db, 'worker.failed', str(exc), 'critical')
            heartbeat('worker', {'time': datetime.utcnow().isoformat() + 'Z', 'error': str(exc), 'error_streak': error_streak}, ttl=120)
        finally:
            db.close()
        await asyncio.sleep(max(3, settings.worker_poll_seconds) + random.random())


if __name__ == '__main__':
    asyncio.run(run())
