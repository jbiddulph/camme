from sqlalchemy.orm import Session

from app.models.report import Report


def persist_report(
    db: Session,
    *,
    room_name: str,
    reported_user: str,
    reason: str,
) -> Report:
    row = Report(room_name=room_name, reported_user=reported_user, reason=reason)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
