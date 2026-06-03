import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
import shutil
import uuid

from database import get_db
import models, schemas
from auth import get_approved_user, get_admin_user
from mailer import send_loan_approved, send_loan_pending_admin

router = APIRouter(prefix="/loans", tags=["loans"])

MAX_LOAN_DAYS = int(os.getenv("MAX_LOAN_DAYS", 14))
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def save_photo(file: UploadFile) -> str:
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "jpg"
    filename = f"{uuid.uuid4()}.{ext}"
    path = f"{UPLOAD_DIR}/{filename}"
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return path


def get_locker_codes(db: Session, lockers: List[str]) -> dict:
    codes = {}
    for locker in lockers:
        row = (
            db.query(models.LockerCode)
            .filter(models.LockerCode.locker == locker)
            .order_by(models.LockerCode.id.desc())
            .first()
        )
        codes[locker] = row.code if row else "0000"
    return codes


@router.post("", response_model=schemas.LoanOut)
def create_loan(
    loan: schemas.LoanCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_approved_user)
):
    if loan.days > MAX_LOAN_DAYS or loan.days < 1:
        raise HTTPException(status_code=400, detail=f"Days must be 1-{MAX_LOAN_DAYS}")

    items = []
    for item_id in loan.item_ids:
        item = db.query(models.Item).filter(
            models.Item.id == item_id,
            models.Item.available == True,
            models.Item.retired == False,
        ).first()
        if not item:
            raise HTTPException(status_code=400, detail=f"Item {item_id} not available")
        items.append(item)

    # Determine which lockers are involved
    involved_lockers = list(set(i.locker for i in items if i.locker))
    due_date = datetime.utcnow() + timedelta(days=loan.days)

    if current_user.auto_approve:
        # Issue locker codes immediately
        locker_codes = get_locker_codes(db, involved_lockers)
        status = "active"
        for item in items:
            item.available = False
    else:
        locker_codes = {}
        status = "pending"

    db_loan = models.Loan(
        user_id=current_user.id,
        item_ids=loan.item_ids,
        locker_codes=locker_codes,
        lockers=involved_lockers,
        due_date=due_date,
        status=status,
    )
    db.add(db_loan)
    db.add(models.AuditLog(
        user_id=current_user.id,
        action="loan_created",
        details=f"status={status}, items={loan.item_ids}, lockers={involved_lockers}"
    ))
    db.commit()
    db.refresh(db_loan)

    item_names = [i.name for i in items]
    if current_user.auto_approve:
        send_loan_approved(current_user.email, locker_codes, due_date.strftime("%Y-%m-%d"), item_names)
    else:
        send_loan_pending_admin(current_user.email, item_names)

    return db_loan


@router.post("/{loan_id}/photos")
def upload_photo(
    loan_id: int,
    locker: str = Form(...),
    photo_type: str = Form(...),  # borrow | return
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_approved_user)
):
    loan = db.query(models.Loan).filter(
        models.Loan.id == loan_id,
        models.Loan.user_id == current_user.id
    ).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if locker not in (loan.lockers or []):
        raise HTTPException(status_code=400, detail=f"Locker {locker} not part of this loan")
    if photo_type not in ("borrow", "return"):
        raise HTTPException(status_code=400, detail="photo_type must be borrow or return")

    # Replace existing photo for same locker+type if exists
    existing = db.query(models.LoanPhoto).filter(
        models.LoanPhoto.loan_id == loan_id,
        models.LoanPhoto.locker == locker,
        models.LoanPhoto.photo_type == photo_type,
    ).first()
    if existing:
        if os.path.exists(existing.file_path):
            os.remove(existing.file_path)
        db.delete(existing)

    path = save_photo(photo)
    db_photo = models.LoanPhoto(
        loan_id=loan_id,
        locker=locker,
        photo_type=photo_type,
        file_path=path,
    )
    db.add(db_photo)
    db.add(models.AuditLog(
        user_id=current_user.id,
        action=f"photo_{photo_type}",
        details=f"Loan {loan_id}, locker: {locker}"
    ))
    db.commit()
    return {"message": "Photo uploaded", "path": path}


@router.post("/{loan_id}/return")
def return_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_approved_user)
):
    loan = db.query(models.Loan).filter(
        models.Loan.id == loan_id,
        models.Loan.user_id == current_user.id
    ).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.status == "returned":
        raise HTTPException(status_code=400, detail="Already returned")

    # Enforce all return photos uploaded
    required_lockers = set(loan.lockers or [])
    uploaded_lockers = set(
        p.locker for p in loan.photos if p.photo_type == "return"
    )
    missing = required_lockers - uploaded_lockers
    if missing:
        labels = [models.LOCKER_LABELS.get(l, l) for l in missing]
        raise HTTPException(
            status_code=400,
            detail=f"Missing return photos for: {', '.join(labels)}"
        )

    loan.status = "returned"
    loan.returned_at = datetime.utcnow()

    for item_id in loan.item_ids:
        item = db.query(models.Item).filter(models.Item.id == item_id).first()
        if item:
            item.available = True

    db.add(models.AuditLog(
        user_id=current_user.id,
        action="returned",
        details=f"Loan {loan_id}"
    ))
    db.commit()
    return {"message": "Return logged", "returned_at": loan.returned_at}


@router.get("/my", response_model=List[schemas.LoanOut])
def my_loans(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_approved_user)
):
    return db.query(models.Loan).filter(models.Loan.user_id == current_user.id).all()


# Admin: approve/deny pending loan
@router.post("/{loan_id}/approve")
def approve_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user)
):
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan or loan.status != "pending":
        raise HTTPException(status_code=404, detail="Pending loan not found")

    items = [db.query(models.Item).get(i) for i in loan.item_ids]
    for item in items:
        if item:
            item.available = False

    locker_codes = get_locker_codes(db, loan.lockers or [])
    loan.locker_codes = locker_codes
    loan.status = "active"

    db.add(models.AuditLog(user_id=admin.id, action="loan_approved", details=f"Loan {loan_id}"))
    db.commit()

    user = db.query(models.User).get(loan.user_id)
    item_names = [i.name for i in items if i]
    send_loan_approved(user.email, locker_codes, loan.due_date.strftime("%Y-%m-%d"), item_names)
    return {"message": "Loan approved"}


@router.post("/{loan_id}/deny")
def deny_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user)
):
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan or loan.status != "pending":
        raise HTTPException(status_code=404, detail="Pending loan not found")

    loan.status = "denied"
    db.add(models.AuditLog(user_id=admin.id, action="loan_denied", details=f"Loan {loan_id}"))
    db.commit()
    return {"message": "Loan denied"}
