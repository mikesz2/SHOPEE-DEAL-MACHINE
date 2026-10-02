def _pct(value):
    if value is None:
        return 0.0
    v = float(value)
    return v * 100 if 0 <= v <= 1 else v


def trend_score(distinct_sources_10m: int = 0, distinct_sources_30m: int = 0, hits_10m: int = 0, hits_30m: int = 0) -> float:
    score = 0.0
    score += min(distinct_sources_10m / 4.0, 1.0) * 40
    score += min(distinct_sources_30m / 6.0, 1.0) * 20
    score += min(hits_10m / 6.0, 1.0) * 25
    score += min(hits_30m / 12.0, 1.0) * 15
    return round(min(score, 100), 1)


def deal_score(product: dict, source_hits: int = 1, source_weight: float = 1.0, priority_boost: float = 0.0) -> float:
    discount = max(0.0, min(_pct(product.get('priceDiscountRate') or product.get('discount_rate')), 100.0))
    rating = float(product.get('ratingStar') or product.get('rating') or 0)
    sales = int(float(product.get('sales') or 0))
    commission_rate = _pct(product.get('commissionRate') or product.get('commission_rate'))
    price = float(product.get('priceMin') or product.get('price') or 0)
    commission_value = product.get('commission')
    try:
        commission_value = float(commission_value) if commission_value is not None else price * commission_rate / 100
    except Exception:
        commission_value = 0

    score = 0.0
    score += min(discount / 55.0, 1.0) * 23
    score += min(sales / 7000.0, 1.0) * 14
    score += max(0.0, min((rating - 3.8) / 1.2, 1.0)) * 10
    score += min(commission_rate / 20.0, 1.0) * 17
    score += min(commission_value / 30.0, 1.0) * 8
    score += min(max(source_hits - 1, 0) / 3.0, 1.0) * 8
    score += min(max(source_weight, 0.1) / 2.0, 1.0) * 8
    if 15 <= price <= 300:
        score += 8
    elif 0 < price <= 800:
        score += 5
    score += max(0.0, min(priority_boost, 4.0))
    return round(min(score, 100.0), 1)


def combined_score(deal: float, trend: float) -> float:
    # Tendência ajuda, mas não deixa um produto ruim virar ótimo sozinho.
    return round(min(100.0, deal * 0.78 + trend * 0.22), 1)
