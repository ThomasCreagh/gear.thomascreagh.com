from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from constants import CATEGORIES, CATEGORY_LABELS, LOCKERS, LOCKER_LABELS

# Auth


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

# Users


class UserOut(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    is_admin: bool
    is_approved: bool
    is_locked: bool
    auto_approve: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None

# Items


class ItemCreate(BaseModel):
    name: str
    description: Optional[str] = None
    tag: Optional[str] = None
    locker: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = "active"
    manufactured_date: Optional[str] = None
    condition_notes: Optional[str] = None
    borrowed_by_email: Optional[str] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tag: Optional[str] = None
    locker: Optional[str] = None
    category: Optional[str] = None
    available: Optional[bool] = None
    status: Optional[str] = None
    manufactured_date: Optional[str] = None
    condition_notes: Optional[str] = None
    borrowed_by_email: Optional[str] = None


class ItemOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    image_path: Optional[str] = None
    tag: Optional[str]
    locker: Optional[str]
    category: Optional[str]
    available: bool
    status: str
    manufactured_date: Optional[str]
    condition_notes: Optional[str]
    borrowed_by_email: Optional[str]

    class Config:
        from_attributes = True


class GearGroupCreate(BaseModel):
    name: str
    item_ids: List[int] = []
    group_ids: List[int] = []


class GearGroupOut(BaseModel):
    id: int
    name: str
    item_ids: List[int]
    group_ids: List[int] = []

    class Config:
        from_attributes = True

# Photos


class LoanPhotoOut(BaseModel):
    id: int
    loan_id: int
    locker: str
    photo_type: str
    file_path: str
    uploaded_at: datetime

    class Config:
        from_attributes = True

# Loans


class LoanCreate(BaseModel):
    lockers: List[str]
    days: Optional[int] = None
    start_date: Optional[datetime] = None
    loan_type: Optional[str] = "standard"  # standard | twall


class LoanUpdate(BaseModel):
    item_ids: Optional[List[int]] = None
    due_date: Optional[datetime] = None


class LoanOut(BaseModel):
    id: int
    user_id: int
    item_ids: List[int]
    lockers: Optional[List[str]]
    locker_codes: Optional[dict] = None
    door_code: Optional[str] = None
    due_date: Optional[datetime]
    start_date: Optional[datetime] = None
    status: str
    loan_type: str = "standard"
    created_at: datetime
    returned_at: Optional[datetime]
    photos: List[LoanPhotoOut] = []

    class Config:
        from_attributes = True

# Admin


class LockerCodeUpdate(BaseModel):
    locker: str
    code: str
