from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_init_db_direct_script_can_import_app_from_any_cwd(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(ROOT / 'windows' / 'init_db.py')],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert 'OK' in proc.stdout


def test_windows_smoke_imports_can_import_app_from_any_cwd(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(ROOT / 'windows' / 'smoke_imports.py')],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert 'APP_OK=' in proc.stdout
    assert 'OK' in proc.stdout


def test_test_integrations_json_is_console_codepage_safe():
    source = (ROOT / 'windows' / 'test_integrations.py').read_text(encoding='utf-8')
    assert 'ensure_ascii=True' in source
    assert "reconfigure(encoding='utf-8'" in source


def test_windows_launchers_force_python_utf8():
    cc = (ROOT / 'windows' / 'ControlCenter.ps1').read_text(encoding='utf-8-sig')
    sup = (ROOT / 'windows' / 'supervisor.py').read_text(encoding='utf-8')
    heal = (ROOT / 'windows' / 'self_heal.py').read_text(encoding='utf-8')
    assert 'PYTHONUTF8' in cc and 'PYTHONIOENCODING' in cc
    assert 'PYTHONUTF8' in sup and 'PYTHONIOENCODING' in sup
    assert 'PYTHONUTF8' in heal and 'PYTHONIOENCODING' in heal
