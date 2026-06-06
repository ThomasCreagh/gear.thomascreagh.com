from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict
from datetime import datetime

LOCKERS = ["outdoor", "top", "bottom", "pad"]
LOCKER_LABELS = {
    "outdoor": "Outdoor Locker",
    "top": "Top Locker",
    "bottom": "Bottom Locker",
    "pad": "Pad Stash",
}

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
    is_admin: bool
    is_approved: bool
    is_locked: bool
    auto_approve: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Items


class ItemCreate(BaseModel):
    name: str
    description: Optional[str] = None
    tag: Optional[str] = None
    locker: Optional[str] = None
    status: Optional[str] = "active"
    manufactured_date: Optional[str] = None
    condition_notes: Optional[str] = None
    borrowed_by_email: Optional[str] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tag: Optional[str] = None
    locker: Optional[str] = None
    available: Optional[bool] = None
    status: Optional[str] = None
    manufactured_date: Optional[str] = None
    condition_notes: Optional[str] = None
    borrowed_by_email: Optional[str] = None


class ItemOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    tag: Optional[str]
    locker: Optional[str]
    available: bool
    status: str
    manufactured_date: Optional[str]
    condition_notes: Optional[str]
    borrowed_by_email: Optional[str]

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
    item_ids: List[int]
    days: int


class LoanOut(BaseModel):
    id: int
    user_id: int
    item_ids: List[int]
    locker_codes: Optional[Dict]
    lockers: Optional[List[str]]
    due_date: Optional[datetime]
    status: str
    created_at: datetime
    returned_at: Optional[datetime]
    photos: List[LoanPhotoOut] = []

    class Config:
        from_attributes = True

# Admin


class StockCheckItem(BaseModel):
    item_id: int
    present: bool
    notes: Optional[str] = None


class StockCheckRequest(BaseModel):
    items: List[StockCheckItem]


class LockerCodeUpdate(BaseModel):
    locker: str
    code: str
