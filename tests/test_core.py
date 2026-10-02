from app.services.url_utils import extract_identity, extract_urls, is_safe_shopee_url
from app.services.scoring import deal_score, trend_score, combined_score
from app.services.message_builder import build_offer_caption
from app.services.product_utils import categorize, name_similarity
from app.services.analytics import _extract_publication_id


def test_identity_slug():
    assert extract_identity('https://shopee.com.br/Produto-X-i.12345.98765') == ('12345', '98765')


def test_identity_product():
    assert extract_identity('https://shopee.com.br/product/12345/98765') == ('12345', '98765')


def test_extract_urls_only_shopee():
    x = extract_urls('olha https://s.shopee.com.br/abc e https://google.com')
    assert x == ['https://s.shopee.com.br/abc']
    assert not is_safe_shopee_url('http://127.0.0.1/private')


def test_score_bounds():
    s = deal_score({'priceMin': 99, 'priceDiscountRate': 50, 'ratingStar': 4.9, 'sales': 10000, 'commissionRate': 0.2}, source_hits=4)
    assert 65 <= s <= 100


def test_trend_score_rises_with_velocity():
    assert trend_score(4, 5, 6, 10) > trend_score(1, 1, 1, 1)
    assert 0 <= combined_score(80, 70) <= 100


def test_caption_has_affiliate_link():
    c = build_offer_caption({'productName':'Teste','priceMin':49.9,'priceDiscountRate':25,'ratingStar':4.8,'sales':1000}, 'https://s.shopee.com.br/meu', 80, 'manual')
    assert 'https://s.shopee.com.br/meu' in c
    assert 'Teste' in c


def test_category_and_similarity():
    assert categorize('Fone Bluetooth Lenovo GM2 Pro') in {'eletronicos','gamer'}
    assert name_similarity('Fone Lenovo GM2 Pro Bluetooth', 'Fone Bluetooth Lenovo GM2 Pro') > 0.7
    assert name_similarity('Fone Lenovo GM2', 'Panela de pressão inox') < 0.3


def test_tracking_parse():
    assert _extract_publication_id('src_canal,p123,clean') == 123
    assert _extract_publication_id('foo-p987-bar') == 987


def test_caption_long_name_keeps_html_balanced_and_escapes_url():
    name = '<Produto & Especial> ' + ('X' * 500)
    c = build_offer_caption({'productName': name, 'priceMin': 10}, 'https://s.shopee.com.br/a?x=1&y=2', 80, 'manual')
    assert '<Produto' not in c
    assert '&lt;Produto &amp; Especial&gt;' in c
    assert 'x=1&amp;y=2' in c
    assert c.count('<b>') == c.count('</b>')
    assert len(c) < 1024


def test_shopee_product_lookup_uses_literal_ids(monkeypatch):
    import asyncio
    from app.services import shopee as shopee_mod
    client = shopee_mod.ShopeeAffiliateClient()
    async def fake_resolve(url):
        return url
    seen = {}
    async def fake_graphql(query, variables=None):
        seen['query'] = query
        seen['variables'] = variables
        return {'productOfferV2': {'nodes': [{'shopId':'12345','itemId':'9876543210','productName':'Teste','productLink':'https://shopee.com.br/product/12345/9876543210'}]}}
    monkeypatch.setattr(shopee_mod, 'resolve_url', fake_resolve)
    monkeypatch.setattr(client, '_graphql', fake_graphql)
    node = asyncio.run(client.get_product('https://shopee.com.br/product/12345/9876543210', strict=True))
    assert node['itemId'] == '9876543210'
    assert 'itemId: 9876543210' in seen['query']
    assert 'shopId: 12345' in seen['query']
    assert seen['variables'] is None


def test_shopee_short_link_uses_literal_input(monkeypatch):
    import asyncio
    from app.services.shopee import ShopeeAffiliateClient
    client = ShopeeAffiliateClient()
    seen = {}
    async def fake_graphql(query, variables=None):
        seen['query'] = query
        seen['variables'] = variables
        return {'generateShortLink': {'shortLink': 'https://s.shopee.com.br/teste'}}
    monkeypatch.setattr(client, '_graphql', fake_graphql)
    link = asyncio.run(client.generate_short_link('https://shopee.com.br/a?x=1&y=2', ['telegram','p123']))
    assert link.endswith('/teste')
    assert 'originUrl: "https://shopee.com.br/a?x=1&y=2"' in seen['query']
    assert 'subIds: ["telegram","p123"]' in seen['query']
    assert seen['variables'] is None


def test_subid_normalization_is_strict_alphanumeric():
    from app.services.shopee import ShopeeAffiliateClient
    assert ShopeeAffiliateClient._normalize_subid('@canal_com-oferta') == 'canalcomoferta'
    assert ShopeeAffiliateClient._normalize_subid('123') == 's123'
    assert ShopeeAffiliateClient._normalize_subid('çã🔥') == ''
    assert len(ShopeeAffiliateClient._normalize_subid('a' * 100)) == 20


def test_short_link_falls_back_on_invalid_subid(monkeypatch):
    import asyncio
    from app.services.shopee import ShopeeAffiliateClient, ShopeeApiError
    client = ShopeeAffiliateClient()
    seen = []
    async def fake_graphql(query, variables=None):
        seen.append(query)
        if len(seen) < 3:
            raise ShopeeApiError("error [11001]: Params Error : invalid sub id")
        return {'generateShortLink': {'shortLink': 'https://s.shopee.com.br/fallback'}}
    monkeypatch.setattr(client, '_graphql', fake_graphql)
    link = asyncio.run(client.generate_short_link('https://shopee.com.br/produto', ['shopee_radar','@canal_x','p123','casa & decoracao','urgent']))
    assert link.endswith('/fallback')
    assert 'subIds: ["shopeeradar","canalx","p123","casadecoracao","urgent"]' in seen[0]
    assert 'subIds: ["p123"]' in seen[1]
    assert 'subIds:' not in seen[2]


def test_conversion_report_uses_int64_timestamps(monkeypatch):
    import asyncio
    from app.services.shopee import ShopeeAffiliateClient
    client = ShopeeAffiliateClient()
    seen = {}
    async def fake_graphql(query, variables=None):
        seen['query'] = query
        seen['variables'] = variables
        return {'conversionReport': {'nodes': []}}
    monkeypatch.setattr(client, '_graphql', fake_graphql)
    rows = asyncio.run(client.get_conversions(days=7, limit=200))
    assert rows == []
    assert '$start: Int64' in seen['query']
    assert '$end: Int64' in seen['query']
    assert '$limit: Int' in seen['query']
    assert isinstance(seen['variables']['start'], int)
    assert isinstance(seen['variables']['end'], int)


def test_telegram_ipc_queue_and_pending(tmp_path, monkeypatch):
    from app.services import telegram_ipc
    req = tmp_path / 'requests'
    res = tmp_path / 'responses'
    monkeypatch.setattr(telegram_ipc, 'REQUESTS', req)
    monkeypatch.setattr(telegram_ipc, 'RESPONSES', res)
    job = telegram_ipc.queue_command('test_source', {'source_id': 1})
    assert (req / f'{job}.json').exists()
    assert telegram_ipc.read_result(job)['status'] == 'pending'
    res.mkdir(parents=True, exist_ok=True)
    (res / f'{job}.json').write_text('{"ok":true,"result":{"accessible":true}}', encoding='utf-8')
    out = telegram_ipc.read_result(job)
    assert out['status'] == 'done'
    assert out['ok'] is True


def test_v7_frontend_has_radar_and_operations():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    html = (root / 'app' / 'static' / 'index.html').read_text(encoding='utf-8')
    js = (root / 'app' / 'static' / 'app.js').read_text(encoding='utf-8')
    assert 'Deal Machine' in html
    assert 'Radar Telegram' in html
    assert 'Importar' in js
    assert '/import-history' in js
    assert '/api/telegram/jobs/' in js
    assert '/api/dashboard' in js
    assert '/api/offers/bulk' in js


def test_v5_enterprise_runtime_guardrails_exist():
    from app.schemas import RuntimeSettings
    r = RuntimeSettings()
    assert r.max_queue_depth >= r.alert_queue_depth
    assert r.circuit_breaker_failures >= 2
    assert r.audit_retention_days >= 30


def test_v5_audit_event_model_present():
    from app.models import AuditEvent
    assert AuditEvent.__tablename__ == 'audit_events'
