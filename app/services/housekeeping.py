from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import OfferEvent, PriceSnapshot, Publication, AuditEvent, RadarInbox
from app.services.settings_store import load_runtime_settings


def cleanup_old_data(db: Session) -> dict:
    runtime = load_runtime_settings(db)
    now = datetime.utcnow()
    event_cutoff = now - timedelta(days=runtime.event_retention_days)
    snapshot_cutoff = now - timedelta(days=runtime.snapshot_retention_days)
    failed_pub_cutoff = now - timedelta(days=runtime.failed_publication_retention_days)
    audit_cutoff = now - timedelta(days=runtime.audit_retention_days)

    snapshots = (db.query(PriceSnapshot)
                 .filter(PriceSnapshot.captured_at < snapshot_cutoff)
                 .delete(synchronize_session=False))
    failed_pubs = (db.query(Publication)
                   .filter(Publication.status == 'failed', Publication.created_at < failed_pub_cutoff)
                   .delete(synchronize_session=False))
    # Preserve any event referenced by a publication; delete only old terminal events without publication.
    referenced = db.query(Publication.offer_event_id)
    events = (db.query(OfferEvent)
              .filter(OfferEvent.created_at < event_cutoff,
                      OfferEvent.status.in_(['rejected', 'duplicate', 'failed']),
                      ~OfferEvent.id.in_(referenced))
              .delete(synchronize_session=False))
    audits = (db.query(AuditEvent).filter(AuditEvent.created_at < audit_cutoff).delete(synchronize_session=False))
    inbox = db.query(RadarInbox).filter(RadarInbox.created_at < now - timedelta(days=7), RadarInbox.status != 'pending').delete(synchronize_session=False)
    db.commit()
    return {'inbox_deleted':int(inbox or 0), 'price_snapshots_deleted': int(snapshots or 0),
            'failed_publications_deleted': int(failed_pubs or 0),
            'events_deleted': int(events or 0), 'audit_events_deleted': int(audits or 0)}
