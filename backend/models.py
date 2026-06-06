from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

LOCKERS = ["outdoor", "top", "bottom", "pad"]
LOCKER_LABELS = {
    "outdoor": "Outdoor Locker",
    "top": "Top Locker",
    "bottom": "Bottom Locker",
    "pad": "Pad Stash",
}

ITEM_STATUSES = ["active", "retired", "missing"]


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)
    is_approved = Column(Boolean, default=False)
    is_locked = Column(Boolean, default=False)
    auto_approve = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    loans = relationship("Loan", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    # item type: harness, cam, etc.
    name = Column(String, nullable=False)
    # model/spec: "BD C4 size 1 red"
    description = Column(String)
    # tag number as string e.g. "001"
    tag = Column(String)
    # outdoor | top | bottom | pad
    locker = Column(String)
    available = Column(Boolean, default=True)       # False when on loan
    # active | retired | missing
    status = Column(String, default="active")
    # free text: "2021", "2010 or earlier"
    manufactured_date = Column(String)
    # from stock check: "good", "janky wire"
    condition_notes = Column(String)
    # email if currently on loan outside system
    borrowed_by_email = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow)


class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    item_ids = Column(JSON, nullable=False)
    locker_codes = Column(JSON)   # {"outdoor": "1234", "top": "5678"}
    lockers = Column(JSON)        # ["outdoor", "top"]
    due_date = Column(DateTime)
    # pending | active | returned | denied
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    returned_at = Column(DateTime)

    user = relationship("User", back_populates="loans")
    photos = relationship(
        "LoanPhoto", back_populates="loan", cascade="all, delete")


class LoanPhoto(Base):
    __tablename__ = "loan_photos"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False)
    locker = Column(String, nullable=False)
    photo_type = Column(String, nullable=False)   # borrow | return
    file_path = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    loan = relationship("Loan", back_populates="photos")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String, nullable=False)
    details = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="audit_logs")


class LockerCode(Base):
    __tablename__ = "locker_codes"

    id = Column(Integer, primary_key=True, index=True)
    locker = Column(String, nullable=False)
    code = Column(String, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"))
