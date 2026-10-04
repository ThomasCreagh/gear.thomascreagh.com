"""Batch inventory queries shared by loan and administration workflows."""

from sqlalchemy import func
from sqlalchemy.orm import Session

import models


def latest_locker_codes(db: Session, lockers):
    latest_ids = db.query(func.max(models.LockerCode.id)).filter(
        models.LockerCode.locker.in_(lockers)
    ).group_by(models.LockerCode.locker)
    return {
        row.locker: row
        for row in db.query(models.LockerCode).filter(
            models.LockerCode.id.in_(latest_ids)
        ).all()
    }


def set_items_available(db: Session, item_ids, available: bool):
    ids = set(item_ids or [])
    if ids:
        db.query(models.Item).filter(models.Item.id.in_(ids)).update(
            {models.Item.available: available}, synchronize_session="fetch"
        )
