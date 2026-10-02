from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

LOGS = ROOT / 'logs'
LOGS.mkdir(parents=True, exist_ok=True)
REPORT = LOGS / 'preflight.json'

REQUIRED = [
    ('fastapi', 'fastapi'),
    ('uvicorn', 'uvicorn'),
    ('sqlalchemy', 'sqlalchemy'),
    ('pydantic', 'pydantic'),
    ('pydantic_settings', 'pydantic-settings'),
    ('httpx', 'httpx'),
    ('telethon', 'telethon'),
    ('dotenv', 'python-dotenv'),
    ('alembic', 'alembic'),
]


def main():
    result = {
        'python': sys.executable,
        'version': sys.version,
        'root': str(ROOT),
        'missing': [],
        'errors': [],
    }
    for module, package in REQUIRED:
        try:
            importlib.import_module(module)
        except Exception as exc:
            result['missing'].append(package)
            result['errors'].append(f'{module}: {exc.__class__.__name__}: {exc}')

    # This catches path/package problems before the supervisor starts.
    try:
        importlib.import_module('app')
        result['app_import_ok'] = True
    except Exception as exc:
        result['app_import_ok'] = False
        result['errors'].append(f'app: {exc.__class__.__name__}: {exc}')

    env = ROOT / '.env'
    result['env_exists'] = env.exists()
    result['requirements_exists'] = (ROOT / 'requirements-windows.txt').exists()
    result['supervisor_exists'] = (ROOT / 'windows' / 'supervisor.py').exists()
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    if result['missing'] or not result.get('app_import_ok'):
        if result['missing']:
            print('MISSING=' + ','.join(result['missing']))
        for e in result['errors']:
            print(e)
        return 10
    print('OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
