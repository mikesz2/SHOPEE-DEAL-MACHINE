"""Massive, category-driven product discovery.

The UI still receives simple categories. Internally the radar expands them into
many semantic queries and several API sort modes, while keeping identity,
quality and store diversity under control.
"""
import math
import re
from collections import Counter
from types import SimpleNamespace

from app.services.product_utils import normalize_name, token_set, csv_items
from app.services.filters import blocked_reason
from app.services.scoring import deal_score


CATEGORY_UNIVERSE = {
    "eletronicos": {
        "roots": ["fone", "headset", "smartwatch", "caixa de som", "carregador", "power bank", "projetor", "tablet", "celular"],
        "attributes": ["bluetooth", "sem fio", "usb", "portatil", "digital", "inteligente", "original", "rapido", "compacto"],
        "intent": ["promocao", "oferta", "barato", "custo beneficio", "kit"],
    },
    "casa": {
        "roots": ["organizador", "luminaria", "lampada", "tapete", "cortina", "almofada", "lençol", "toalha", "decoracao", "varal", "cabide"],
        "attributes": ["grande", "pequeno", "modular", "dobravel", "multiuso", "resistente", "decorativo", "moderno", "kit"],
        "intent": ["promocao", "oferta", "barato", "achadinho", "custo beneficio"],
    },
    "cozinha": {
        "roots": ["air fryer", "fritadeira", "panela", "panela eletrica", "pote", "organizador cozinha", "liquidificador", "cafeteira", "forma", "escorredor", "garrafa", "copo termico", "utensilios", "moedor", "processador"],
        "attributes": ["antiaderente", "eletrica", "inox", "silicone", "hermetico", "termico", "grande", "pequeno", "5 litros", "4 litros", "kit", "profissional"],
        "intent": ["promocao", "oferta", "barato", "achadinho", "custo beneficio", "kit"],
    },
    "beleza": {
        "roots": ["secador", "chapinha", "escova", "maquiagem", "skin care", "creme", "perfume", "modelador", "depilador", "unhas"],
        "attributes": ["profissional", "eletrico", "portatil", "kit", "original", "compacto", "bivolt"],
        "intent": ["promocao", "oferta", "barato", "achadinho"],
    },
    "gamer": {
        "roots": ["mouse gamer", "teclado mecanico", "headset gamer", "controle", "mousepad", "suporte monitor", "cadeira gamer", "microfone gamer", "webcam"],
        "attributes": ["rgb", "sem fio", "mecanico", "ergonomico", "wireless", "usb", "60", "65", "75"],
        "intent": ["promocao", "oferta", "barato", "kit", "custo beneficio"],
    },
    "celular": {
        "roots": ["smartphone", "celular", "capinha", "pelicula", "carregador", "cabo usb", "power bank", "suporte celular", "fone bluetooth"],
        "attributes": ["rapido", "turbo", "20w", "25w", "65w", "usb c", "magnetico", "anti impacto", "original"],
        "intent": ["promocao", "oferta", "barato", "kit", "achadinho"],
    },
    "ferramentas": {
        "roots": ["parafusadeira", "furadeira", "jogo de ferramentas", "chave", "alicate", "serra", "broca", "compressor", "multimetro", "caixa ferramentas"],
        "attributes": ["eletrica", "sem fio", "profissional", "12v", "20v", "21v", "kit", "inox", "resistente"],
        "intent": ["promocao", "oferta", "barato", "kit", "custo beneficio"],
    },
    "moda": {
        "roots": ["camiseta", "camisa", "calca", "bermuda", "vestido", "tenis", "sandalia", "bolsa", "mochila", "conjunto"],
        "attributes": ["feminino", "masculino", "casual", "esportivo", "oversized", "confortavel", "slim", "kit"],
        "intent": ["promocao", "oferta", "barato", "achadinho"],
    },
}

# Fallback keeps legacy custom keywords working.
LEGACY = {
    "eletronicos": ["fone bluetooth", "smartwatch", "caixa de som"],
    "casa": ["organizador", "luminaria", "jogo de lençol"],
    "cozinha": ["air fryer", "panela", "cafeteira"],
    "beleza": ["secador", "maquiagem", "skincare"],
    "gamer": ["mouse gamer", "teclado mecanico", "headset"],
    "celular": ["smartphone", "carregador", "power bank"],
    "ferramentas": ["parafusadeira", "furadeira", "jogo de ferramentas"],
}


def _clean(value):
    return re.sub(r"\s+", " ", normalize_name(value)).strip()


def _category_matrix(category):
    data = CATEGORY_UNIVERSE.get(_clean(category))
    if not data:
        return [_clean(category)]
    roots = data["roots"]
    queries = list(roots)
    # High-yield combinations without exploding into every possible permutation.
    for root in roots:
        for attr in data["attributes"][:6]:
            queries.append(f"{root} {attr}")
    for root in roots[:10]:
        for intent in data["intent"][:4]:
            queries.append(f"{root} {intent}")
    return list(dict.fromkeys(_clean(q) for q in queries if q))


def query_plan(keywords, expand=True, rotation=0):
    seeds = list(dict.fromkeys(_clean(k) for k in (keywords or "").split(",") if _clean(k)))
    plan = []
    for seed in seeds:
        family = _category_matrix(seed) if seed in CATEGORY_UNIVERSE else LEGACY.get(seed, [seed])
        plan.extend((q, seed) for q in family)
        if expand and seed in CATEGORY_UNIVERSE:
            # A few broad family terms improve discovery of products whose title
            # doesn't contain the exact root selected by the user.
            plan.extend((q, seed) for q in LEGACY.get(seed, []))
    unique = list(dict.fromkeys(plan))
    if not unique:
        return []
    offset = rotation % len(unique)
    return unique[offset:] + unique[:offset]


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
    # A single exact root is enough for broad discovery; stricter quality rules
    # happen later. This avoids throwing away legitimate long-tail products.
    if direct > 0:
        return max(direct, min(1.0, direct + 0.25))
    return 0


def evaluate(node, query, runtime, now):
    if not all(str(node.get(k) or "").isdigit() and int(node[k]) > 0 for k in ("shopId", "itemId")):
        return None, "identidade inválida"
    for key in ("priceMin", "ratingStar", "sales", "commissionRate", "priceDiscountRate"):
        if node.get(key) is not None and number(node[key], None) is None:
            return None, "dados numéricos inválidos"
    end, start = number(node.get("periodEndTime")), number(node.get("periodStartTime"))
    if (end > 0 and end <= now) or start > now:
        return None, "fora do período da oferta"
    product = SimpleNamespace(
        name=str(node.get("productName") or ""),
        shop_id=str(node["shopId"]),
        price=number(node.get("priceMin")),
        rating=number(node.get("ratingStar")) if node.get("ratingStar") is not None else None,
        sales=number(node.get("sales")) if node.get("sales") is not None else None,
        commission_rate=percent(node["commissionRate"]) if node.get("commissionRate") is not None else None,
        discount_rate=percent(node["priceDiscountRate"]) if node.get("priceDiscountRate") is not None else None,
    )
    reason = blocked_reason(product, runtime)
    if reason:
        return None, reason
    rel = relevance(product.name, query)
    if rel <= 0:
        return None, "resultado pouco relacionado à busca"
    quality = deal_score(node)
    demand = min(1, math.log1p(max(0, product.sales or 0)) / math.log1p(7000))
    rating = max(0, min(1, ((product.rating or 0) - 3.5) / 1.5))
    boost = 3 if any(t in _clean(product.name) for t in csv_items(runtime.priority_keywords)) else 0
    # Novelty is intentionally rewarded later in radar; this score is quality-first.
    rank = quality * .60 + rel * 20 + demand * 10 + rating * 10 + boost
    return round(min(100, rank), 1), None


def diverse_order(candidates, shop_limit):
    """Round-robin topics, preferring quality but forcing store diversity."""
    buckets = {}
    for candidate in sorted(candidates, key=lambda c: (-c["rank"], c["identity"])):
        buckets.setdefault(candidate["topic"], []).append(candidate)
    shops = Counter()
    yielded = set()
    while any(buckets.values()):
        progressed = False
        for bucket in buckets.values():
            while bucket:
                candidate = bucket.pop(0)
                shop = candidate["identity"][0]
                if shops[shop] < shop_limit and candidate["identity"] not in yielded:
                    shops[shop] += 1
                    yielded.add(candidate["identity"])
                    yield candidate
                    progressed = True
                    break
        if not progressed:
            # If every remaining candidate belongs to already saturated stores,
            # release the hard diversity barrier instead of returning zero offers.
            for bucket in buckets.values():
                while bucket:
                    candidate = bucket.pop(0)
                    if candidate["identity"] not in yielded:
                        yielded.add(candidate["identity"])
                        yield candidate
            break
