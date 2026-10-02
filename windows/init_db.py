from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app.db import Base, engine  # noqa: E402
import app.models  # noqa: F401,E402

(ROOT / 'data' / 'windows').mkdir(parents=True, exist_ok=True)
Base.metadata.create_all(bind=engine)
print('OK')
