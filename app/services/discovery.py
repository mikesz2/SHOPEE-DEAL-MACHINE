"""Deterministic discovery: bounded expansion, relevance and diverse ranking."""
import math
from collections import Counter
from types import SimpleNamespace
from app.services.product_utils import normalize_name, token_set, csv_items
from app.services.filters import blocked_reason
from app.services.scoring import deal_score

# These are search terms, never fabricated product data.
FAMILIES = {
    'eletronicos': ['fone bluetooth', 'smartwatch', 'caixa de som'],
    'casa': ['organizador', 'luminaria', 'jogo de lençol'],
    'cozinha': ['air fryer', 'panela', 'cafeteira'],
    'beleza': ['secador', 'maquiagem', 'skincare'],
    'gamer': ['mouse gamer', 'teclado mecanico', 'headset'],
    'celular': ['smartphone', 'carregador', 'power bank'],
    'ferramentas': ['parafusadeira', 'furadeira', 'jogo de ferramentas'],
}


def query_plan(keywords, expand=True, rotation=0):
    base = list(dict.fromkeys(k.strip() for k in keywords.split(',') if k.strip()))[:24]
    # Give every configured topic its first pass before any expansion.
    plan = [(k, k) for k in base]
    if expand:
        for k in base:
            family = FAMILIES.get(normalize_name(k))
            if family:
                plan.append((family[rotation % len(family)], k))
    return list(dict.fromkeys(plan))


def number(value, default=0):
    try:
        n = float(value)
        return n if math.isfinite(n) else default
    except (ValueError, TypeError):
        return default


def percent(value):
    n = number(value)
    return n * 100 if 0 <= n <= 1 else n


def relevance(name, query):
    name_tokens, query_tokens = token_set(name), token_set(query)
    if not query_tokens:
        return 0
    direct = len(name_tokens & query_tokens) / len(query_tokens)
    family = FAMILIES.get(normalize_name(query), [])
    expanded = max((len(name_tokens & token_set(k)) / max(1, len(token_set(k))) for k in family), default=0)
    return max(direct, expanded)


def evaluate(node, query, runtime, now):
    if not all(str(node.get(k) or '').isdigit() and int(node[k]) > 0 for k in ('shopId', 'itemId')):
        return None, 'identidade inválida'
    for key in ('priceMin', 'ratingStar', 'sales', 'commissionRate', 'priceDiscountRate'):
        if node.get(key) is not None and number(node[key], None) is None:
            return None, 'dados numéricos inválidos'
    end, start = number(node.get('periodEndTime')), number(node.get('periodStartTime'))
    if (end > 0 and end <= now) or start > now:
        return None, 'fora do período da oferta'
    product = SimpleNamespace(
        name=str(node.get('productName') or ''), shop_id=str(node['shopId']),
        price=number(node.get('priceMin')), rating=number(node.get('ratingStar')) if node.get('ratingStar') is not None else None,
        sales=number(node.get('sales')) if node.get('sales') is not None else None,
        commission_rate=percent(node['commissionRate']) if node.get('commissionRate') is not None else None,
        discount_rate=percent(node['priceDiscountRate']) if node.get('priceDiscountRate') is not None else None)
    reason = blocked_reason(product, runtime)
    if reason:
        return None, reason
    rel = relevance(product.name, query)
    if rel < 0.5:
        return None, 'resultado pouco relacionado à busca'
    quality = deal_score(node)
    # Log sales recognize emerging products without requiring thousands of sales.
    demand = min(1, math.log1p(max(0, product.sales or 0)) / math.log1p(7000))
    rating = max(0, min(1, ((product.rating or 0) - 3.5) / 1.5))
    boost = 3 if any(t in normalize_name(product.name) for t in csv_items(runtime.priority_keywords)) else 0
    rank = quality * .60 + rel * 20 + demand * 10 + rating * 10 + boost
    return round(min(100, rank), 1), None


def diverse_order(candidates, shop_limit):
    """Round-robin topics; best score inside each; cap stores across the run."""
    buckets = {}
    for candidate in sorted(candidates, key=lambda c: (-c['rank'], c['identity'])):
        buckets.setdefault(candidate['topic'], []).append(candidate)
    shops = Counter()
    while any(buckets.values()):
        for bucket in buckets.values():
            while bucket:
                candidate = bucket.pop(0)
                shop = candidate['identity'][0]
                if shops[shop] < shop_limit:
                    shops[shop] += 1
                    yield candidate
                    break
