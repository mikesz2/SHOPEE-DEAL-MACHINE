import json
import logging
import os
import time
from contextlib import contextmanager
from pathlib import Path
from app.config import settings

log = logging.getLogger(__name__)
try:
    import redis
except Exception:
    redis = None

_client = None
HEALTH_DIR = Path('data/runtime/health')
LOCK_DIR = Path('data/runtime/locks')


def get_redis():
    global _client
    if not settings.redis_url:
        return None
    if _client is not None:
        return _client
    if redis is None:
        if settings.redis_required:
            raise RuntimeError('Pacote redis não instalado')
        return None
    try:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
        _client.ping()
        return _client
    except Exception:
        if settings.redis_required:
            raise
        log.warning('Redis indisponível; usando heartbeat/locks locais')
        return None


def _health_path(component: str) -> Path:
    HEALTH_DIR.mkdir(parents=True, exist_ok=True)
    safe = ''.join(c for c in component if c.isalnum() or c in '-_')
    return HEALTH_DIR / f'{safe}.json'


def heartbeat(component: str, payload: dict | None = None, ttl: int = 120):
    value = {'ok': True, 'expires_at': time.time() + ttl, **(payload or {})}
    r = get_redis()
    if r:
        r.setex(f'health:{component}', ttl, json.dumps(value, ensure_ascii=False))
        return
    p = _health_path(component)
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, p)


def health(component: str) -> dict | None:
    r = get_redis()
    if r:
        raw = r.get(f'health:{component}')
        return json.loads(raw) if raw else None
    p = _health_path(component)
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
        if float(data.get('expires_at', 0)) < time.time():
            return None
        return data
    except Exception:
        return None


@contextmanager
def distributed_lock(name: str, timeout: int = 60, blocking_timeout: int = 1):
    r = get_redis()
    if r:
        lock = r.lock(f'lock:{name}', timeout=timeout, blocking_timeout=blocking_timeout)
        acquired = False
        try:
            acquired = lock.acquire(blocking=True)
            yield acquired
        finally:
            if acquired:
                try:
                    lock.release()
                except Exception:
                    pass
        return

    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    safe = ''.join(c for c in name if c.isalnum() or c in '-_')
    path = LOCK_DIR / f'{safe}.lock'
    deadline = time.time() + max(0, blocking_timeout)
    fd = None
    acquired = False
    while True:
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f'{os.getpid()}|{time.time()}'.encode())
            acquired = True
            break
        except FileExistsError:
            try:
                if time.time() - path.stat().st_mtime > timeout:
                    path.unlink(missing_ok=True)
                    continue
            except Exception:
                pass
            if time.time() >= deadline:
                break
            time.sleep(0.1)
    try:
        yield acquired
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass
        if acquired:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
