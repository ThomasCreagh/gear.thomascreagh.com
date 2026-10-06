from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from typing import List
import os
import shutil
import uuid
from config import read_secret

from database import get_db
import models
import schemas
from auth import get_approved_user, get_admin_user

router = APIRouter(prefix="/items", tags=["items"])
UPLOAD_DIR = read_secret("UPLOAD_DIR", "uploads")
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


@router.post("/{item_id}/image", response_model=schemas.ItemOut)
def upload_item_image(item_id: int, image: UploadFile = File(...), db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    item = db.get(models.Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Upload a JPEG, PNG, WebP, or GIF image")
    ext = os.path.splitext(image.filename or "")[1].lower() or ".jpg"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = f"gear-{uuid.uuid4()}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    with open(path, "wb") as destination:
        shutil.copyfileobj(image.file, destination)
    item.image_path = filename
    db.add(models.AuditLog(user_id=admin.id, action="item_image_uploaded", details=f"Item {item_id}"))
    db.commit()
    db.refresh(item)
    return item


def validate_group_items(item_ids: List[int], db: Session):
    unique_ids = list(dict.fromkeys(item_ids))
    if not unique_ids:
        raise HTTPException(status_code=400, detail="A gear group must include at least one item")
    found = db.query(models.Item).filter(models.Item.id.in_(unique_ids)).count()
    if found != len(unique_ids):
        raise HTTPException(status_code=400, detail="One or more selected items do not exist")
    return unique_ids


def validate_group_ids(group_ids: List[int], db: Session, current_id: int | None = None):
    unique_ids = list(dict.fromkeys(group_ids or []))
    if current_id in unique_ids:
        raise HTTPException(status_code=400, detail="A gear group cannot contain itself")
    if unique_ids and db.query(models.GearGroup).filter(models.GearGroup.id.in_(unique_ids)).count() != len(unique_ids):
        raise HTTPException(status_code=400, detail="One or more selected sub-groups do not exist")
    return unique_ids


@router.post("/groups/{group_id}/image", response_model=schemas.GearGroupOut)
def upload_group_image(group_id: int, image: UploadFile = File(...), db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    group = db.get(models.GearGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Gear group not found")
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Upload a JPEG, PNG, WebP, or GIF image")
    ext = os.path.splitext(image.filename or "")[1].lower() or ".jpg"
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = f"gear-group-{uuid.uuid4()}{ext}"
    path = os.path.join(UPLOAD_DIR, filename)
    with open(path, "wb") as destination:
        shutil.copyfileobj(image.file, destination)
    group.image_path = filename
    db.add(models.AuditLog(user_id=admin.id, action="gear_group_image_uploaded", details=f"Gear group {group_id}"))
    db.commit()
    db.refresh(group)
    return group


@router.get("/groups", response_model=List[schemas.GearGroupOut])
def list_gear_groups(db: Session = Depends(get_db), current_user: models.User = Depends(get_approved_user)):
    return db.query(models.GearGroup).order_by(models.GearGroup.name).all()


@router.get("/groups/all", response_model=List[schemas.GearGroupOut])
def list_all_gear_groups(db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    return db.query(models.GearGroup).order_by(models.GearGroup.name).all()


@router.post("/groups", response_model=schemas.GearGroupOut)
def create_gear_group(group: schemas.GearGroupCreate, db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    name = group.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="A group name is required")
    if db.query(models.GearGroup).filter(models.GearGroup.name == name).first():
        raise HTTPException(status_code=400, detail="A group with that name already exists")
    if not group.item_ids and not group.group_ids:
        raise HTTPException(status_code=400, detail="Add at least one item or sub-group")
    db_group = models.GearGroup(
        name=name,
        item_ids=validate_group_items(group.item_ids, db) if group.item_ids else [],
        group_ids=validate_group_ids(group.group_ids, db),
    )
    db.add(db_group)
    db.add(models.AuditLog(user_id=admin.id, action="gear_group_created", details=f"{name}: {db_group.item_ids}"))
    db.commit()
    db.refresh(db_group)
    return db_group


@router.put("/groups/{group_id}", response_model=schemas.GearGroupOut)
def update_gear_group(group_id: int, update: schemas.GearGroupCreate, db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    group = db.query(models.GearGroup).filter(models.GearGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Gear group not found")
    name = update.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="A group name is required")
    same_name_group = db.query(models.GearGroup).filter(models.GearGroup.name == name).first()
    if same_name_group and same_name_group.id != group_id:
        raise HTTPException(status_code=400, detail="A group with that name already exists")
    group.name = name
    if not update.item_ids and not update.group_ids:
        raise HTTPException(status_code=400, detail="Add at least one item or sub-group")
    group.item_ids = validate_group_items(update.item_ids, db) if update.item_ids else []
    group.group_ids = validate_group_ids(update.group_ids, db, group_id)
    db.add(models.AuditLog(user_id=admin.id, action="gear_group_updated", details=f"{name}: {group.item_ids}"))
    db.commit()
    db.refresh(group)
    return group


@router.delete("/groups/{group_id}")
def delete_gear_group(group_id: int, db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    group = db.query(models.GearGroup).filter(models.GearGroup.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Gear group not found")
    db.delete(group)
    db.add(models.AuditLog(user_id=admin.id, action="gear_group_deleted", details=f"{group.name}: {group.item_ids}"))
    db.commit()
    return {"message": "Gear group deleted"}


@router.get("", response_model=List[schemas.ItemOut])
def list_items(db: Session = Depends(get_db), current_user: models.User = Depends(get_approved_user)):
    return db.query(models.Item).filter(models.Item.status == "active").order_by(models.Item.tag).all()


@router.get("/all", response_model=List[schemas.ItemOut])
def list_all_items(db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    return db.query(models.Item).order_by(models.Item.tag).all()


@router.post("", response_model=schemas.ItemOut)
def create_item(item: schemas.ItemCreate, db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    db_item = models.Item(**item.dict())
    db.add(db_item)
    db.add(models.AuditLog(user_id=admin.id,
           action="item_created", details=f"Item: {item.name}"))
    db.commit()
    db.refresh(db_item)
    return db_item


@router.put("/{item_id}", response_model=schemas.ItemOut)
def update_item(item_id: int, item: schemas.ItemUpdate, db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    db_item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    for k, v in item.dict(exclude_none=True).items():
        setattr(db_item, k, v)
    db.add(models.AuditLog(user_id=admin.id, action="item_updated",
           details=f"Item {item_id}: {item.dict(exclude_none=True)}"))
    db.commit()
    db.refresh(db_item)
    return db_item


@router.delete("/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    db_item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(db_item)
    db.add(models.AuditLog(user_id=admin.id,
           action="item_deleted", details=f"Item {item_id}"))
    db.commit()
    return {"message": "Deleted"}
