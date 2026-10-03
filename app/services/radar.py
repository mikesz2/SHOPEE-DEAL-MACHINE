import asyncio
import logging
import time
from collections import Counter
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import OfferEvent
from app.services.shopee import ShopeeAffiliateClient
from app.services.settings_store import load_runtime_settings
from app.services.ingest import ingest_node
from app.services.redis_store import distributed_lock
from app.services.discovery import query_plan, evaluate, diverse_order

log = logging.getLogger(__name__)


async def run_shopee_radar(db: Session) -> dict:
    runtime = load_runtime_settings(db)
    client = ShopeeAffiliateClient()
    if not client.configured:
        return {'ok': False, 'reason': 'Shopee não configurada', 'created': 0}
    report = dict(ok=True, created=0, scanned=0, unique=0, eligible=0, duplicates=0, queries=0, errors=[])
    rejected = Counter()
    with distributed_lock('shopee-radar', timeout=180, blocking_timeout=1) as locked:
        if not locked:
            return {'ok': False, 'reason': 'radar já está executando', 'created': 0}
        queue = db.query(OfferEvent).filter(OfferEvent.status.in_(['queued', 'reserved'])).count()
        room = min(runtime.discovery_max_candidates, max(0, runtime.max_queue_depth - queue))
        if not room:
            return {'ok': False, 'reason': 'Fila no limite configurado; aguarde as publicações', 'created': 0}
        plan = query_plan(runtime.radar_keywords, runtime.discovery_expand_keywords, datetime.utcnow().hour)
        if not plan:
            return {'ok': False, 'reason': 'Cadastre palavras-chave em Automação', 'created': 0}
        # Rotate the starting topic so bounded calls do not starve later topics.
        rotation = datetime.utcnow().hour % len(plan)
        plan = plan[rotation:] + plan[:rotation]
        candidates, seen, exhausted = {}, set(), set()
        deadline = time.monotonic() + 100
        stop = False
        # Breadth first: all topics get page one before deeper pagination.
        for page in range(1, runtime.radar_pages + 1):
            for query, topic in plan:
                if query in exhausted:
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 1 or report['queries'] >= 36:
                    report['limited'] = True
                    stop = True
                    break
                report['queries'] += 1
                try:
                    nodes = await asyncio.wait_for(client.search_products(query, page=page, limit=runtime.max_products_per_keyword), timeout=min(25, remaining))
                except Exception:
                    db.rollback()
                    report['errors'].append(f'Falha ao consultar “{query}” (página {page}).')
                    exhausted.add(query)
                    continue
                if len(nodes) < runtime.max_products_per_keyword:
                    exhausted.add(query)
                for node in nodes:
                    report['scanned'] += 1
                    identity = (str(node.get('shopId') or ''), str(node.get('itemId') or ''))
                    if identity in seen:
                        report['duplicates'] += 1
                    seen.add(identity)
                    rank, reason = evaluate(node, query, runtime, time.time())
                    if reason:
                        rejected[reason] += 1
                        continue
                    previous = candidates.get(identity)
                    if previous is None or rank > previous['rank']:
                        candidates[identity] = dict(identity=identity, node=node, topic=topic, rank=rank, query=query)
            if stop:
                break
        report['unique'], report['eligible'] = len(seen), len(candidates)
        report['selection_limit'] = room
        attempted = 0
        for candidate in diverse_order(candidates.values(), runtime.discovery_shop_limit):
            if attempted >= room:
                break
            attempted += 1
            try:
                # A unique invocation ID preserves retries without counting a prior run as new.
                ev = await ingest_node(db, candidate['node'], 'shopee_radar', candidate['query'],
                    source_message_id=datetime.utcnow().isoformat(timespec='microseconds'), source_weight=1.0)
                if ev.status == 'queued':
                    report['created'] += 1
                elif ev.status == 'duplicate':
                    report['duplicates'] += 1
                elif ev.status == 'rejected':
                    rejected[ev.reject_reason or 'regras de qualidade'] += 1
            except Exception:
                db.rollback()
                log.exception('Falha ao salvar candidato do radar')
                report['errors'].append('Um produto não pôde ser salvo; os demais foram processados.')
        report['selected'] = attempted
    report['ok'] = not report['errors']
    report['errors'] = report['errors'][:20]
    report['rejections'] = dict(rejected)
    return report
