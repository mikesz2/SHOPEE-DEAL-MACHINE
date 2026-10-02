from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, distinct
from sqlalchemy.exc import IntegrityError
from app.models import Product, OfferEvent, PriceSnapshot, Source
from app.services.shopee import ShopeeAffiliateClient
from app.services.scoring import deal_score, trend_score, combined_score
from app.services.message_builder import estimated_original
from app.services.url_utils import resolve_url, extract_identity
from app.services.product_utils import normalize_name, categorize
from app.services.filters import priority_boost, blocked_reason
from app.services.settings_store import load_runtime_settings
from app.services.analytics import source_learning_multiplier


def fnum(v):
    try:
        return float(v) if v is not None else None
    except Exception:
        return None


def inum(v):
    try:
        return int(float(v)) if v is not None else None
    except Exception:
        return None


def normalize_pct(v):
    v = fnum(v)
    if v is None:
        return None
    return v * 100 if 0 <= v <= 1 else v


async def upsert_product(db: Session, node: dict) -> Product:
    shop_id = str(node.get('shopId') or '')
    item_id = str(node.get('itemId') or '')
    if not shop_id or not item_id:
        raise ValueError('Produto sem shopId/itemId')
    product = db.query(Product).filter(Product.shop_id == shop_id, Product.item_id == item_id).one_or_none()
    if not product:
        product = Product(shop_id=shop_id, item_id=item_id, name=str(node.get('productName') or f'Produto {item_id}'))
        db.add(product)
    price = fnum(node.get('priceMin'))
    discount = normalize_pct(node.get('priceDiscountRate'))
    product.name = str(node.get('productName') or product.name)
    product.normalized_name = normalize_name(product.name)
    product.category = categorize(product.name)
    product.shop_name = node.get('shopName') or product.shop_name
    product.image_url = node.get('imageUrl') or product.image_url
    product.product_url = node.get('productLink') or node.get('resolvedUrl') or product.product_url
    product.price = price if price is not None else product.price
    product.discount_rate = discount if discount is not None else product.discount_rate
    product.original_price = None
    product.rating = fnum(node.get('ratingStar')) if node.get('ratingStar') is not None else product.rating
    product.sales = inum(node.get('sales')) if node.get('sales') is not None else product.sales
    product.commission_rate = normalize_pct(node.get('commissionRate')) if node.get('commissionRate') is not None else product.commission_rate
    product.commission = fnum(node.get('commission')) if node.get('commission') is not None else product.commission
    product.offer_period_end = inum(node.get('periodEndTime')) if node.get('periodEndTime') is not None else product.offer_period_end
    product.updated_at = datetime.utcnow()
    db.flush()
    db.add(PriceSnapshot(product_id=product.id, price=product.price, discount_rate=product.discount_rate, commission_rate=product.commission_rate))
    db.commit()
    db.refresh(product)
    return product


def _trend_metrics(db: Session, product_id: int, new_source_ref: str | None) -> tuple[int, int, int, int]:
    now = datetime.utcnow()
    c10 = now - timedelta(minutes=10)
    c30 = now - timedelta(minutes=30)
    def sources(cutoff):
        refs = {r[0] for r in db.query(OfferEvent.source_ref).filter(
            OfferEvent.product_id == product_id, OfferEvent.created_at >= cutoff,
            OfferEvent.source_type.in_(['telegram', 'whatsapp'])).all() if r[0]}
        if new_source_ref:
            refs.add(new_source_ref)
        return len(refs)
    # Each source contributes once: repetition cannot inflate velocity.
    a, b = sources(c10), sources(c30)
    return a, b, a, b



async def ingest_node(db: Session, node: dict, source_type: str, source_ref: str | None = None,
                      source_message_id: str | None = None, detected_url: str | None = None,
                      source_weight: float = 1.0, detected_at: datetime | None = None) -> OfferEvent:
    identity = db.query(Product).filter(Product.shop_id == str(node.get('shopId')), Product.item_id == str(node.get('itemId'))).first()
    if identity and source_message_id:
        existing = db.query(OfferEvent).filter_by(product_id=identity.id, source_type=source_type, source_ref=source_ref, source_message_id=source_message_id).first()
        if existing:
            return existing
    product = await upsert_product(db, node)
    runtime = load_runtime_settings(db)
    adaptive = source_learning_multiplier(db, source_ref) if runtime.source_learning else 1.0
    weight = max(0.1, min(source_weight * adaptive, 5.0))
    d10, d30, h10, h30 = _trend_metrics(db, product.id, source_ref if source_type in {'telegram', 'whatsapp'} and (not detected_at or detected_at >= datetime.utcnow() - timedelta(minutes=10)) else None)
    tr = trend_score(d10, d30, h10, h30)
    pboost = priority_boost(product.name, runtime)
    ds = deal_score({
        'price': product.price, 'discount_rate': product.discount_rate, 'rating': product.rating,
        'sales': product.sales, 'commission_rate': product.commission_rate, 'commission': product.commission,
    }, source_hits=max(1, d30), source_weight=weight, priority_boost=pboost)
    from app.services.quality import price_evidence
    evidence = price_evidence(db, product)
    ds = round(max(0, min(100, ds + evidence['score_adjustment'])), 1)
    final = combined_score(ds, tr)
    reason = blocked_reason(product, runtime)
    active = db.query(OfferEvent).filter(OfferEvent.product_id == product.id, OfferEvent.status.in_(['queued','reserved'])).first()
    status = 'rejected' if reason else ('duplicate' if active else 'queued')
    if active and active.status == 'queued':
        active.deal_score, active.trend_score, active.final_score = ds, tr, final
    if active and not reason:
        reason = 'produto já possui uma oferta ativa na fila' 
    event = OfferEvent(
        product_id=product.id, source_type=source_type, source_ref=source_ref,
        source_message_id=source_message_id, detected_url=detected_url,
        deal_score=ds, trend_score=tr, final_score=final,
        source_weight_snapshot=weight, status=status, reject_reason=reason,
        created_at=detected_at or datetime.utcnow(),
    )
    db.add(event)
    try:
        db.commit()
        db.refresh(event)
    except IntegrityError:
        db.rollback()
        existing = (db.query(OfferEvent).filter(OfferEvent.product_id == product.id,
                    OfferEvent.source_type == source_type, OfferEvent.source_ref == source_ref,
                    OfferEvent.source_message_id == source_message_id).order_by(OfferEvent.id.desc()).first())
        if existing:
            return existing
        raise
    if source_ref:
        source = db.query(Source).filter(Source.chat_ref == source_ref).one_or_none()
        if source:
            source.detected_count += 1
            db.commit()
    return event


async def ingest_url(db: Session, url: str, source_type: str, source_ref: str | None = None,
                     source_message_id: str | None = None, source_weight: float = 1.0, detected_at: datetime | None = None) -> OfferEvent:
    client = ShopeeAffiliateClient()
    final_url = await resolve_url(url)
    if not client.configured:
        raise RuntimeError('Configure Shopee antes de processar os links coletados')
    node = await client.get_product(final_url, strict=True)
    if not node:
        raise ValueError('Oferta indisponível na API Shopee')
    if not node:
        identity = extract_identity(final_url)
        if not identity:
            raise ValueError('Não consegui identificar shopId/itemId no link da Shopee')
        node = {'shopId': identity[0], 'itemId': identity[1], 'productName': f'Produto Shopee {identity[1]}', 'productLink': final_url}
    return await ingest_node(db, node, source_type, source_ref, source_message_id, final_url, source_weight, detected_at=detected_at)
