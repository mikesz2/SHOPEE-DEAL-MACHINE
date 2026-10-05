import asyncio
import logging
import uuid
import re
from datetime import datetime, timedelta
from sqlalchemy import update, or_
from sqlalchemy.orm import Session
from app.models import OfferEvent, Publication, Product, Source
from app.services.settings_store import load_runtime_settings
from app.services.message_builder import build_offer_caption
from app.services.telegram_bot import TelegramPublisher
from app.services.shopee import ShopeeAffiliateClient
from app.services.ingest import upsert_product
from app.services.filters import (
    blocked_reason, too_many_same_category,
    similar_recently_published, in_quiet_hours
)
from app.services.analytics import choose_template, smart_interval_minutes
from app.services.redis_store import distributed_lock
from app.config import settings
from app.services.whatsapp import WhatsAppPublisher, DeliveryUncertain

log = logging.getLogger(__name__)


def safe_subid(value: str | None, fallback: str = 'src') -> str:
    value = re.sub(r'[^A-Za-z0-9]+', '', (value or fallback))
    value = value or re.sub(r'[^A-Za-z0-9]+', '', fallback) or 'src'
    if not value[0].isalpha():
        value = 's' + value
    return value[:20]

def is_in_cooldown(db: Session, product_id: int, cooldown_days: int, exclude_event_id: int | None = None) -> bool:
    if cooldown_days <= 0:
        return False
    cutoff = datetime.utcnow() - timedelta(days=cooldown_days)
    return (db.query(Publication).join(OfferEvent)
            .filter(OfferEvent.product_id == product_id, Publication.status == 'published',
                    Publication.offer_event_id != (exclude_event_id or -1),
                    Publication.published_at >= cutoff).first() is not None)


def reserve_event(db: Session, event_id: int) -> OfferEvent | None:
    now = datetime.utcnow()
    result = db.execute(
        update(OfferEvent)
        .where(OfferEvent.id == event_id, OfferEvent.status == 'queued')
        .values(status='reserved', reserved_at=now, attempts=OfferEvent.attempts + 1, next_retry_at=None)
    )
    db.commit()
    if result.rowcount != 1:
        return None
    return db.get(OfferEvent, event_id)


def recover_stale_reservations(db: Session, minutes: int = 125) -> int:
    cutoff = datetime.utcnow() - timedelta(minutes=minutes)
    result = db.execute(
        update(OfferEvent)
        .where(OfferEvent.status == 'reserved', OfferEvent.reserved_at < cutoff)
        .values(status='queued', reserved_at=None, next_retry_at=datetime.utcnow(), reject_reason='reserva expirada; reencaminhada')
    )
    db.commit()
    return int(result.rowcount or 0)


async def _revalidate(db: Session, event: OfferEvent) -> tuple[Product, float | None]:
    product = db.get(Product, event.product_id)
    if not product or not product.product_url:
        raise RuntimeError('Produto sem URL válida para revalidação')
    old_price = product.price
    client = ShopeeAffiliateClient()
    if not client.configured:
        raise RuntimeError('Shopee API não configurada; publicação exige revalidação')
    node = await client.get_product(product.product_url, strict=True)
    if not node:
        raise RuntimeError('Oferta não encontrada na Shopee durante revalidação')
    product = await upsert_product(db, node)
    if product.offer_period_end and product.offer_period_end < int(datetime.utcnow().timestamp()):
        raise RuntimeError('Período da oferta encerrado')
    return product, old_price


def _validate_for_publish(db: Session, event: OfferEvent, product: Product, runtime, force: bool = False):
    reason = blocked_reason(product, runtime)
    if reason:
        raise ValueError(reason)
    if event.final_score < runtime.min_score and not force:
        raise ValueError('score abaixo do mínimo')
    if is_in_cooldown(db, product.id, runtime.cooldown_days, event.id) and not force:
        raise ValueError('produto em cooldown')
    if too_many_same_category(db, product, runtime) and not force:
        raise ValueError('categoria já apareceu vezes demais em sequência')
    similar, sim_reason = similar_recently_published(db, product, runtime)
    if similar and not force:
        raise ValueError(sim_reason or 'produto muito similar a publicação recente')


def publication_targets(runtime):
    targets = []
    if runtime.telegram_publish_enabled:
        targets.append(settings.telegram_target_chat)
    if runtime.whatsapp_enabled:
        targets.extend('wa:' + group for group in dict.fromkeys(runtime.whatsapp_groups))
    return targets


async def publish_reserved_event(db: Session, event: OfferEvent, force: bool = False) -> Publication:
    if event.status != 'reserved':
        raise RuntimeError('Oferta não está reservada para publicação')
    runtime = load_runtime_settings(db)
    try:
        targets = publication_targets(runtime)
        if not targets or any(not target for target in targets):
            raise RuntimeError('Selecione pelo menos um destino válido de publicação')
        previous = db.query(Publication).filter_by(offer_event_id=event.id).all()
        if any(x.status in {'sending', 'uncertain'} for x in previous):
            raise DeliveryUncertain('Há envio sem confirmação. Confira e resolva na aba WhatsApp antes de tentar novamente')
        sent = {x.telegram_chat for x in previous if x.status == 'published'}
        product, old_price = await _revalidate(db, event)
        if old_price and product.price and product.price > old_price:
            increase = (product.price - old_price) / old_price * 100
            if increase > runtime.max_price_increase_pct and not force:
                raise ValueError(f'preço subiu {increase:.1f}% desde a detecção')
        if not force and event.created_at < datetime.utcnow() - timedelta(hours=runtime.max_offer_age_hours):
            raise ValueError('oferta antiga: descubra novamente para publicar')
        # Re-score current data rather than trusting the stale discovery score.
        from app.services.scoring import deal_score, combined_score
        from app.services.quality import price_evidence
        current = deal_score({'price':product.price, 'discount_rate':product.discount_rate,
            'rating':product.rating, 'sales':product.sales, 'commission_rate':product.commission_rate,
            'commission':product.commission}, source_weight=event.source_weight_snapshot)
        current += price_evidence(db, product)['score_adjustment']
        event.deal_score = max(0, min(100, current))
        event.final_score = combined_score(event.deal_score, event.trend_score)
        if not sent:
            _validate_for_publish(db, event, product, runtime, force=force)
        else:
            reason = blocked_reason(product, runtime)
            if reason:
                raise ValueError(reason)
            if event.final_score < runtime.min_score and not force:
                raise ValueError('score atualizado abaixo do mínimo')
        template = choose_template(db, product.category, runtime.allowed_templates, runtime.template_learning)
        last_pub = next((x for x in previous if x.status == 'published'), None)
        wa_count = 0
        for target in targets:
            if target in sent:
                continue
            is_wa = target.startswith('wa:')
            if is_wa:
                provider = WhatsAppPublisher()
                state = await provider.status()
                if state.get('state') != 'open':
                    raise RuntimeError('WhatsApp desconectado; conecte pela aba WhatsApp')
                if wa_count:
                    await asyncio.sleep(runtime.whatsapp_interval_seconds)
            pub = Publication(offer_event_id=event.id, telegram_chat=target,
                status='pending', template_variant=template, tracking_key='pending-' + uuid.uuid4().hex,
                price_at_publish=product.price, commission_rate_at_publish=product.commission_rate)
            db.add(pub); db.commit(); db.refresh(pub)
            pub.tracking_key = f'p{pub.id}'
            client = ShopeeAffiliateClient()
            url = await client.generate_short_link(product.product_url,
                ['whatsapp' if is_wa else 'telegram', safe_subid(event.source_ref or event.source_type),
                 pub.tracking_key, safe_subid(product.category), safe_subid(template)])
            caption = build_offer_caption({'productName':product.name, 'price':product.price,
                'priceMin':product.price, 'original_price':None, 'discount_rate':product.discount_rate,
                'rating':product.rating, 'sales':product.sales}, url, event.final_score, event.source_type, template)
            pub.caption, pub.affiliate_url = caption, url
            pub.status = 'sending'
            db.commit()  # crash after dispatch => uncertain, never silently resend
            try:
                result = await (provider.publish(target[3:], caption, url, product.image_url) if is_wa
                    else TelegramPublisher().publish(caption, url, product.image_url))
            except Exception as exc:
                pub.status = 'uncertain'
                pub.failure_reason = 'Confira o destino antes de liberar nova tentativa'
                db.commit()
                raise DeliveryUncertain(pub.failure_reason) from exc
            pub.telegram_message_id = str(result.get('message_id') or '')
            pub.status, pub.published_at = 'published', datetime.utcnow()
            db.commit()
            last_pub = pub
            wa_count += int(is_wa)
        event.status, event.reject_reason, event.reserved_at = 'published', None, None
        if event.source_ref:
            source = db.query(Source).filter_by(chat_ref=event.source_ref).one_or_none()
            if source:
                source.published_count += 1
        db.commit()
        return last_pub
    except DeliveryUncertain as exc:
        event.status, event.reject_reason, event.reserved_at = 'failed', str(exc)[:255], None
        event.next_retry_at = None
        db.commit()
        raise
    except ValueError as exc:
        event.status, event.reject_reason, event.reserved_at = 'rejected', str(exc)[:255], None
        db.commit()
        raise
    except Exception as exc:
        event.status = 'failed' if event.attempts >= runtime.max_publish_attempts else 'queued'
        delay = min(21600, runtime.retry_base_seconds * 2 ** max(0, event.attempts - 1))
        event.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
        event.reject_reason, event.reserved_at = str(exc)[:255], None
        db.commit()
        raise


async def publish_event(db: Session, event: OfferEvent, force: bool = False) -> Publication:
    if event.status != 'queued':
        raise RuntimeError(f'Oferta não pode ser publicada no estado {event.status}')
    reserved = reserve_event(db, event.id)
    if not reserved:
        raise RuntimeError('Oferta já foi reservada por outro worker')
    return await publish_reserved_event(db, reserved, force=force)


def _is_breaking(event: OfferEvent, runtime) -> bool:
    return bool(runtime.breaking_enabled and event.final_score >= runtime.breaking_min_score and event.trend_score >= runtime.breaking_min_trend)


async def publish_next_eligible(db: Session):
    runtime = load_runtime_settings(db)
    if not runtime.auto_publish or in_quiet_hours(runtime):
        return None
    recover_stale_reservations(db)
    with distributed_lock('publisher', timeout=7200, blocking_timeout=1) as locked:
        if not locked:
            return None
        last = (db.query(Publication).filter(Publication.status == 'published')
                .order_by(Publication.published_at.desc()).first())
        events = (db.query(OfferEvent).filter(OfferEvent.status == 'queued',
                  or_(OfferEvent.next_retry_at.is_(None), OfferEvent.next_retry_at <= datetime.utcnow()))
                  .order_by(OfferEvent.final_score.desc(), OfferEvent.trend_score.desc(), OfferEvent.created_at.asc())
                  .limit(80).all())
        if not events:
            return None
        breaking = next((e for e in events if _is_breaking(e, runtime)), None)
        if breaking:
            if last and last.published_at and last.published_at > datetime.utcnow() - timedelta(minutes=runtime.breaking_min_interval_minutes):
                breaking = None
        if not breaking:
            interval = smart_interval_minutes(db, runtime.post_interval_minutes, runtime.smart_schedule)
            if last and last.published_at and last.published_at > datetime.utcnow() - timedelta(minutes=interval):
                return None
        candidates = [breaking] if breaking else events
        last_operational_error = None
        operational_failures = 0
        for event in [x for x in candidates if x is not None]:
            product = db.get(Product, event.product_id)
            if not product:
                event.status = 'rejected'; event.reject_reason = 'produto inexistente'; db.commit(); continue
            if is_in_cooldown(db, product.id, runtime.cooldown_days, event.id):
                event.status = 'duplicate'; event.reject_reason = 'produto em cooldown'; db.commit(); continue
            reserved = reserve_event(db, event.id)
            if not reserved:
                continue
            try:
                return await publish_reserved_event(db, reserved)
            except ValueError:
                # Regras de negócio rejeitam a oferta sem indicar falha do sistema.
                continue
            except Exception as exc:
                operational_failures += 1
                last_operational_error = exc
                log.exception('Falha ao publicar oferta %s', event.id)
                # Tente o próximo candidato, mas propague a falha se nenhum publicar.
                continue
        if operational_failures and last_operational_error is not None:
            raise RuntimeError(f'{operational_failures} falha(s) operacionais no publicador; última: {last_operational_error}') from last_operational_error
        return None
