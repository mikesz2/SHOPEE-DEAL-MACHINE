import asyncio
import hashlib
import json
import logging
import random
import re
import time
import httpx
from app.config import settings
from app.services.url_utils import extract_identity, resolve_url

log = logging.getLogger(__name__)


class ShopeeApiError(RuntimeError):
    pass


class ShopeeAffiliateClient:
    def __init__(self):
        self.app_id = settings.shopee_app_id
        self.secret = settings.shopee_secret
        self.url = settings.shopee_api_url

    @property
    def configured(self) -> bool:
        return bool(self.app_id and self.secret)

    async def _graphql(self, query: str, variables: dict | None = None) -> dict:
        if not self.configured:
            raise ShopeeApiError('Credenciais da Shopee não configuradas')
        payload = json.dumps({'query': query, 'variables': variables or {}}, ensure_ascii=False, separators=(',', ':'))
        last_error = None
        for attempt in range(max(1, settings.http_max_retries)):
            ts = int(time.time())
            signature = hashlib.sha256(f'{self.app_id}{ts}{payload}{self.secret}'.encode()).hexdigest()
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'SHA256 Credential={self.app_id}, Timestamp={ts}, Signature={signature}',
            }
            try:
                async with httpx.AsyncClient(timeout=settings.shopee_request_timeout_seconds) as client:
                    resp = await client.post(self.url, content=payload.encode(), headers=headers)
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise ShopeeApiError(f'HTTP {resp.status_code}')
                resp.raise_for_status()
                data = resp.json()
                if data.get('errors'):
                    raise ShopeeApiError(str(data['errors']))
                return data.get('data') or {}
            except Exception as exc:
                last_error = exc
                if attempt + 1 >= max(1, settings.http_max_retries):
                    break
                await asyncio.sleep((2 ** attempt) + random.random())
        raise ShopeeApiError(str(last_error))

    @staticmethod
    def _normalize_subid(value: str | None) -> str:
        raw = re.sub(r'[^A-Za-z0-9]+', '', str(value or ''))
        if not raw:
            return ''
        if not raw[0].isalpha():
            raw = 's' + raw
        return raw[:20]

    @staticmethod
    def _is_invalid_subid_error(exc: Exception) -> bool:
        msg = str(exc).lower()
        return 'invalid sub id' in msg or ('11001' in msg and 'sub' in msg)

    async def generate_short_link(self, origin_url: str, sub_ids: list[str] | None = None) -> str:
        origin_literal = json.dumps(str(origin_url), ensure_ascii=False)
        safe_ids: list[str] = []
        for value in (sub_ids or [])[:5]:
            sid = self._normalize_subid(value)
            if sid and sid not in safe_ids:
                safe_ids.append(sid)

        async def _call(ids: list[str] | None) -> str:
            if ids:
                sub_literal = '[' + ','.join(json.dumps(x, ensure_ascii=True) for x in ids) + ']'
                input_literal = f'{{originUrl: {origin_literal}, subIds: {sub_literal}}}'
            else:
                input_literal = f'{{originUrl: {origin_literal}}}'
            query = f'''
            mutation {{
              generateShortLink(input: {input_literal}) {{ shortLink }}
            }}
            '''
            data = await self._graphql(query)
            return data['generateShortLink']['shortLink']

        try:
            return await _call(safe_ids)
        except Exception as exc:
            if not self._is_invalid_subid_error(exc):
                raise
            log.warning('Shopee rejeitou SubIDs %s; tentando fallback', safe_ids)

        tracking_only: list[str] = []
        if len(safe_ids) >= 3:
            tracking_only = [safe_ids[2]]
        elif safe_ids:
            tracking_only = [safe_ids[-1]]
        if tracking_only:
            try:
                return await _call(tracking_only)
            except Exception as exc:
                if not self._is_invalid_subid_error(exc):
                    raise
                log.warning('Shopee rejeitou tracking SubID %s; gerando sem SubID', tracking_only)

        return await _call(None)

    async def search_products(self, keyword: str | None = None, page: int = 1, limit: int = 10) -> list[dict]:
        query = '''
        query ProductOfferV2($keyword: String, $page: Int, $limit: Int) {
          productOfferV2(keyword: $keyword, page: $page, limit: $limit) {
            nodes {
              itemId shopId productName shopName imageUrl productLink offerLink
              priceMin priceMax priceDiscountRate ratingStar sales
              commissionRate sellerCommissionRate shopeeCommissionRate commission
              periodStartTime periodEndTime
            }
            pageInfo { page limit hasNextPage }
          }
        }
        '''
        data = await self._graphql(query, {'keyword': keyword, 'page': page, 'limit': limit})
        return (data.get('productOfferV2') or {}).get('nodes') or []

    async def get_product(self, url: str, strict: bool = False) -> dict | None:
        final_url = await resolve_url(url)
        identity = extract_identity(final_url)
        if not identity:
            return None
        shop_id, item_id = identity
        # Nao declare shopId/itemId como variaveis Int64. O endpoint BR
        # pode devolver code 10010 / wrong type nessa forma. IDs vindos da
        # URL sao validados como digitos e enviados como literais numericos.
        if not str(shop_id).isdigit() or not str(item_id).isdigit():
            return None if strict else {'shopId': shop_id, 'itemId': item_id, 'productName': f'Produto Shopee {item_id}', 'productLink': final_url}
        query = f'''
        query ProductOfferV2 {{
          productOfferV2(itemId: {int(item_id)}, shopId: {int(shop_id)}, page: 1, limit: 10) {{
            nodes {{
              itemId shopId productName shopName imageUrl productLink offerLink
              priceMin priceMax priceDiscountRate ratingStar sales
              commissionRate sellerCommissionRate shopeeCommissionRate commission
              periodStartTime periodEndTime
            }}
          }}
        }}
        '''
        try:
            data = await self._graphql(query)
            nodes = (data.get('productOfferV2') or {}).get('nodes') or []
            if nodes:
                node = nodes[0]
                node['resolvedUrl'] = final_url
                return node
            return None if strict else {'shopId': shop_id, 'itemId': item_id, 'productName': f'Produto Shopee {item_id}', 'productLink': final_url}
        except Exception:
            if strict:
                raise
            return {'shopId': shop_id, 'itemId': item_id, 'productName': f'Produto Shopee {item_id}', 'productLink': final_url}

    async def get_conversions(self, days: int = 7, limit: int = 200) -> list[dict]:
        now = int(time.time())
        start = now - max(1, min(days, 90)) * 86400
        query = '''
        query ConversionReport($start: Int64, $end: Int64, $limit: Int) {
          conversionReport(purchaseTimeStart: $start, purchaseTimeEnd: $end, limit: $limit) {
            nodes {
              purchaseTime clickTime conversionId totalCommission buyerType device utmContent
              orders {
                orderId orderStatus
                items { itemId itemName shopName itemPrice qty itemTotalCommission attributionType }
              }
            }
            pageInfo { limit hasNextPage scrollId }
          }
        }
        '''
        data = await self._graphql(query, {'start': start, 'end': now, 'limit': min(limit, 500)})
        return (data.get('conversionReport') or {}).get('nodes') or []
