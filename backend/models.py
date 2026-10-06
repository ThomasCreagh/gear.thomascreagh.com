from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base
from constants import CATEGORIES, CATEGORY_LABELS, ITEM_STATUSES, LOCKERS, LOCKER_LABELS


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    name = Column(String)
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
    # Admin-uploaded reference photo, shown on the gear browser.
    image_path = Column(String)
    # tag number as string e.g. "001"
    tag = Column(String)
    # outdoor | top | bottom | pad
    locker = Column(String)
    # category: harness | cam | rope | etc.
    category = Column(String)
    available = Column(Boolean, default=True)       # False when on loan
    # active | retired | missing
    status = Column(String, default="active")
    # free text: "2021", "2010 or earlier"
    manufactured_date = Column(String)
    # free-text condition notes: "good", "janky wire"
    condition_notes = Column(String)
    # email if currently on loan outside system
    borrowed_by_email = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow,
                        onupdate=datetime.utcnow)


class GearGroup(Base):
    """A named set of individually tagged items, e.g. a trad rack."""
    __tablename__ = "gear_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, unique=True)
    # Admin-uploaded reference photo, shown alongside the group in the catalogue.
    image_path = Column(String)
    item_ids = Column(JSON, nullable=False, default=list)
    group_ids = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)


class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    item_ids = Column(JSON, nullable=False, default=list)  # filled after locker opened
    lockers = Column(JSON)             # ["outdoor", "top"] — chosen at loan creation
    locker_codes = Column(JSON)        # Locker combinations snapshot for this loan
    door_code = Column(String)         # Trinity Wall door code issued with every loan
    due_date = Column(DateTime)
    # For outdoor loans this may be a future booking date; T-wall loans start now.
    start_date = Column(DateTime)
    # pending_review | active | returned | denied
    status = Column(String, default="active")
    # standard | twall
    loan_type = Column(String, default="standard")
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
    """Current/history of physical locker combinations for admin reference."""
    __tablename__ = "locker_codes"

    id = Column(Integer, primary_key=True, index=True)
    locker = Column(String, nullable=False)
    code = Column(String, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"))
