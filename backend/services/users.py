"""User lookup helpers shared by authentication and administration routes."""

from sqlalchemy import func
from sqlalchemy.orm import Session

import models


def normalise_email(email: str) -> str:
    """Use one canonical email form throughout the application."""
    return email.strip().lower()


def find_user_by_email(db: Session, email: str) -> models.User | None:
    """Find an account regardless of the casing used in the email address."""
    return db.query(models.User).filter(
        func.lower(models.User.email) == normalise_email(email)
    ).first()
