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
    v = float(v)
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
    # Avoid oversized Telegram captions and, importantly, never truncate an HTML tag mid-way.
    if len(raw_name) > 180:
        raw_name = raw_name[:177].rstrip() + "..."
    name = html.escape(raw_name, quote=False)
    price = product.get("priceMin") if product.get("priceMin") is not None else product.get("price")
    discount = product.get("priceDiscountRate") if product.get("priceDiscountRate") is not None else product.get("discount_rate")
    original = product.get("original_price")
    rating = product.get("ratingStar") if product.get("ratingStar") is not None else product.get("rating")
    sales = product.get("sales")
    return name, price, normalize_pct(discount), original, rating, sales


def build_offer_caption(product, affiliate_url: str, score: float, source_type: str, style: str = "default") -> str:
    name, price, d, original, rating, sales = _facts(product)
    safe_url = html.escape(str(affiliate_url or ""), quote=False)
    if style == "clean":
        lines = [f"🛍️ <b>{name}</b>"]
        if price: lines.append(f"💰 <b>{money(price)}</b>")
        if d: lines.append(f"🏷️ {d:.0f}% de desconto")
        extras = []
        if rating: extras.append(f"⭐ {float(rating):.1f}")
        if sales: extras.append(f"🛒 {int(float(sales)):,} vendidos".replace(",", "."))
        if extras: lines.append(" • ".join(extras))
        lines += ["", "👉 <b>Ver na Shopee:</b>", safe_url, "", "⚠️ Oferta sujeita a alteração."]
    elif style == "urgente":
        lines = ["🚨 <b>CORRE QUE PODE ACABAR!</b>", "", f"🔥 <b>{name}</b>"]
        if original and price and float(original) > float(price): lines.append(f"❌ Era <s>{money(original)}</s>")
        if price: lines.append(f"✅ AGORA: <b>{money(price)}</b>")
        if d: lines.append(f"💥 <b>{d:.0f}% OFF</b>")
        if rating or sales:
            info=[]
            if rating: info.append(f"⭐ {float(rating):.1f}/5")
            if sales: info.append(f"🛒 {int(float(sales)):,} vendidos".replace(",", "."))
            lines += ["", " • ".join(info)]
        lines += ["", "👇 <b>PEGAR ANTES QUE MUDE:</b>", safe_url, "", "⚠️ Preço/estoque podem mudar sem aviso."]
    else:
        lines = ["🔥 <b>OFERTA ENCONTRADA!</b>", "", f"🛍️ <b>{name}</b>"]
        if original and price and float(original) > float(price): lines.append(f"❌ De: <s>{money(original)}</s>")
        if price: lines.append(f"✅ Por: <b>{money(price)}</b>")
        if d: lines.append(f"💥 <b>{d:.0f}% OFF</b>")
        extras = []
        if rating: extras.append(f"⭐ {float(rating):.1f}/5")
        if sales: extras.append(f"🛒 {int(float(sales)):,} vendidos".replace(",", "."))
        if extras: lines.extend(["", " • ".join(extras)])
        lines.extend(["", "👇 <b>PEGAR A OFERTA:</b>", safe_url, "", "⚠️ Preço, estoque e cupom podem mudar a qualquer momento."])
    # With the capped name this stays well below sendPhoto's 1024-char caption limit.
    return "\n".join(lines)
