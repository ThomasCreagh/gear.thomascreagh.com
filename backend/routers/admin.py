from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from database import get_db
import models
import schemas
from auth import get_admin_user, hash_password
from email_service import send_account_created, send_overdue_notice
import secrets

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=List[schemas.UserOut])
def list_users(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user),
):
    return db.query(models.User).all()


@router.post("/users")
def create_user(
    email: str,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user)
):
    if db.query(models.User).filter(models.User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already exists")

    temp_password = secrets.token_urlsafe(10)
    user = models.User(
        email=email,
        password_hash=hash_password(temp_password),
        is_approved=True
    )
    db.add(user)
    log = models.AuditLog(
        user_id=admin.id, action="user_created", details=f"Created: {email}")
    db.add(log)
    db.commit()

    send_account_created(email, temp_password)
    return {"message": "User created", "email": email}


@router.post("/users/{user_id}/approve")
def approve_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_approved = True
    log = models.AuditLog(
        user_id=admin.id, action="user_approved", details=f"User {user_id}")
    db.add(log)
    db.commit()
    return {"message": "User approved"}


@router.post("/users/{user_id}/lock")
def lock_user(
    user_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_locked = not user.is_locked
    action = "user_locked" if user.is_locked else "user_unlocked"
    log = models.AuditLog(user_id=admin.id, action=action,
                          details=f"User {user_id}")
    db.add(log)
    db.commit()
    return {"message": f"User {'locked' if user.is_locked else 'unlocked'}"}


@router.post("/users/{user_id}/reset-password")
def reset_password(
    user_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    temp_password = secrets.token_urlsafe(10)
    user.password_hash = hash_password(temp_password)
    log = models.AuditLog(
        user_id=admin.id, action="password_reset", details=f"User {user_id}")
    db.add(log)
    db.commit()
    send_account_created(user.email, temp_password)
    return {"message": "Password reset, email sent"}


@router.get("/loans", response_model=List[schemas.LoanOut])
def list_loans(
    active_only: bool = False,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user)
):
    q = db.query(models.Loan)
    if active_only:
        q = q.filter(models.Loan.returned == False)
    return q.all()


@router.post("/stock-check")
def stock_check(
    check: schemas.StockCheckRequest,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user)
):
    discrepancies = []
    for entry in check.items:
        item = db.query(models.Item).filter(
            models.Item.id == entry.item_id).first()
        if not item:
            continue
        expected_available = item.available
        if expected_available != entry.present:
            discrepancies.append({
                "item_id": entry.item_id,
                "name": item.name,
                "expected": expected_available,
                "found": entry.present,
                "notes": entry.notes
            })

    log = models.AuditLog(
        user_id=admin.id,
        action="stock_check",
        details=f"Checked {len(check.items)} items, {
            len(discrepancies)} discrepancies"
    )
    db.add(log)
    db.commit()
    return {"checked": len(check.items), "discrepancies": discrepancies}


@router.post("/locker-code")
def update_locker_code(
    update: schemas.LockerCodeUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user)
):
    code = models.LockerCode(code=update.code, updated_by=admin.id)
    db.add(code)
    log = models.AuditLog(
        user_id=admin.id, action="locker_code_updated", details=f"New code set")
    db.add(log)
    db.commit()
    return {"message": "Locker code updated"}


@router.get("/locker-code")
def get_locker_code(db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    code = db.query(models.LockerCode).order_by(
        models.LockerCode.id.desc()).first()
    return {"code": code.code if code else None, "updated_at": code.updated_at if code else None}


@router.get("/audit-log")
def audit_log(
    limit: int = 100,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user)
):
    logs = db.query(models.AuditLog).order_by(
        models.AuditLog.timestamp.desc()).limit(limit).all()
    return logs


@router.post("/check-overdue")
def check_overdue(db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    now = datetime.utcnow()
    overdue_loans = db.query(models.Loan).filter(
        models.Loan.returned == False,
        models.Loan.due_date < now
    ).all()

    locked = []
    for loan in overdue_loans:
        user = db.query(models.User).filter(
            models.User.id == loan.user_id).first()
        if user and not user.is_locked:
            user.is_locked = True
            items = [db.query(models.Item).get(
                i).name for i in loan.item_ids if db.query(models.Item).get(i)]
            send_overdue_notice(user.email, items)
            locked.append(user.email)
            log = models.AuditLog(
                user_id=admin.id, action="auto_locked", details=f"Overdue: {user.email}")
            db.add(log)

    db.commit()
    return {"locked_users": locked}
