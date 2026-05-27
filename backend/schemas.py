from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


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
    created_at: datetime

    class Config:
        from_attributes = True


# Items
class ItemCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    available: Optional[bool] = None


class ItemOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    available: bool

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
    locker_code: Optional[str]
    due_date: Optional[datetime]
    returned: bool
    created_at: datetime
    returned_at: Optional[datetime]

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
    code: str
