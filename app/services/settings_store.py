import json
from sqlalchemy.orm import Session
from app.models import AppSetting
from app.schemas import RuntimeSettings


DEFAULTS = RuntimeSettings().model_dump()


def load_runtime_settings(db: Session) -> RuntimeSettings:
    values = DEFAULTS.copy()
    rows = db.query(AppSetting).all()
    for row in rows:
        if row.key in values:
            try:
                values[row.key] = json.loads(row.value)
            except Exception:
                values[row.key] = row.value
    return RuntimeSettings(**values)


def save_runtime_settings(db: Session, settings: RuntimeSettings) -> RuntimeSettings:
    for key, value in settings.model_dump().items():
        row = db.get(AppSetting, key)
        encoded = json.dumps(value, ensure_ascii=False)
        if row:
            row.value = encoded
        else:
            db.add(AppSetting(key=key, value=encoded))
    db.commit()
    return settings
