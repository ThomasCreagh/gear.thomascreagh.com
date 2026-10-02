from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
import models
import schemas
from auth import get_approved_user, get_admin_user

router = APIRouter(prefix="/items", tags=["items"])


def validate_group_items(item_ids: List[int], db: Session):
    unique_ids = list(dict.fromkeys(item_ids))
    if not unique_ids:
        raise HTTPException(status_code=400, detail="A gear group must include at least one item")
    found = db.query(models.Item).filter(models.Item.id.in_(unique_ids)).count()
    if found != len(unique_ids):
        raise HTTPException(status_code=400, detail="One or more selected items do not exist")
    return unique_ids


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
    db_group = models.GearGroup(name=name, item_ids=validate_group_items(group.item_ids, db))
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
    group.item_ids = validate_group_items(update.item_ids, db)
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
