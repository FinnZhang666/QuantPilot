from datetime import datetime, timezone

from sqlalchemy import select

from app.database.models import CandidatePoolEntry


def expire_due(db, now=None):
    now = now or datetime.now(timezone.utc)
    rows = db.scalars(select(CandidatePoolEntry).where(
        CandidatePoolEntry.expires_at <= now,
        CandidatePoolEntry.status.in_(["CANDIDATE", "RESEARCHING", "QUALIFIED"]),
    )).all()
    for row in rows:
        row.status = "EXPIRED"
    db.commit()
    return list(rows)
