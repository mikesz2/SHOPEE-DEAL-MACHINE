from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='backslashreplace')
    except Exception:
        pass

LOGS = ROOT / 'logs'
LOGS.mkdir(parents=True, exist_ok=True)
LOG = LOGS / 'self_heal.log'
REQ = ROOT / 'requirements-windows.txt'
ENV = ROOT / '.env'
ENV_EXAMPLE = ROOT / '.env.example'
REQUIRED = [
    'fastapi', 'uvicorn', 'sqlalchemy', 'pydantic', 'pydantic_settings',
    'httpx', 'telethon', 'dotenv', 'alembic',
]


def log(msg: str):
    line = time.strftime('%Y-%m-%d %H:%M:%S') + ' ' + msg
    print(line, flush=True)
    with LOG.open('a', encoding='utf-8', errors='replace') as f:
        f.write(line + '\n')


def child_env():
    env = os.environ.copy()
    existing = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = str(ROOT) + (os.pathsep + existing if existing else '')
    env['PYTHONUNBUFFERED'] = '1'
    env['PYTHONUTF8'] = '1'
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


def run(cmd, timeout=1200):
    log('RUN: ' + ' '.join(map(str, cmd)))
    p = subprocess.run(
        cmd,
        cwd=ROOT,
        env=child_env(),
        text=True,
        capture_output=True,
        timeout=timeout,
    )
    if p.stdout:
        for line in p.stdout.splitlines():
            log('OUT: ' + line)
    if p.stderr:
        for line in p.stderr.splitlines():
            log('ERR: ' + line)
    if p.returncode != 0:
        detail = (p.stderr or p.stdout or '').strip()
        suffix = f' | {detail[-1500:]}' if detail else ''
        raise RuntimeError(f'Comando falhou com código {p.returncode}: {cmd[0]}{suffix}')
    return p


def missing_modules():
    missing = []
    for name in REQUIRED:
        try:
            importlib.import_module(name)
        except Exception:
            missing.append(name)
    return missing


def main():
    try:
        log('=== SELF HEAL START ===')
        log('Python: ' + sys.executable)
        log('Projeto: ' + str(ROOT))

        if not ENV.exists() and ENV_EXAMPLE.exists():
            shutil.copy2(ENV_EXAMPLE, ENV)
            log('.env criado a partir de .env.example')

        # pip validation uses the actual return code, never warning text.
        try:
            import pip  # noqa: F401
            log('pip import OK')
        except Exception:
            log('pip import indisponivel; executando ensurepip')
            run([sys.executable, '-m', 'ensurepip', '--upgrade'], 600)
        run([sys.executable, '-m', 'pip', '--version'], 90)

        missing = missing_modules()
        if missing:
            log('Dependências ausentes: ' + ', '.join(missing))
            if not REQ.exists():
                raise RuntimeError('requirements-windows.txt não encontrado')
            run([
                sys.executable, '-m', 'pip', '--disable-pip-version-check',
                '--no-input', 'install', '-r', str(REQ),
            ], 1800)
            check = (
                'import fastapi,uvicorn,sqlalchemy,pydantic,pydantic_settings,'
                'httpx,telethon,dotenv,alembic; print("DEPENDENCIES_OK")'
            )
            run([sys.executable, '-c', check], 120)
        else:
            log('Dependências Python OK')

        # Explicitly validate the project package before DB initialization.
        run([
            sys.executable, '-c',
            'import os,sys; from pathlib import Path; '
            'root=Path.cwd(); sys.path.insert(0,str(root)); import app; '
            'print("APP_IMPORT_OK", app.__file__)',
        ], 90)

        init_db = ROOT / 'windows' / 'init_db.py'
        if not init_db.exists():
            raise RuntimeError('windows\\init_db.py não encontrado')
        run([sys.executable, str(init_db)], 180)
        log('Banco local OK')
        log('=== SELF HEAL READY ===')
        print('READY')
        return 0
    except Exception as exc:
        log('FATAL: ' + repr(exc))
        for line in traceback.format_exc().splitlines():
            log(line)
        print('SELF_HEAL_ERROR: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
