import json
import math
import random
import re
from collections import defaultdict
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import Publication, OfferEvent, Product, Source, Conversion

TRACK_RE = re.compile(r'\bp(\d+)\b', re.I)


def source_learning_multiplier(db: Session, source_ref: str | None) -> float:
    if not source_ref:
        return 1.0
    source = db.query(Source).filter(Source.chat_ref == source_ref).one_or_none()
    if not source:
        return 1.0
    return max(0.6, min(float(source.learned_weight or 1.0), 1.8))


def choose_template(db: Session, category: str, allowed: list[str], learning: bool = True) -> str:
    allowed = [x for x in allowed if x in {'default', 'urgente', 'clean'}] or ['default']
    if not learning or len(allowed) == 1:
        return allowed[0]
    cutoff = datetime.utcnow() - timedelta(days=45)
    scored = []
    for template in allowed:
        rows = (db.query(Publication.conversion_count)
                .join(OfferEvent, Publication.offer_event_id == OfferEvent.id)
                .join(Product, OfferEvent.product_id == Product.id)
                .filter(Publication.status == 'published', Publication.published_at >= cutoff,
                        Publication.template_variant == template, Product.category == category)
                .all())
        success = sum(1 for (c,) in rows if (c or 0) > 0)
        failure = max(0, len(rows) - success)
        # Thompson sampling: explora sem abandonar o que já funciona.
        sample = random.betavariate(1 + success, 1 + failure)
        scored.append((sample, template))
    return max(scored)[1]


def smart_interval_minutes(db: Session, base: int, enabled: bool = True) -> int:
    if not enabled:
        return base
    cutoff = datetime.utcnow() - timedelta(days=30)
    rows = (db.query(Publication.published_at, Publication.conversion_count)
            .filter(Publication.status == 'published', Publication.published_at >= cutoff,
                    Publication.published_at.is_not(None)).all())
    if len(rows) < 30:
        return base
    by_hour = defaultdict(lambda: [0, 0])
    for published_at, conversions in rows:
        h = published_at.hour
        by_hour[h][0] += 1
        by_hour[h][1] += 1 if (conversions or 0) > 0 else 0
    total_posts = sum(v[0] for v in by_hour.values())
    total_wins = sum(v[1] for v in by_hour.values())
    avg = total_wins / max(1, total_posts)
    h = datetime.utcnow().hour
    posts, wins = by_hour[h]
    if posts < 5:
        return base
    rate = wins / posts
    if rate >= avg * 1.35 and rate > 0:
        return max(3, round(base * 0.7))
    if rate < avg * 0.65:
        return round(base * 1.25)
    return base


def _extract_publication_id(utm: str | None) -> int | None:
    if not utm:
        return None
    # Shopee pode serializar múltiplos SubIDs de formas diferentes; buscamos nosso token p<ID>.
    m = TRACK_RE.search(str(utm).replace('_', ' ').replace('-', ' '))
    if m:
        return int(m.group(1))
    m = re.search(r'p(\d+)', str(utm), re.I)
    return int(m.group(1)) if m else None


def sync_conversion_nodes(db: Session, nodes: list[dict]) -> dict:
    created = 0
    matched = 0
    touched_publications: set[int] = set()
    for node in nodes:
        cid = str(node.get('conversionId') or '')
        if not cid:
            continue
        conv = db.query(Conversion).filter(Conversion.conversion_id == cid).one_or_none()
        if conv is None:
            conv = Conversion(conversion_id=cid)
            db.add(conv)
            created += 1
        utm = str(node.get('utmContent') or '')
        pub_id = _extract_publication_id(utm)
        publication = db.get(Publication, pub_id) if pub_id else None
        total_commission = 0.0
        try:
            total_commission = float(node.get('totalCommission') or 0)
        except Exception:
            pass
        orders = node.get('orders') or []
        completed = sum(1 for o in orders if str(o.get('orderStatus') or '').upper() == 'COMPLETED')
        conv.publication_id = publication.id if publication else None
        conv.utm_content = utm or None
        try:
            conv.purchase_time = int(node.get('purchaseTime')) if node.get('purchaseTime') is not None else None
        except Exception:
            conv.purchase_time = None
        conv.total_commission = total_commission
        conv.orders_count = len(orders)
        conv.completed_orders = completed
        conv.raw_json = json.dumps(node, ensure_ascii=False)
        conv.synced_at = datetime.utcnow()
        if publication:
            matched += 1
            touched_publications.add(publication.id)
    db.commit()

    for pub_id in touched_publications:
        pub = db.get(Publication, pub_id)
        rows = db.query(Conversion).filter(Conversion.publication_id == pub_id).all()
        pub.conversion_count = len(rows)
        pub.commission_total = sum(float(x.total_commission or 0) for x in rows)
    db.commit()
    refresh_source_learning(db)
    return {'created': created, 'matched': matched, 'total': len(nodes)}


def refresh_source_learning(db: Session):
    sources = db.query(Source).all()
    cutoff = datetime.utcnow() - timedelta(days=45)
    for source in sources:
        pubs = (db.query(Publication)
                .join(OfferEvent, Publication.offer_event_id == OfferEvent.id)
                .filter(OfferEvent.source_ref == source.chat_ref,
                        Publication.status == 'published', Publication.published_at >= cutoff).all())
        wins = sum(1 for p in pubs if (p.conversion_count or 0) > 0)
        commission = sum(float(p.commission_total or 0) for p in pubs)
        rate = wins / max(1, len(pubs))
        # suavização conservadora para não supervalorizar fonte com poucas amostras
        confidence = min(1.0, len(pubs) / 40.0)
        raw = 0.8 + min(0.8, rate * 5.0) + min(0.2, commission / 1000.0)
        source.learned_weight = round((1 - confidence) * 1.0 + confidence * raw, 3)
        source.published_count = len(pubs)
        source.converted_count = wins
        source.commission_total = round(commission, 2)
    db.commit()
