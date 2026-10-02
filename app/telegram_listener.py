import asyncio
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from telethon import TelegramClient, events
from app.config import settings
from app.db import SessionLocal
from app.models import Source
from app.services.url_utils import extract_urls, is_safe_shopee_url
from app.services.ingest import ingest_url
from app.services.redis_store import heartbeat
from app.services.telegram_ipc import REQUESTS, RESPONSES, ensure_ipc_dirs, clean_old_jobs
from app.services.audit import safe_record
from app.services.collector import enqueue_message, inbox_loop, catchup_loop

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                    format='%(asctime)s %(levelname)s %(name)s %(message)s')
log = logging.getLogger('telegram-radar')


def norm(v: str) -> str:
    raw = (v or '').strip().lower()
    raw = re.sub(r'^https?://t\.me/', '', raw).strip('/')
    return raw.lstrip('@')


def ref_for_telethon(v: str):
    raw = (v or '').strip()
    raw = re.sub(r'^https?://t\.me/', '', raw, flags=re.I).strip('/')
    if re.fullmatch(r'-?\d+', raw):
        try:
            return int(raw)
        except Exception:
            return raw
    return raw if raw.startswith('@') else ('@' + raw if raw and not raw.startswith('+') else raw)


def message_urls(message) -> list[str]:
    urls = extract_urls(getattr(message, 'raw_text', '') or getattr(message, 'message', '') or '')
    try:
        for entity in (getattr(message, 'entities', None) or []):
            u = getattr(entity, 'url', None)
            if u and is_safe_shopee_url(u) and u not in urls:
                urls.append(u)
    except Exception:
        pass
    try:
        for row in (getattr(message, 'buttons', None) or []):
            for button in row:
                u = getattr(button, 'url', None)
                if u and is_safe_shopee_url(u) and u not in urls:
                    urls.append(u)
    except Exception:
        pass
    try:
        webpage = getattr(getattr(message, 'media', None), 'webpage', None)
        u = getattr(webpage, 'url', None)
        if u and is_safe_shopee_url(u) and u not in urls:
            urls.append(u)
    except Exception:
        pass
    return urls[:8]


async def resolve_source_entity(client: TelegramClient, chat_ref: str):
    candidate = ref_for_telethon(chat_ref)
    try:
        return await client.get_entity(candidate)
    except Exception as first_error:
        wanted = norm(chat_ref)
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            eid = str(getattr(entity, 'id', ''))
            # Telegram event ids for channels/supergroups are often -100<id>.
            peer_id = str(getattr(dialog, 'id', '') or '')
            username = norm(getattr(entity, 'username', '') or '')
            if wanted in {norm(eid), norm(peer_id), username}:
                return entity
        raise first_error


async def source_diagnostics(client: TelegramClient, source: Source, sample_limit: int = 50) -> dict:
    entity = await resolve_source_entity(client, source.chat_ref)
    dialog_member = False
    try:
        async for dialog in client.iter_dialogs():
            if getattr(dialog.entity, 'id', None) == getattr(entity, 'id', None):
                dialog_member = True
                break
    except Exception:
        pass

    previews = []
    shopee_links = 0
    last_msg = None
    async for msg in client.iter_messages(entity, limit=max(1, min(sample_limit, 100))):
        if last_msg is None:
            last_msg = msg
        urls = message_urls(msg)
        shopee_links += len(urls)
        if len(previews) < 5:
            text = (getattr(msg, 'raw_text', '') or getattr(msg, 'message', '') or '').replace('\n', ' ').strip()
            previews.append({
                'id': str(getattr(msg, 'id', '')),
                'date': getattr(msg, 'date', None).isoformat() if getattr(msg, 'date', None) else None,
                'text': text[:180],
                'shopee_links': len(urls),
            })

    return {
        'accessible': True,
        'member': dialog_member,
        'source_id': source.id,
        'name': source.name,
        'chat_ref': source.chat_ref,
        'telegram_id': str(getattr(entity, 'id', '')),
        'username': getattr(entity, 'username', None),
        'title': getattr(entity, 'title', None) or getattr(entity, 'first_name', None) or source.name,
        'last_message_id': str(getattr(last_msg, 'id', '')) if last_msg else None,
        'last_message_at': getattr(last_msg, 'date', None).isoformat() if last_msg and getattr(last_msg, 'date', None) else None,
        'sample_messages': max(1, min(sample_limit, 100)),
        'shopee_links_in_sample': shopee_links,
        'recent_messages': previews,
    }


async def import_history(client: TelegramClient, source: Source, message_limit: int) -> dict:
    entity = await resolve_source_entity(client, source.chat_ref)
    limit = max(1, min(int(message_limit or 100), 500))
    scanned = 0
    messages_with_links = 0
    links_found = 0
    ingested = 0
    failed = 0
    duplicates_or_existing = 0
    seen_urls = set()

    async for msg in client.iter_messages(entity, limit=limit):
        scanned += 1
        urls = message_urls(msg)
        if not urls:
            continue
        messages_with_links += 1
        for url in urls:
            links_found += 1
            key = (str(getattr(msg, 'id', '')), url)
            if key in seen_urls:
                continue
            seen_urls.add(key)
            from datetime import timedelta
            from app.services.settings_store import load_runtime_settings
            db = SessionLocal()
            try:
                max_age = load_runtime_settings(db).max_offer_age_hours
                stamp = getattr(msg, 'date', None)
                if stamp and stamp.replace(tzinfo=None) < datetime.utcnow() - timedelta(hours=max_age):
                    continue
                added = enqueue_message(db, source, getattr(msg, 'id', ''), [url], posted_at=stamp)
                ingested += added
                duplicates_or_existing += int(not added)
            except Exception:
                db.rollback()
                failed += 1
            finally:
                db.close()
            # Keep the reader responsive and avoid a tight burst against external APIs.
            await asyncio.sleep(0.05)

    return {
        'source_id': source.id,
        'source': source.chat_ref,
        'scanned_messages': scanned,
        'messages_with_shopee_links': messages_with_links,
        'links_found': links_found,
        'ingested': ingested,
        'failed': failed,
        'existing_or_duplicate': duplicates_or_existing,
    }


async def command_loop(client: TelegramClient):
    ensure_ipc_dirs()
    clean_old_jobs()
    while True:
        try:
            for req_path in sorted(REQUESTS.glob('*.json'), key=lambda p: p.stat().st_mtime)[:4]:
                try:
                    req = json.loads(req_path.read_text(encoding='utf-8'))
                    job_id = str(req.get('job_id') or req_path.stem)
                    action = req.get('action')
                    payload = req.get('payload') or {}
                    result = None
                    db = SessionLocal()
                    try:
                        source_id = int(payload.get('source_id') or 0)
                        source = db.get(Source, source_id) if source_id else None
                        if action in {'test_source', 'import_history'} and not source:
                            raise ValueError('Fonte não encontrada')
                        if action == 'test_source':
                            result = await source_diagnostics(client, source, int(payload.get('sample_limit') or 50))
                            safe_record(db, 'telegram.source_test', f'Fonte testada: {source.name}', context={'source_id':source.id,'links':result.get('shopee_links_in_sample',0)})
                        elif action == 'import_history':
                            # detach simple values before DB closes; import_history opens its own sessions per URL.
                            source_name, source_id = source.name, source.id
                            db.expunge(source)
                            result = await import_history(client, source, int(payload.get('message_limit') or 100))
                            safe_record(db, 'telegram.history_import', f'Histórico importado: {source_name}', context={'source_id':source_id, **result})
                        else:
                            raise ValueError(f'Ação de Reader desconhecida: {action}')
                    finally:
                        db.close()
                    response = {'ok': True, 'result': result, 'finished_at': time.time()}
                except Exception as e:
                    log.exception('falha em comando do painel: %s', e)
                    response = {'ok': False, 'error': str(e), 'finished_at': time.time()}
                try:
                    target = RESPONSES / f'{job_id}.json'
                    temp = target.with_suffix('.tmp')
                    temp.write_text(json.dumps(response, ensure_ascii=False, default=str), encoding='utf-8')
                    temp.replace(target)
                finally:
                    req_path.unlink(missing_ok=True)
        except Exception as e:
            log.warning('falha no loop de comandos: %s', e)
        await asyncio.sleep(1)


async def main():
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise SystemExit('Configure TELEGRAM_API_ID e TELEGRAM_API_HASH')
    settings.telegram_session_parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(settings.telegram_session_path, settings.telegram_api_id, settings.telegram_api_hash)

    @client.on(events.NewMessage)
    async def handler(event):
        db = SessionLocal()
        try:
            chat = await event.get_chat()
            username = getattr(chat, 'username', None)
            chat_id = str(getattr(event, 'chat_id', ''))
            entity_id = str(getattr(chat, 'id', ''))
            refs = {norm(username or ''), norm(chat_id), norm(entity_id)}
            sources = db.query(Source).filter(Source.active.is_(True)).all()
            source = next((s for s in sources if norm(s.chat_ref) in refs), None)
            if not source:
                return
            urls = message_urls(event.message)
            enqueue_message(db, source, event.id, urls, posted_at=event.message.date)
            heartbeat('listener', {'time': datetime.utcnow().isoformat() + 'Z', 'source': source.chat_ref, 'links': len(urls)}, ttl=180)
        finally:
            db.close()

    await client.connect()
    if not await client.is_user_authorized():
        marker = settings.telegram_session_parent / (Path(settings.telegram_session_path).name + '.authorized')
        try:
            marker.unlink(missing_ok=True)
        except Exception:
            pass
        await client.disconnect()
        raise RuntimeError('Sessão do Telegram expirou ou foi revogada. Use “Conectar conta leitora” novamente na Central Windows.')
    me = await client.get_me()
    log.info('Radar conectado como %s', getattr(me, 'username', None) or getattr(me, 'first_name', 'conta'))
    heartbeat('listener', {'time': datetime.utcnow().isoformat() + 'Z', 'connected': True}, ttl=180)

    async def pulse():
        while True:
            heartbeat('listener', {'time': datetime.utcnow().isoformat() + 'Z', 'connected': client.is_connected()}, ttl=180)
            await asyncio.sleep(60)
    asyncio.create_task(pulse())
    asyncio.create_task(command_loop(client))
    asyncio.create_task(inbox_loop())
    asyncio.create_task(catchup_loop(client, resolve_source_entity, message_urls))
    await client.run_until_disconnected()


if __name__ == '__main__':
    asyncio.run(main())
