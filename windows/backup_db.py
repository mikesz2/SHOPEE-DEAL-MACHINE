from __future__ import annotations
import argparse
import os
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)


def db_path() -> Path:
    env = dotenv_values(ROOT / '.env')
    url = str(env.get('DATABASE_URL') or 'sqlite:///./data/windows/deals.db')
    if not url.startswith('sqlite:///'):
        raise RuntimeError('A edição Windows usa SQLite para backup local')
    raw = url[len('sqlite:///'):]
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def _check_database(path: Path) -> None:
    if not path.exists() or not path.is_file():
        raise RuntimeError(f'Arquivo de banco não encontrado: {path}')
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        row = conn.execute('PRAGMA quick_check').fetchone()
        result = str(row[0] if row else '').strip().lower()
        if result != 'ok':
            raise RuntimeError(f'Falha na verificação de integridade do banco: {result or "sem resposta"}')
    finally:
        conn.close()


def backup(quiet: bool = False):
    src = db_path()
    src.parent.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        if not quiet:
            print('Banco ainda não existe.')
        return None

    outdir = ROOT / 'backups'
    outdir.mkdir(exist_ok=True)
    out = outdir / f'deals-{datetime.now().strftime("%Y%m%d-%H%M%S-%f")}.db'

    source = sqlite3.connect(str(src), timeout=30)
    target = sqlite3.connect(str(out), timeout=30)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    _check_database(out)

    env = dotenv_values(ROOT / '.env')
    keep = max(1, int(env.get('BACKUP_RETENTION_DAYS') or 30))
    cutoff = datetime.now() - timedelta(days=keep)
    for file in outdir.glob('deals-*.db'):
        try:
            if datetime.fromtimestamp(file.stat().st_mtime) < cutoff:
                file.unlink()
        except Exception:
            pass

    if not quiet:
        print(out)
    return out


def restore(source):
    src = Path(source).resolve()
    _check_database(src)

    dest = db_path().resolve()
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + '.restore.tmp')

    for stale in (tmp, Path(str(dest) + '-wal'), Path(str(dest) + '-shm')):
        try:
            stale.unlink(missing_ok=True)
        except Exception:
            pass

    shutil.copy2(src, tmp)
    _check_database(tmp)
    os.replace(tmp, dest)

    # Remove WAL/SHM remnants from the previous database so they can never
    # be replayed on top of the restored snapshot.
    for sidecar in (Path(str(dest) + '-wal'), Path(str(dest) + '-shm')):
        try:
            sidecar.unlink(missing_ok=True)
        except Exception:
            pass

    _check_database(dest)
    return dest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--quiet', action='store_true')
    parser.add_argument('--restore')
    args = parser.parse_args()
    if args.restore:
        print(restore(args.restore))
    else:
        result = backup(args.quiet)
        if not args.quiet:
            # backup() already prints the path or status; avoid a duplicate.
            pass
        elif result is None:
            print('')
