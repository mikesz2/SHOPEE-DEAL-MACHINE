from __future__ import annotations
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
import app
from app.config import settings
from app.db import Base, engine
import app.models
print('APP_OK=' + str(app.__file__))
print('DB=' + str(settings.database_url))
print('OK')
