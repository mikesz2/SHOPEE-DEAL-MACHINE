import json
import time
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IPC_ROOT = PROJECT_ROOT / 'data' / 'windows' / 'telegram_ipc'
REQUESTS = IPC_ROOT / 'requests'
RESPONSES = IPC_ROOT / 'responses'


def ensure_ipc_dirs():
    REQUESTS.mkdir(parents=True, exist_ok=True)
    RESPONSES.mkdir(parents=True, exist_ok=True)


def queue_command(action: str, payload: dict | None = None) -> str:
    ensure_ipc_dirs()
    clean_old_jobs()
    job_id = uuid.uuid4().hex
    data = {
        'job_id': job_id,
        'action': action,
        'payload': payload or {},
        'created_at': time.time(),
    }
    target = REQUESTS / f'{job_id}.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    temp.replace(target)
    return job_id


def read_result(job_id: str) -> dict:
    ensure_ipc_dirs()
    if not job_id or any(c not in '0123456789abcdef' for c in job_id.lower()) or len(job_id) != 32:
        return {'status': 'error', 'error': 'job_id inválido'}
    path = RESPONSES / f'{job_id}.json'
    if not path.exists():
        return {'status': 'pending', 'job_id': job_id}
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return {'status': 'done', 'job_id': job_id, **data}
    except Exception as e:
        return {'status': 'error', 'job_id': job_id, 'error': f'Falha ao ler resultado: {e}'}


def clean_old_jobs(max_age_seconds: int = 86400):
    ensure_ipc_dirs()
    cutoff = time.time() - max_age_seconds
    for folder in (REQUESTS, RESPONSES):
        for p in folder.glob('*.json'):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink(missing_ok=True)
            except Exception:
                pass
