from __future__ import annotations
import json, os, signal, subprocess, sys, time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
DATA = ROOT / 'data' / 'runtime'
LOGS = ROOT / 'logs'
DATA.mkdir(parents=True, exist_ok=True)
LOGS.mkdir(parents=True, exist_ok=True)
PID_FILE = DATA / 'supervisor.pid'
STATE_FILE = DATA / 'state.json'
STOP_FILE = DATA / 'stop.flag'
PYTHON_FILE = DATA / 'python_path.txt'

CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
CREATE_NEW_PROCESS_GROUP = 0x00000200 if os.name == 'nt' else 0


def now(): return datetime.utcnow().isoformat() + 'Z'

def pid_alive(pid: int) -> bool:
    if pid <= 0: return False
    try:
        if os.name == 'nt':
            out = subprocess.run(['tasklist','/FI',f'PID eq {pid}','/NH'], capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
            return str(pid) in out.stdout
        os.kill(pid, 0); return True
    except Exception: return False


def rotate(path: Path, max_bytes=12*1024*1024):
    try:
        if path.exists() and path.stat().st_size > max_bytes:
            old = path.with_suffix(path.suffix + '.1')
            old.unlink(missing_ok=True); path.replace(old)
    except Exception: pass


def load_env():
    """Tiny .env reader using only the Python standard library.

    The supervisor must be able to start even before third-party packages are installed,
    so do not import python-dotenv here.
    """
    values = {}
    path = ROOT / '.env'
    if not path.exists():
        return values
    try:
        for raw in path.read_text(encoding='utf-8-sig', errors='replace').splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip()
            if value and len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                value = value[1:-1]
            if key:
                values[key] = value
    except Exception:
        pass
    return values


def truth(v): return str(v).strip().lower() in {'1','true','yes','on','sim'}


def child_specs(env):
    python = Path(sys.executable)
    host = env.get('APP_HOST','127.0.0.1')
    port = env.get('APP_PORT','8787')
    level = env.get('LOG_LEVEL','INFO').lower()
    specs = {
        'web': [str(python), '-m', 'uvicorn', 'app.main:app', '--host', host, '--port', port, '--log-level', level],
        'worker': [str(python), '-m', 'app.worker'],
    }
    session_base = ROOT / env.get('TELEGRAM_SESSION_PATH','data/telegram/reader')
    session_exists = session_base.with_suffix('.session').exists() or session_base.exists()
    authorized = session_base.with_suffix('.authorized').exists()
    reader_ok = truth(env.get('TELEGRAM_READER_ENABLED','true')) and env.get('TELEGRAM_API_ID') and env.get('TELEGRAM_API_HASH') and session_exists and authorized
    if reader_ok:
        specs['listener'] = [str(python), '-m', 'app.telegram_listener']
    return specs


def backup_db(env):
    try:
        subprocess.run([sys.executable, str(ROOT/'windows'/'backup_db.py'), '--quiet'], cwd=ROOT, timeout=120, creationflags=CREATE_NO_WINDOW)
    except Exception:
        pass


def write_state(children, restarts, last_exit):
    state={'supervisor':{'pid':os.getpid(),'running':True,'time':now()},'components':{}}
    for name,p in children.items():
        state['components'][name]={'pid':p.pid if p else None,'running':bool(p and p.poll() is None),'restarts':restarts.get(name,0),'last_exit':last_exit.get(name)}
    tmp=STATE_FILE.with_suffix('.tmp'); tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8'); os.replace(tmp,STATE_FILE)


def main():
    if PID_FILE.exists():
        try:
            old=int(PID_FILE.read_text().strip())
            if pid_alive(old) and old != os.getpid(): return 0
        except Exception: pass
    STOP_FILE.unlink(missing_ok=True)
    PID_FILE.write_text(str(os.getpid()),encoding='ascii')
    env=load_env(); proc_env=os.environ.copy(); proc_env.update(env); proc_env['PYTHONUNBUFFERED']='1'; proc_env['PYTHONUTF8']='1'; proc_env['PYTHONIOENCODING']='utf-8'; proc_env['PYTHONPATH']=str(ROOT)+(os.pathsep+proc_env['PYTHONPATH'] if proc_env.get('PYTHONPATH') else '')
    children={}; handles={}; restarts={}; last_exit={}; next_start={}
    last_backup=datetime.utcnow()-timedelta(days=1)
    stop=False
    def request_stop(*_):
        nonlocal stop; stop=True
    try:
        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
    except Exception: pass
    try:
        while not stop and not STOP_FILE.exists():
            env=load_env(); specs=child_specs(env)
            # stop components no longer desired
            for name in list(children):
                if name not in specs:
                    p=children.pop(name)
                    if p and p.poll() is None:
                        try: p.terminate(); p.wait(timeout=8)
                        except Exception:
                            try: p.kill()
                            except Exception: pass
                    h=handles.pop(name,None)
                    if h: h.close()
            # start/restart
            for name,cmd in specs.items():
                p=children.get(name)
                if p and p.poll() is None: continue
                if p and p.poll() is not None:
                    last_exit[name]={'code':p.returncode,'time':now()}; restarts[name]=restarts.get(name,0)+1
                    h=handles.pop(name,None)
                    if h: h.close()
                if time.time() < next_start.get(name,0): continue
                log_path=LOGS/f'{name}.log'; rotate(log_path); h=open(log_path,'a',encoding='utf-8',errors='replace')
                flags=CREATE_NO_WINDOW|CREATE_NEW_PROCESS_GROUP
                try:
                    child_env={**os.environ,**env,'PYTHONUNBUFFERED':'1','PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'}; child_env['PYTHONPATH']=str(ROOT)+(os.pathsep+child_env['PYTHONPATH'] if child_env.get('PYTHONPATH') else ''); p=subprocess.Popen(cmd,cwd=ROOT,env=child_env,stdout=h,stderr=subprocess.STDOUT,creationflags=flags)
                    children[name]=p; handles[name]=h; next_start[name]=time.time()+5
                except Exception as exc:
                    h.write(f'{now()} supervisor failed to start {name}: {exc}\n'); h.flush(); h.close(); next_start[name]=time.time()+15
            if datetime.utcnow()-last_backup >= timedelta(hours=max(1,int(env.get('BACKUP_INTERVAL_HOURS','12')))):
                backup_db(env); last_backup=datetime.utcnow()
            write_state(children,restarts,last_exit)
            time.sleep(3)
    finally:
        for name,p in list(children.items()):
            if p and p.poll() is None:
                try: p.terminate(); p.wait(timeout=10)
                except Exception:
                    try: p.kill()
                    except Exception: pass
        for h in handles.values():
            try: h.close()
            except Exception: pass
        try:
            STATE_FILE.write_text(json.dumps({'supervisor':{'pid':os.getpid(),'running':False,'time':now()},'components':{}},indent=2),encoding='utf-8')
        except Exception: pass
        PID_FILE.unlink(missing_ok=True); STOP_FILE.unlink(missing_ok=True)
    return 0

if __name__=='__main__': raise SystemExit(main())
