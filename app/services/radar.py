import logging
from datetime import datetime, timedelta
from app.models import OfferEvent, Product
from sqlalchemy.orm import Session
from app.services.shopee import ShopeeAffiliateClient
from app.services.settings_store import load_runtime_settings
from app.services.ingest import ingest_node
from app.services.redis_store import distributed_lock

log = logging.getLogger(__name__)


async def run_shopee_radar(db: Session) -> dict:
    runtime = load_runtime_settings(db)
    client = ShopeeAffiliateClient()
    if not client.configured:
        return {'ok': False, 'reason': 'Shopee não configurada', 'created': 0}
    created = 0
    errors = []
    with distributed_lock('shopee-radar', timeout=180, blocking_timeout=1) as locked:
        if not locked:
            return {'ok': False, 'reason': 'radar já está executando', 'created': 0}
        keywords = [k.strip() for k in runtime.radar_keywords.split(',') if k.strip()]
        seen = set()
        for kw in keywords:
            try:
                for page in range(1, runtime.radar_pages + 1):
                    nodes = await client.search_products(kw, page=page, limit=runtime.max_products_per_keyword)
                    if not nodes:
                        break
                    for node in nodes:
                        identity = (str(node.get('shopId')), str(node.get('itemId')))
                        if identity in seen:
                            continue
                        seen.add(identity)
                        try:
                            ev = await ingest_node(db, node, 'shopee_radar', kw,
                                source_message_id=datetime.utcnow().strftime('%Y%m%d%H'), source_weight=1.0)
                            if ev.status == 'queued':
                                created += 1
                        except Exception as e:
                            db.rollback()
                            errors.append(f'{kw}: {e}')
                    if len(nodes) < runtime.max_products_per_keyword:
                        break
            except Exception as e:
                errors.append(f'{kw}: {e}')
    return {'ok': len(errors) == 0, 'created': created, 'errors': errors[:20]}
