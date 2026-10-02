from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import secrets

from database import get_db
import models, schemas
from auth import get_admin_user, hash_password
from mailer import send_account_created
from services.overdue import send_overdue_reminders
from services.users import find_user_by_email, normalise_email

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=List[schemas.UserOut])
def list_users(db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    return db.query(models.User).all()


@router.post("/users")
def create_user(email: str, name: str = "", db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    email = normalise_email(email)
    if find_user_by_email(db, email):
        raise HTTPException(status_code=400, detail="Email already exists")
    temp_password = secrets.token_urlsafe(10)
    user = models.User(email=email, name=name.strip() or None, password_hash=hash_password(temp_password), is_approved=True)
    db.add(user)
    db.add(models.AuditLog(user_id=admin.id, action="user_created", details=f"Created: {email}"))
    db.commit()
    send_account_created(email, temp_password)
    return {"message": "User created", "email": email}


@router.put("/users/{user_id}", response_model=schemas.UserOut)
def update_user(user_id: int, update: schemas.UserUpdate, db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if update.email is not None:
        email = normalise_email(str(update.email))
        existing = find_user_by_email(db, email)
        if existing and existing.id != user_id:
            raise HTTPException(status_code=400, detail="Email already exists")
        user.email = email
    if update.name is not None:
        user.name = update.name.strip() or None
    db.add(models.AuditLog(user_id=admin.id, action="user_updated", details=f"User {user_id}"))
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{user_id}/approve")
def approve_user(user_id: int, db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_approved = True
    db.add(models.AuditLog(user_id=admin.id, action="user_approved", details=f"User {user_id}"))
    db.commit()
    return {"message": "User approved"}


@router.post("/users/{user_id}/lock")
def lock_user(user_id: int, db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_locked = not user.is_locked
    db.add(models.AuditLog(user_id=admin.id, action="user_locked" if user.is_locked else "user_unlocked", details=f"User {user_id}"))
    db.commit()
    return {"locked": user.is_locked}


@router.post("/users/{user_id}/auto-approve")
def toggle_auto_approve(user_id: int, db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.auto_approve = not user.auto_approve
    db.add(models.AuditLog(user_id=admin.id, action="auto_approve_toggled", details=f"User {user_id} → {user.auto_approve}"))
    db.commit()
    return {"auto_approve": user.auto_approve}


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    temp_password = secrets.token_urlsafe(10)
    user.password_hash = hash_password(temp_password)
    db.add(models.AuditLog(user_id=admin.id, action="password_reset", details=f"User {user_id}"))
    db.commit()
    send_account_created(user.email, temp_password)
    return {"message": "Password reset, email sent"}


@router.get("/loans")
def list_loans(active_only: bool = False, db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    q = db.query(models.Loan)
    if active_only:
        q = q.filter(models.Loan.status.in_(["pending_review", "active"]))
    loans = q.order_by(models.Loan.created_at.desc()).all()
    result = []
    for loan in loans:
        user = db.query(models.User).get(loan.user_id)
        items = [db.query(models.Item).get(i) for i in loan.item_ids]
        result.append({
            "id": loan.id,
            "user_email": user.email if user else "?",
            "user_id": loan.user_id,
            "item_ids": loan.item_ids,
            "item_names": [i.name for i in items if i],
            "lockers": loan.lockers,
            "due_date": loan.due_date,
            "start_date": loan.start_date,
            "status": loan.status,
            "loan_type": loan.loan_type,
            "created_at": loan.created_at,
            "returned_at": loan.returned_at,
            "photos": [
                {
                    "id": p.id,
                    "locker": p.locker,
                    "photo_type": p.photo_type,
                    "file_path": p.file_path,
                    "uploaded_at": p.uploaded_at,
                }
                for p in loan.photos
            ],
        })
    return result


@router.post("/stock-check")
def stock_check(check: schemas.StockCheckRequest, db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    discrepancies = []
    for entry in check.items:
        item = db.query(models.Item).filter(models.Item.id == entry.item_id).first()
        if not item:
            continue
        if item.available != entry.present:
            discrepancies.append({"item_id": entry.item_id, "name": item.name, "expected": item.available, "found": entry.present, "notes": entry.notes})
    db.add(models.AuditLog(user_id=admin.id, action="stock_check", details=f"Checked {len(check.items)}, {len(discrepancies)} discrepancies"))
    db.commit()
    return {"checked": len(check.items), "discrepancies": discrepancies}


@router.get("/audit-log")
def audit_log(limit: int = 100, db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    logs = db.query(models.AuditLog).order_by(models.AuditLog.timestamp.desc()).limit(limit).all()
    return [{"id": l.id, "user_id": l.user_id, "action": l.action, "details": l.details, "timestamp": l.timestamp} for l in logs]


@router.post("/check-overdue")
def check_overdue(db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    notified = send_overdue_reminders(db, admin.id)
    return {"notified_users": [reminder["user"] for reminder in notified], "count": len(notified)}
