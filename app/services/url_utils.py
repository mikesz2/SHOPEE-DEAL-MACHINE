import re
import ipaddress
import socket
import httpx
from urllib.parse import urlparse, parse_qs

URL_RE = re.compile(r'https?://[^\s<>()]+', re.I)
ALLOWED_SHOPEE_SUFFIXES = ('shopee.com.br', 's.shopee.com.br', 'shope.ee', 'shopee.com')


def _host_allowed(host: str | None) -> bool:
    host = (host or '').lower().strip('.')
    return any(host == x or host.endswith('.' + x) for x in ALLOWED_SHOPEE_SUFFIXES)


def is_safe_shopee_url(url: str) -> bool:
    try:
        p = urlparse(url)
        return p.scheme in {'http', 'https'} and _host_allowed(p.hostname)
    except Exception:
        return False


def extract_urls(text: str) -> list[str]:
    urls = [u.rstrip('.,!?)]}') for u in URL_RE.findall(text or '')]
    out = []
    for u in urls:
        if is_safe_shopee_url(u) and u not in out:
            out.append(u)
    return out


def extract_identity(url: str) -> tuple[str, str] | None:
    patterns = [r'/product/(\d+)/(\d+)', r'-i\.(\d+)\.(\d+)', r'/opaanlp/(\d+)/(\d+)']
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1), m.group(2)
    parsed = urlparse(url)
    qs = {k.lower(): v for k, v in parse_qs(parsed.query).items()}
    shop = (qs.get('shopid') or qs.get('shop_id') or [None])[0]
    item = (qs.get('itemid') or qs.get('item_id') or [None])[0]
    if shop and item:
        return str(shop), str(item)
    return None


async def resolve_url(url: str) -> str:
    if not is_safe_shopee_url(url):
        raise ValueError('URL fora dos domínios permitidos da Shopee')
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=12.0, headers={'User-Agent': 'Mozilla/5.0'}) as client:
            r = await client.get(url)
            final = str(r.url)
            if not is_safe_shopee_url(final):
                raise ValueError('Redirecionamento saiu dos domínios da Shopee')
            return final
    except ValueError:
        raise
    except Exception:
        return url
