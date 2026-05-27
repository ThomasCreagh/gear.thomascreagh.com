from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from database import get_db
import models
import schemas
from auth import get_approved_user, get_admin_user

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=List[schemas.ItemOut])
def list_items(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_approved_user)
):
    return db.query(models.Item).all()


@router.post("", response_model=schemas.ItemOut)
def create_item(
    item: schemas.ItemCreate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user)
):
    db_item = models.Item(**item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    log = models.AuditLog(
        user_id=admin.id, action="item_created", details=f"Item: {item.name}")
    db.add(log)
    db.commit()
    return db_item


@router.put("/{item_id}", response_model=schemas.ItemOut)
def update_item(
    item_id: int,
    item: schemas.ItemUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user)
):
    db_item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    for k, v in item.dict(exclude_none=True).items():
        setattr(db_item, k, v)
    db.commit()
    db.refresh(db_item)
    return db_item


@router.delete("/{item_id}")
def delete_item(
    item_id: int,
    db: Session = Depends(get_db),
    admin: models.User = Depends(get_admin_user)
):
    db_item = db.query(models.Item).filter(models.Item.id == item_id).first()
    if not db_item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(db_item)
    db.commit()
    return {"message": "Deleted"}
