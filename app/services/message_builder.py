import html


def money(v):
    if v is None:
        return None
    try:
        return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return None


def normalize_pct(v):
    if v is None:
        return 0.0
    try:
        v = float(v)
    except Exception:
        return 0.0
    return v * 100 if 0 <= v <= 1 else v


def estimated_original(price, discount):
    try:
        p = float(price)
        d = normalize_pct(discount)
        if 0 < d < 100:
            return p / (1 - d / 100)
    except Exception:
        pass
    return None


def _facts(product):
    raw_name = str(product.get("productName") or product.get("name") or "Oferta Shopee").strip()
    if len(raw_name) > 180:
        raw_name = raw_name[:177].rstrip() + "..."
    name = html.escape(raw_name, quote=False)

    price = product.get("priceMin") if product.get("priceMin") is not None else product.get("price")
    discount = product.get("priceDiscountRate") if product.get("priceDiscountRate") is not None else product.get("discount_rate")
    original = product.get("original_price")

    # Only use a real original price supplied by the source. Never invent a "DE"
    # price just to make the message look better.
    try:
        if original is not None and price is not None and float(original) <= float(price):
            original = None
    except Exception:
        original = None

    rating = product.get("ratingStar") if product.get("ratingStar") is not None else product.get("rating")
    sales = product.get("sales")
    return name, price, normalize_pct(discount), original, rating, sales


def _social_proof(rating, sales):
    parts = []
    if rating:
        try:
            parts.append(f"⭐ {float(rating):.1f}/5")
        except Exception:
            pass
    if sales:
        try:
            parts.append(f"🛒 {int(float(sales)):,} vendidos".replace(",", "."))
        except Exception:
            pass
    return " • ".join(parts)


def build_offer_caption(product, affiliate_url: str, score: float, source_type: str, style: str = "default") -> str:
    name, price, discount, original, rating, sales = _facts(product)
    safe_url = html.escape(str(affiliate_url or ""), quote=False)
    social_proof = _social_proof(rating, sales)

    # Main format: more commercial, scannable and similar to the proven old layout.
    # Keep the strongest information near the top and avoid fake reference prices.
    lines = ["🔥 <b>OFERTA BOA ❤️</b>", "", f"🛍️ <b>{name}</b>", ""]

    if original and price:
        lines.append(f"❌ DE: <s>{money(original)}</s>")
        lines.append(f"✅ POR: <b>{money(price)}</b>")
    elif price:
        lines.append(f"✅ POR: <b>{money(price)}</b>")

    if discount > 0:
        lines.append(f"💥 <b>{discount:.0f}% OFF</b>")

    if social_proof:
        lines += ["", social_proof]

    lines += [
        "",
        "🛒 <b>COMPRAR NA SHOPEE:</b>",
        safe_url,
        "",
        "⚠️ Preço, estoque e cupom podem mudar a qualquer momento.",
    ]

    return "\n".join(lines)
