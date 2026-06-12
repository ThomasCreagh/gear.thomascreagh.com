import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
import shutil
import uuid

from database import get_db
import models
import schemas
from auth import get_approved_user, get_admin_user
from mailer import send_loan_approved, send_loan_pending_admin
from config import read_secret

router = APIRouter(prefix="/loans", tags=["loans"])

MAX_LOAN_DAYS = int(os.getenv("MAX_LOAN_DAYS", 14))
UPLOAD_DIR = read_secret("UPLOAD_DIR", "uploads")
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


def get_verification_code(db: Session) -> str | None:
    row = (
        db.query(models.VerificationCode)
        .order_by(models.VerificationCode.id.desc())
        .first()
    )
    return row.code if row else None


# ---------------------------------------------------------------------------
# Create loan — user is at the locker, picks which lockers + how many days.
# No items selected yet; those are logged after opening the locker.
# ---------------------------------------------------------------------------
@router.post("", response_model=schemas.LoanOut)
def create_loan(
    loan: schemas.LoanCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_approved_user),
):
    if current_user.is_locked:
        raise HTTPException(
            status_code=403, detail="Your account is locked due to overdue items.")

    if loan.days > MAX_LOAN_DAYS or loan.days < 1:
        raise HTTPException(
            status_code=400, detail=f"Days must be 1–{MAX_LOAN_DAYS}")

    valid_lockers = set(models.LOCKERS)
    for locker in loan.lockers:
        if locker not in valid_lockers:
            raise HTTPException(
                status_code=400, detail=f"Invalid locker: {locker}")

    if not loan.lockers:
        raise HTTPException(
            status_code=400, detail="Select at least one locker")

    due_date = datetime.utcnow() + timedelta(days=loan.days)

    db_loan = models.Loan(
        user_id=current_user.id,
        item_ids=[],
        locker_codes=None,          # revealed only after verification
        lockers=loan.lockers,
        locker_verified=False,
        due_date=due_date,
        status="pending_verification",
    )
    db.add(db_loan)
    db.add(models.AuditLog(
        user_id=current_user.id,
        action="loan_created",
        details=f"lockers={loan.lockers}, days={loan.days}",
    ))
    db.commit()
    db.refresh(db_loan)
    return db_loan


# ---------------------------------------------------------------------------
# Verify — user enters the single in-person code; receives locker unlock codes.
# Can be called for both borrow (pending_verification) and return (active).
# ---------------------------------------------------------------------------
@router.post("/{loan_id}/verify", response_model=schemas.LoanVerifyResponse)
def verify_loan(
    loan_id: int,
    body: schemas.LoanVerifyRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_approved_user),
):
    loan = db.query(models.Loan).filter(
        models.Loan.id == loan_id,
        models.Loan.user_id == current_user.id,
    ).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.status not in ("pending_verification", "active"):
        raise HTTPException(
            status_code=400, detail="This loan cannot be verified at this stage")

    correct = get_verification_code(db)
    if correct is None:
        raise HTTPException(
            status_code=503, detail="Verification code not configured. Contact Tom.")
    if body.verification_code.strip() != correct.strip():
        raise HTTPException(
            status_code=403, detail="Incorrect verification code")

    # Reveal locker codes and activate
    locker_codes = get_locker_codes(db, loan.lockers or [])
    loan.locker_codes = locker_codes
    loan.locker_verified = True

    if loan.status == "pending_verification":
        loan.status = "active"
        db.add(models.AuditLog(
            user_id=current_user.id,
            action="loan_verified",
            details=f"Loan {loan_id} verified, codes issued for {
                loan.lockers}",
        ))

    db.commit()
    db.refresh(loan)
    return schemas.LoanVerifyResponse(locker_codes=locker_codes, due_date=loan.due_date)


# ---------------------------------------------------------------------------
# Update loan — log which items were actually taken
# ---------------------------------------------------------------------------
@router.put("/{loan_id}", response_model=schemas.LoanOut)
def update_loan(
    loan_id: int,
    update: schemas.LoanUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_approved_user),
):
    loan = db.query(models.Loan).filter(
        models.Loan.id == loan_id,
        models.Loan.user_id == current_user.id,
    ).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.status != "active":
        raise HTTPException(
            status_code=400, detail="Can only edit active loans")

    changes = []

    if update.due_date is not None:
        loan.due_date = update.due_date
        changes.append(f"due_date={update.due_date.strftime('%Y-%m-%d')}")

    if update.item_ids is not None:
        removed_ids = set(loan.item_ids) - set(update.item_ids)
        added_ids = set(update.item_ids) - set(loan.item_ids)

        for item_id in removed_ids:
            item = db.query(models.Item).filter(
                models.Item.id == item_id).first()
            if item:
                item.available = True

        for item_id in added_ids:
            item = db.query(models.Item).filter(
                models.Item.id == item_id,
                models.Item.available == True,
                models.Item.status == "active",
            ).first()
            if not item:
                raise HTTPException(status_code=400, detail=f"Item {
                                    item_id} not available")
            item.available = False

        loan.item_ids = update.item_ids
        changes.append(f"item_ids={update.item_ids}")

    db.add(models.AuditLog(
        user_id=current_user.id,
        action="loan_updated",
        details=f"Loan {loan_id}: {', '.join(changes)}",
    ))
    db.commit()
    db.refresh(loan)
    return loan


# ---------------------------------------------------------------------------
# Upload photo
# ---------------------------------------------------------------------------
@router.post("/{loan_id}/photos")
def upload_photo(
    loan_id: int,
    locker: str = Form(...),
    photo_type: str = Form(...),   # borrow | return
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_approved_user),
):
    loan = db.query(models.Loan).filter(
        models.Loan.id == loan_id,
        models.Loan.user_id == current_user.id,
    ).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if locker not in (loan.lockers or []):
        raise HTTPException(status_code=400, detail=f"Locker '{
                            locker}' not part of this loan")
    if photo_type not in ("borrow", "return"):
        raise HTTPException(
            status_code=400, detail="photo_type must be 'borrow' or 'return'")

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
    db.add(models.LoanPhoto(
        loan_id=loan_id,
        locker=locker,
        photo_type=photo_type,
        file_path=path,
    ))
    db.add(models.AuditLog(
        user_id=current_user.id,
        action=f"photo_{photo_type}",
        details=f"Loan {loan_id}, locker: {locker}",
    ))
    db.commit()
    return {"message": "Photo uploaded", "path": path}


# ---------------------------------------------------------------------------
# Return loan
# ---------------------------------------------------------------------------
@router.post("/{loan_id}/return")
def return_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_approved_user),
):
    loan = db.query(models.Loan).filter(
        models.Loan.id == loan_id,
        models.Loan.user_id == current_user.id,
    ).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    if loan.status == "returned":
        raise HTTPException(status_code=400, detail="Already returned")
    if loan.status != "active":
        raise HTTPException(status_code=400, detail="Loan is not active")

    required_lockers = set(loan.lockers or [])
    uploaded_lockers = {
        p.locker for p in loan.photos if p.photo_type == "return"}
    missing = required_lockers - uploaded_lockers
    if missing:
        labels = [models.LOCKER_LABELS.get(l, l) for l in missing]
        raise HTTPException(status_code=400, detail=f"Missing return photos for: {
                            ', '.join(labels)}")

    loan.status = "returned"
    loan.returned_at = datetime.utcnow()
    # Hide locker codes now that return is complete
    loan.locker_codes = None

    for item_id in loan.item_ids:
        item = db.query(models.Item).filter(models.Item.id == item_id).first()
        if item:
            item.available = True

    db.add(models.AuditLog(
        user_id=current_user.id,
        action="returned",
        details=f"Loan {loan_id}",
    ))
    db.commit()
    return {"message": "Return logged", "returned_at": loan.returned_at}


# ---------------------------------------------------------------------------
# My loans
# ---------------------------------------------------------------------------
@router.get("/my", response_model=List[schemas.LoanOut])
def my_loans(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_approved_user),
):
    return (
        db.query(models.Loan)
        .filter(models.Loan.user_id == current_user.id)
        .order_by(models.Loan.created_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Admin: set the global verification code
# ---------------------------------------------------------------------------
@router.get("/admin/verification-code")
def get_verification_code_admin(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user),
):
    code = get_verification_code(db)
    return {"code": code or "Not set"}


@router.post("/admin/verification-code")
def set_verification_code(
    body: schemas.VerificationCodeUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user),
):
    db.add(models.VerificationCode(code=body.code, updated_by=admin.id))
    db.add(models.AuditLog(
        user_id=admin.id,
        action="verification_code_updated",
        details="Global verification code changed",
    ))
    db.commit()
    return {"message": "Verification code updated"}


# ---------------------------------------------------------------------------
# Admin: approve / deny (kept for edge cases; codes still gate-kept by verify)
# ---------------------------------------------------------------------------
@router.post("/{loan_id}/approve")
def approve_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user),
):
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    db.add(models.AuditLog(user_id=admin.id,
           action="loan_approved", details=f"Loan {loan_id}"))
    db.commit()
    return {"message": "Loan noted"}


@router.post("/{loan_id}/deny")
def deny_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user),
):
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan or loan.status not in ("pending_verification", "active"):
        raise HTTPException(status_code=404, detail="Loan not found")
    loan.status = "denied"
    db.add(models.AuditLog(user_id=admin.id,
           action="loan_denied", details=f"Loan {loan_id}"))
    db.commit()
    return {"message": "Loan denied"}
