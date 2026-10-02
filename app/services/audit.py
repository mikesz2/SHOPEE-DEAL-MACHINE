from __future__ import annotations
import json
from typing import Any
from sqlalchemy.orm import Session
from app.models import AuditEvent


def record_event(db: Session, event_type: str, message: str, severity: str = 'info', actor: str = 'system', context: dict[str, Any] | None = None, commit: bool = True) -> AuditEvent:
    row = AuditEvent(
        event_type=(event_type or 'event')[:80],
        severity=(severity or 'info')[:16],
        actor=(actor or 'system')[:80],
        message=str(message)[:4000],
        context_json=json.dumps(context or {}, ensure_ascii=False, default=str)[:12000],
    )
    db.add(row)
    if commit:
        db.commit(); db.refresh(row)
    return row


def safe_record(db: Session, *args, **kwargs):
    try:
        return record_event(db, *args, **kwargs)
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return None
