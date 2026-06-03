from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

LOCKER_CHOICES = ["upper", "lower", "outdoor", "pad"]


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)
    is_approved = Column(Boolean, default=False)
    is_locked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    loans = relationship("Loan", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")


class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String)
    tag = Column(Integer)                          # physical tag number
    # upper | lower | outdoor | pad
    locker = Column(String)
    available = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    item_ids = Column(JSON, nullable=False)
    locker_code = Column(String)
    locker = Column(String)                        # which locker to use
    due_date = Column(DateTime)
    returned = Column(Boolean, default=False)
    borrow_photo = Column(String)
    return_photo = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    returned_at = Column(DateTime)

    user = relationship("User", back_populates="loans")


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
    # which locker this code is for
    locker = Column(String, nullable=False)
    code = Column(String, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow)
    updated_by = Column(Integer, ForeignKey("users.id"))
