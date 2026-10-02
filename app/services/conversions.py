from sqlalchemy.orm import Session
from app.services.shopee import ShopeeAffiliateClient
from app.services.analytics import sync_conversion_nodes
from app.services.redis_store import distributed_lock


async def sync_conversions(db: Session, days: int = 30) -> dict:
    client = ShopeeAffiliateClient()
    if not client.configured:
        return {'ok': False, 'reason': 'Shopee não configurada'}
    with distributed_lock('conversion-sync', timeout=180, blocking_timeout=1) as locked:
        if not locked:
            return {'ok': False, 'reason': 'sincronização já em execução'}
        nodes = await client.get_conversions(days=days, limit=500)
        result = sync_conversion_nodes(db, nodes)
        return {'ok': True, **result}
