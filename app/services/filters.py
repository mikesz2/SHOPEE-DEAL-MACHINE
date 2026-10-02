from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models import Product, Publication, OfferEvent
from app.services.product_utils import csv_items, normalize_name, name_similarity
from app.config import settings


def blocked_reason(product: Product, runtime) -> str | None:
    if runtime.require_quality_data and (product.rating is None or product.sales is None or product.commission_rate is None):
        return 'dados de avaliação, vendas ou comissão ausentes'
    name = normalize_name(product.name)
    for term in csv_items(runtime.blocked_keywords):
        if term and term in name:
            return f'palavra bloqueada: {term}'
    blocked_shops = {x.strip() for x in (runtime.blocked_shop_ids or '').split(',') if x.strip()}
    if product.shop_id in blocked_shops:
        return 'loja bloqueada'
    if product.price is None or product.price <= 0:
        return 'preço indisponível'
    if product.discount_rate is not None and product.discount_rate < runtime.min_discount:
        return 'desconto abaixo do mínimo'
    if product.rating is not None and product.rating < runtime.min_rating:
        return 'avaliação abaixo do mínimo'
    if product.sales is not None and product.sales < runtime.min_sales:
        return 'vendas abaixo do mínimo'
    if product.commission_rate is not None and product.commission_rate < runtime.min_commission_rate:
        return 'comissão abaixo do mínimo'
    return None


def priority_boost(product_name: str, runtime) -> float:
    name = normalize_name(product_name)
    return 4.0 if any(term and term in name for term in csv_items(runtime.priority_keywords)) else 0.0


def in_quiet_hours(runtime) -> bool:
    if not runtime.quiet_hours_enabled:
        return False
    hour = datetime.now(ZoneInfo(settings.app_timezone)).hour
    start, end = runtime.quiet_start_hour, runtime.quiet_end_hour
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def category_quota_exceeded(db: Session, product: Product, runtime) -> bool:
    limit = int(runtime.category_daily_limits.get(product.category, runtime.category_daily_limits.get('outros', 10)))
    if limit <= 0:
        return True
    cutoff = datetime.utcnow() - timedelta(hours=24)
    count = (db.query(func.count(func.distinct(Publication.offer_event_id))).join(OfferEvent).join(Product, OfferEvent.product_id == Product.id)
             .filter(Publication.status == 'published', Publication.published_at >= cutoff, Product.category == product.category)
             .scalar())
    return count >= limit


def too_many_same_category(db: Session, product: Product, runtime) -> bool:
    rows = (db.query(Product.category, OfferEvent.id).join(OfferEvent, OfferEvent.product_id == Product.id)
            .join(Publication, Publication.offer_event_id == OfferEvent.id)
            .filter(Publication.status == 'published').group_by(Product.category, OfferEvent.id)
            .order_by(func.max(Publication.published_at).desc()).limit(runtime.max_same_category_consecutive).all())
    return len(rows) >= runtime.max_same_category_consecutive and all(r[0] == product.category for r in rows)



def similar_recently_published(db: Session, product: Product, runtime) -> tuple[bool, str | None]:
    if runtime.similarity_cooldown_hours <= 0:
        return False, None
    cutoff = datetime.utcnow() - timedelta(hours=runtime.similarity_cooldown_hours)
    rows = (db.query(Product).join(OfferEvent, OfferEvent.product_id == Product.id)
            .join(Publication, Publication.offer_event_id == OfferEvent.id)
            .filter(Publication.status == 'published', Publication.published_at >= cutoff, Product.id != product.id)
            .order_by(Publication.published_at.desc()).limit(100).all())
    for other in rows:
        sim = name_similarity(product.name, other.name)
        if sim >= runtime.similarity_threshold:
            return True, f'similar a produto recente ({sim:.0%})'
    return False, None
