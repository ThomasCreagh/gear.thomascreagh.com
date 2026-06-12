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

CATEGORIES = [
    "harness",
    "pad",
    "rope",
    "cam",
    "quickdraw",
    "nut",
    "carabiner",
    "helmet",
    "belay_device",
    "sling",
    "rope_protector",
    "misc_trad",
    "misc",
]

CATEGORY_LABELS = {
    "harness": "Harness",
    "pad": "Pad",
    "rope": "Rope",
    "cam": "Cam",
    "quickdraw": "Quickdraw",
    "nut": "Nut",
    "carabiner": "Carabiner",
    "helmet": "Helmet",
    "belay_device": "Belay Device",
    "sling": "Sling",
    "rope_protector": "Rope Protector",
    "misc_trad": "Misc Trad",
    "misc": "Misc",
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
    lockers: List[str]   # which lockers they need, e.g. ["top", "bottom", "pad"]
    days: int


class LoanVerifyRequest(BaseModel):
    verification_code: str


class LoanVerifyResponse(BaseModel):
    locker_codes: Dict[str, str]   # {"top": "1234", "bottom": "5678", ...}
    due_date: datetime


class LoanUpdate(BaseModel):
    item_ids: Optional[List[int]] = None
    due_date: Optional[datetime] = None


class LoanOut(BaseModel):
    id: int
    user_id: int
    item_ids: List[int]
    locker_codes: Optional[Dict]
    lockers: Optional[List[str]]
    locker_verified: bool = False
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


class VerificationCodeUpdate(BaseModel):
    code: str
