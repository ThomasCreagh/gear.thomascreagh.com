"""Overdue-loan reminder workflow shared by admin endpoints."""

from datetime import datetime
from sqlalchemy.orm import Session

import models
from mailer import send_overdue_notice


def item_label(item: models.Item) -> str:
    """Return a concise, recognisable label for an item in an email."""
    label = f"#{item.tag} {item.name}" if item.tag else item.name
    return f"{label} — {item.description}" if item.description else label


def send_overdue_reminders(db: Session, triggered_by: int) -> list[dict]:
    """Email one consolidated reminder per borrower with an overdue loan."""
    overdue_loans = db.query(models.Loan).filter(
        models.Loan.status == "active",
        models.Loan.due_date < datetime.utcnow(),
    ).all()

    reminders: dict[int, dict] = {}
    for loan in overdue_loans:
        user = db.get(models.User, loan.user_id)
        if not user:
            continue
        reminder = reminders.setdefault(user.id, {"user": user, "items": [], "loan_ids": []})
        items = db.query(models.Item).filter(models.Item.id.in_(loan.item_ids or [])).all()
        reminder["items"].extend(item_label(item) for item in items)
        reminder["loan_ids"].append(loan.id)

    notified = []
    for reminder in reminders.values():
        user = reminder["user"]
        send_overdue_notice(user.email, reminder["items"] or ["(no items logged)"])
        db.add(models.AuditLog(
            user_id=triggered_by,
            action="overdue_notice_sent",
            details=f"Loans {reminder['loan_ids']}, user {user.email}",
        ))
        notified.append({"loan_ids": reminder["loan_ids"], "user": user.email})

    db.commit()
    return notified
