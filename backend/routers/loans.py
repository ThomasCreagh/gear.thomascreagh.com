import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
import shutil
import uuid

from database import get_db
import models
import schemas
from auth import get_approved_user
from mailer import send_loan_approved

router = APIRouter(prefix="/loans", tags=["loans"])

MAX_LOAN_DAYS = int(os.getenv("MAX_LOAN_DAYS", 14))
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def save_photo(file: UploadFile) -> str:
    ext = file.filename.split(".")[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    path = f"{UPLOAD_DIR}/{filename}"
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return path


def get_locker_code(db: Session, locker: str) -> str:
    code = (
        db.query(models.LockerCode)
        .filter(models.LockerCode.locker == locker)
        .order_by(models.LockerCode.id.desc())
        .first()
    )
    return code.code if code else "0000"


@router.post("", response_model=schemas.LoanOut)
def create_loan(
    loan: schemas.LoanCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_approved_user)
):
    if loan.days > MAX_LOAN_DAYS or loan.days < 1:
        raise HTTPException(
            status_code=400, detail=f"Days must be 1-{MAX_LOAN_DAYS}")

    # Validate all items available
    items = []
    for item_id in loan.item_ids:
        item = db.query(models.Item).filter(
            models.Item.id == item_id,
            models.Item.available == True
        ).first()
        if not item:
            raise HTTPException(status_code=400, detail=f"Item {
                                item_id} not available")
        items.append(item)

    # Determine locker from first item (items in same locker assumed)
    locker = items[0].locker or "upper"
    locker_code = get_locker_code(db, locker)
    due_date = datetime.utcnow() + timedelta(days=loan.days)

    db_loan = models.Loan(
        user_id=current_user.id,
        item_ids=loan.item_ids,
        locker_code=locker_code,
        locker=locker,
        due_date=due_date
    )
    db.add(db_loan)

    for item in items:
        item.available = False

    log = models.AuditLog(
        user_id=current_user.id,
        action="loan_created",
        details=f"Items: {loan.item_ids}, locker: {locker}, due: {due_date}"
    )
    db.add(log)
    db.commit()
    db.refresh(db_loan)

    item_names = [i.name for i in items]
    send_loan_approved(current_user.email, locker_code,
                       due_date.strftime("%Y-%m-%d"), item_names)

    return db_loan


@router.post("/{loan_id}/borrow-photo")
def upload_borrow_photo(
    loan_id: int,
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

    loan.borrow_photo = save_photo(photo)
    db.add(models.AuditLog(user_id=current_user.id,
           action="borrow_photo", details=f"Loan {loan_id}"))
    db.commit()
    return {"message": "Photo uploaded"}


@router.post("/{loan_id}/return")
def return_loan(
    loan_id: int,
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
    if loan.returned:
        raise HTTPException(status_code=400, detail="Already returned")

    loan.return_photo = save_photo(photo)
    loan.returned = True
    loan.returned_at = datetime.utcnow()

    for item_id in loan.item_ids:
        item = db.query(models.Item).filter(models.Item.id == item_id).first()
        if item:
            item.available = True

    db.add(models.AuditLog(
        user_id=current_user.id,
        action="returned",
        details=f"Loan {loan_id}, items: {loan.item_ids}"
    ))
    db.commit()
    return {"message": "Return logged", "returned_at": loan.returned_at}


@router.get("/my", response_model=List[schemas.LoanOut])
def my_loans(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_approved_user)
):
    return db.query(models.Loan).filter(models.Loan.user_id == current_user.id).all()
