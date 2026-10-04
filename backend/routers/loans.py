import os
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session, selectinload
from typing import List
from datetime import datetime, timedelta
import shutil
import uuid

from database import get_db
import models
import schemas
from auth import get_approved_user, get_admin_user
from config import read_secret
from services.overdue import send_overdue_reminders
from services.inventory import latest_locker_codes, set_items_available

router = APIRouter(prefix="/loans", tags=["loans"])

MAX_LOAN_DAYS = int(os.getenv("MAX_LOAN_DAYS", 14))
TWALL_DOOR_LOCKER = "twall_door"
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
    return {locker: row.code for locker, row in latest_locker_codes(db, lockers).items()}


def expand_gear_group(group, db: Session, seen=None, groups_by_id=None):
    # Load the small group catalogue once, rather than querying each child.
    if groups_by_id is None:
        groups_by_id = {g.id: g for g in db.query(models.GearGroup).all()}
    seen = seen or set()
    if group.id in seen:
        raise HTTPException(status_code=400, detail="Circular gear group nesting detected")
    seen.add(group.id)
    ids = list(group.item_ids or [])
    for child_id in (group.group_ids or []):
        child = groups_by_id.get(child_id)
        if child:
            ids.extend(expand_gear_group(child, db, seen.copy(), groups_by_id))
    return list(dict.fromkeys(ids))


# ---------------------------------------------------------------------------
# Create a loan or future outdoor booking.  Physical locker verification is no
# longer part of borrowing: trusted users can log what they take directly.
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

    loan_type = loan.loan_type or "standard"
    if loan_type not in ("standard", "twall"):
        raise HTTPException(status_code=400, detail="Invalid loan type")
    days = loan.days or 1
    if days > MAX_LOAN_DAYS or days < 1:
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

    now = datetime.utcnow()
    if loan_type == "twall":
        start_date = now
        days = 1
    else:
        start_date = loan.start_date or now
        # Outdoor bookings must be today or later; dates are stored at midnight
        # when chosen through the date input.
        if start_date.date() < now.date():
            raise HTTPException(status_code=400, detail="Outdoor bookings cannot start in the past")
    due_date = start_date + timedelta(days=days)
    initial_status = "active" if current_user.auto_approve else "pending_review"
    codes = get_locker_codes(db, [*loan.lockers, TWALL_DOOR_LOCKER])
    locker_codes = {locker: codes[locker] for locker in loan.lockers if locker in codes}

    db_loan = models.Loan(
        user_id=current_user.id,
        item_ids=[],
        lockers=loan.lockers,
        due_date=due_date,
        status=initial_status,
        loan_type=loan_type,
        start_date=start_date,
        locker_codes=locker_codes or None,
        door_code=codes.get(TWALL_DOOR_LOCKER),
    )
    db.add(db_loan)
    db.add(models.AuditLog(
        user_id=current_user.id,
        action="loan_created",
        details=f"type={'trinity_wall' if loan_type == 'twall' else 'outside'}, lockers={loan.lockers}, start={start_date.isoformat()}, days={days}, status={initial_status}",
    ))
    db.commit()
    db.refresh(db_loan)
    return db_loan


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

        # Validate the complete addition before changing availability. Lock in ID
        # order so concurrent borrowers cannot both take the same available item.
        changed_ids = removed_ids | added_ids
        items_by_id = {
            item.id: item for item in db.query(models.Item).filter(
                models.Item.id.in_(changed_ids)
            ).order_by(models.Item.id).with_for_update().all()
        } if changed_ids else {}
        for item_id in added_ids:
            item = items_by_id.get(item_id)
            if not item or not item.available or item.status != "active":
                raise HTTPException(status_code=400, detail=f"Item {item_id} not available")
        for item_id, item in items_by_id.items():
            item.available = item_id in removed_ids

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


@router.post("/{loan_id}/gear-groups/{group_id}", response_model=schemas.LoanOut)
def add_gear_group_to_loan(
    loan_id: int,
    group_id: int,
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
        raise HTTPException(status_code=400, detail="Can only add a gear group to an active loan")

    group = db.query(models.GearGroup).filter(models.GearGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Gear group not found or has no items")

    expanded_ids = expand_gear_group(group, db)
    if not expanded_ids:
        raise HTTPException(status_code=404, detail="Gear group has no items")
    items = db.query(models.Item).filter(models.Item.id.in_(expanded_ids)).order_by(models.Item.id).with_for_update().all()
    items_by_id = {item.id: item for item in items}
    missing_ids = set(expanded_ids) - set(items_by_id)
    if missing_ids:
        raise HTTPException(status_code=400, detail=f"{group.name} contains deleted gear")
    unavailable = [item for item in items if not item.available or item.status != "active"]
    if unavailable:
        raise HTTPException(status_code=400, detail=f"{group.name} is not fully available")
    wrong_locker = [item for item in items if item.locker and item.locker not in (loan.lockers or [])]
    if wrong_locker:
        raise HTTPException(status_code=400, detail=f"Open the required locker(s) before adding {group.name}")

    new_item_ids = list(dict.fromkeys((loan.item_ids or []) + expanded_ids))
    for item in items:
        item.available = False
    loan.item_ids = new_item_ids
    db.add(models.AuditLog(
        user_id=current_user.id,
        action="gear_group_added_to_loan",
        details=f"Loan {loan_id}: {group.name} ({group.item_ids})",
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
    return {"message": "Photo uploaded", "path": path, "loan": schemas.LoanOut.model_validate(loan)}


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

    # T-wall loans skip photo requirement
    if loan.loan_type != "twall":
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

    set_items_available(db, loan.item_ids, True)

    db.add(models.AuditLog(
        user_id=current_user.id,
        action="returned",
        details=f"Loan {loan_id}",
    ))
    db.commit()
    return {"message": "Return logged", "returned_at": loan.returned_at, "loan": schemas.LoanOut.model_validate(loan)}


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
        .options(selectinload(models.Loan.photos))
        .filter(models.Loan.user_id == current_user.id)
        .order_by(models.Loan.created_at.desc())
        .all()
    )


# ---------------------------------------------------------------------------
# Admin: approve / deny. Approval makes a requested loan active immediately.
# ---------------------------------------------------------------------------
@router.post("/{loan_id}/approve")
def approve_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user),
):
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan or loan.status != "pending_review":
        raise HTTPException(status_code=404, detail="No pending review for this loan")
    loan.status = "active"
    db.add(models.AuditLog(user_id=admin.id,
           action="loan_approved", details=f"Loan {loan_id}"))
    db.commit()
    return {"message": "Loan approved"}


@router.post("/{loan_id}/deny")
def deny_loan(
    loan_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user),
):
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan or loan.status not in ("pending_review", "active"):
        raise HTTPException(status_code=404, detail="Loan not found")
    loan.status = "denied"
    db.add(models.AuditLog(user_id=admin.id,
           action="loan_denied", details=f"Loan {loan_id}"))
    db.commit()
    return {"message": "Loan denied"}


# ---------------------------------------------------------------------------
# Admin: manually toggle a loan's returned state
# ---------------------------------------------------------------------------
@router.post("/{loan_id}/admin-toggle-return")
def admin_toggle_return(
    loan_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user),
):
    loan = db.query(models.Loan).filter(models.Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    if loan.status == "returned":
        # Mark as not returned — reopen as active, items go back to unavailable
        loan.status = "active"
        loan.returned_at = None
        set_items_available(db, loan.item_ids, False)
        action = "admin_marked_not_returned"
    elif loan.status == "active":
        loan.status = "returned"
        loan.returned_at = datetime.utcnow()
        set_items_available(db, loan.item_ids, True)
        action = "admin_marked_returned"
    else:
        raise HTTPException(status_code=400, detail=f"Cannot toggle return from status '{loan.status}'")

    db.add(models.AuditLog(user_id=admin.id, action=action, details=f"Loan {loan_id}"))
    db.commit()
    return {"message": "Loan status updated", "status": loan.status}


# ---------------------------------------------------------------------------
# Auto-close T-wall loans older than 24h.
# Shared by the admin trigger endpoint below and the in-app scheduler in main.py.
# triggered_by is an admin user id when called manually, None when called by the scheduler.
# ---------------------------------------------------------------------------
def run_twall_autoclose(db: Session, triggered_by: int | None = None) -> list[int]:
    cutoff = datetime.utcnow() - timedelta(hours=24)
    loans = db.query(models.Loan).filter(
        models.Loan.loan_type == "twall",
        models.Loan.status == "active",
        models.Loan.created_at <= cutoff,
    ).all()

    set_items_available(db, [item_id for loan in loans for item_id in (loan.item_ids or [])], True)
    closed = []
    for loan in loans:
        loan.status = "returned"
        loan.returned_at = datetime.utcnow()
        db.add(models.AuditLog(
            user_id=triggered_by,
            action="twall_autoclosed",
            details=f"Loan {loan.id} auto-closed after 24h",
        ))
        closed.append(loan.id)

    db.commit()
    return closed


@router.post("/admin/twall-autoclose")
def twall_autoclose(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user),
):
    closed = run_twall_autoclose(db, triggered_by=admin.id)
    return {"closed": closed, "count": len(closed)}


# ---------------------------------------------------------------------------
# Send overdue return reminders (call from cron or admin panel daily)
# ---------------------------------------------------------------------------
@router.post("/admin/send-overdue-emails")
def send_overdue_emails(
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user),
):
    notified = send_overdue_reminders(db, admin.id)
    return {"notified": notified, "count": len(notified)}
