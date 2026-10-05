"""Persistent novelty and exploration intelligence for the radar."""
from datetime import datetime, timedelta
from sqlalchemy import func
from app.models import DiscoveryMemory, Product, Publication, OfferEvent

def remember(db, product, query, sort_type=1, base_score=0):
    row = db.query(DiscoveryMemory).filter_by(product_id=product.id).one_or_none()
    now = datetime.utcnow()
    if not row:
        row = DiscoveryMemory(product_id=product.id, first_seen_at=now, last_seen_at=now,
                              times_seen=1, query_hits=1, unique_queries=1, unique_sorts=1,
                              novelty_score=100, best_score=float(base_score or 0),
                              last_query=query, last_sort=sort_type)
        db.add(row)
    else:
        old_query, old_sort = row.last_query, row.last_sort
        row.last_seen_at, row.times_seen, row.query_hits = now, row.times_seen + 1, row.query_hits + 1
        row.unique_queries += int(old_query != query)
        row.unique_sorts += int(old_sort != sort_type)
        row.novelty_score = max(0, min(100, 100 - (row.times_seen - 1) * 4 + min(12, row.unique_queries)))
        row.best_score = max(row.best_score or 0, float(base_score or 0))
        row.last_query, row.last_sort = query, sort_type
    return row

def novelty_bonus(db, product_id):
    row = db.query(DiscoveryMemory).filter_by(product_id=product_id).one_or_none()
    if not row:
        return 25.0
    age_hours = max(0, (datetime.utcnow() - row.first_seen_at).total_seconds() / 3600)
    recency = max(0, 20 - row.times_seen * 3)
    return min(25.0, (row.novelty_score or 0) * 0.18 + min(5, age_hours / 24))

def publication_penalty(db, product_id):
    cutoff = datetime.utcnow() - timedelta(days=30)
    published = (db.query(Publication).join(OfferEvent)
                 .filter(OfferEvent.product_id == product_id, Publication.status == 'published',
                         Publication.published_at >= cutoff).count())
    return min(45.0, published * 25.0)

def discovery_priority(db, product_id, base_score):
    return max(0.0, min(100.0, float(base_score) + novelty_bonus(db, product_id) - publication_penalty(db, product_id)))
