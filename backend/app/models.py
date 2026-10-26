from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(StrEnum):
    MANAGER = "manager"
    STAFF = "staff"


class EnquiryStatus(StrEnum):
    NEW = "New"
    ATTENDED = "Attended"
    FOLLOW_UPS = "Follow-ups"
    CLOSED = "Closed"
    OPEN = "Open"
    LOST = "Lost"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('manager', 'staff')", name="ck_users_role"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    sessions: Mapped[list["LoginSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class LoginSession(Base):
    __tablename__ = "login_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_login_sessions_token_hash"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    merged_into_customer_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    enquiries: Mapped[list["Enquiry"]] = relationship(back_populates="customer")
    merged_into: Mapped["Customer | None"] = relationship(remote_side=[id])


class Enquiry(Base):
    __tablename__ = "enquiries"
    __table_args__ = (
        CheckConstraint("status IN ('New', 'Attended', 'Follow-ups', 'Closed', 'Open', 'Lost')", name="ck_enquiries_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    service_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=EnquiryStatus.NEW.value, nullable=False, index=True)
    handled_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    outcome_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="enquiries")
    handled_by: Mapped[User | None] = relationship(foreign_keys=[handled_by_id])
