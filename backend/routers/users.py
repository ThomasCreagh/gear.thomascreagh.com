from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import timedelta

from database import get_db
import models
import schemas
from auth import verify_password, create_access_token, get_current_user, hash_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenResponse)
def login(request: schemas.LoginRequest, db: Session = Depends(get_db)):
    # Accepts JSON: {"email": "...", "password": "..."}
    user = db.query(models.User).filter(
        models.User.email == request.email).first()
    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=401, detail="Invalid email or password")

    token = create_access_token({"sub": str(user.id)})

    # Audit log
    log = models.AuditLog(user_id=user.id, action="login",
                          details=f"Login from {request.email}")
    db.add(log)
    db.commit()

    return {"access_token": token}


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.post("/change-password")
def change_password(
    old_password: str,
    new_password: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not verify_password(old_password, current_user.password_hash):
        raise HTTPException(
            status_code=400, detail="Incorrect current password")
    current_user.password_hash = hash_password(new_password)
    db.commit()
    return {"message": "Password changed"}
