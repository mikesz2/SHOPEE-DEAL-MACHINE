from datetime import datetime, timedelta
from statistics import median
from app.models import PriceSnapshot


def price_evidence(db, product):
    now = datetime.utcnow()
    rows = db.query(PriceSnapshot).filter(
        PriceSnapshot.product_id == product.id,
        PriceSnapshot.captured_at >= now - timedelta(days=30),
        PriceSnapshot.captured_at < now - timedelta(hours=1),
        PriceSnapshot.price > 0).order_by(PriceSnapshot.captured_at).all()
    days = {}
    for row in rows:
        days.setdefault(row.captured_at.date(), []).append(row.price)
    # Daily medians stop a busy source from dominating the reference price.
    if len(days) < 3 or not product.price:
        return {'days': len(days), 'reference': None, 'drop_pct': None,
                'score_adjustment': 0, 'reason': 'Histórico insuficiente: mínimo de 3 dias observados'}
    reference = median([median(values) for values in days.values()])
    drop = (reference - product.price) / reference * 100
    adjustment = min(15, max(-20, drop * 0.6))
    return {'days': len(days), 'reference': round(reference, 2), 'drop_pct': round(drop, 1),
            'score_adjustment': round(adjustment, 1), 'reason': 'Comparação com mediana diária observada em 30 dias; frete e variações não incluídos'}
