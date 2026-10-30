from datetime import datetime, timezone
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(StrEnum):
    MANAGER = "manager"
    STAFF = "staff"


class EnquiryStatus(StrEnum):
    NEW = "New"
    ASSIGNED = "Assigned"
    ATTENDED = "Attended"
    FOLLOW_UPS = "Follow-ups"
    CLOSED = "Closed"
    OPEN = "Open"
    LOST = "Lost"


class ChangeRequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STALE = "stale"
    COMPLETED = "completed"


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
    claim_attempt_window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
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
        CheckConstraint("status IN ('New', 'Assigned', 'Attended', 'Follow-ups', 'Closed', 'Open', 'Lost')", name="ck_enquiries_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    customer_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id", ondelete="RESTRICT"), nullable=False, index=True)
    service_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=EnquiryStatus.NEW.value, nullable=False, index=True)
    handled_by_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    do_not_contact: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    customer: Mapped[Customer] = relationship(back_populates="enquiries")
    handled_by: Mapped[User | None] = relationship(foreign_keys=[handled_by_id])
    follow_ups: Mapped[list["FollowUp"]] = relationship(back_populates="enquiry", order_by="FollowUp.completed_at")


class FollowUp(Base):
    __tablename__ = "follow_ups"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    enquiry_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    enquiry: Mapped[Enquiry] = relationship(back_populates="follow_ups")
    created_by: Mapped[User | None] = relationship()


class EnquiryChangeRequest(Base):
    __tablename__ = "enquiry_change_requests"
    __table_args__ = (
        CheckConstraint("request_type IN ('edit', 'delete')", name="ck_change_requests_type"),
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'stale', 'completed')", name="ck_change_requests_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    enquiry_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="RESTRICT"), nullable=False, index=True)
    request_type: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(12), default=ChangeRequestStatus.PENDING.value, nullable=False, index=True)
    proposed_changes: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    original_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    base_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    enquiry: Mapped[Enquiry] = relationship()
    submitted_by: Mapped[User | None] = relationship(foreign_keys=[submitted_by_user_id])
    decided_by: Mapped[User | None] = relationship(foreign_keys=[decided_by_user_id])
    confirmed_by: Mapped[User | None] = relationship(foreign_keys=[confirmed_by_user_id])

    @property
    def submitted_by_name(self) -> str | None:
        return self.submitted_by.display_name if self.submitted_by else None

    @property
    def decided_by_name(self) -> str | None:
        return self.decided_by.display_name if self.decided_by else None

    @property
    def confirmed_by_name(self) -> str | None:
        return self.confirmed_by.display_name if self.confirmed_by else None


class EnquiryAuditEvent(Base):
    __tablename__ = "enquiry_audit_events"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    enquiry_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="RESTRICT"), nullable=False, index=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    before_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    after_values: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    actor: Mapped[User | None] = relationship()


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint(
            "notification_type IN ('new_enquiry', 'deletion_request', 'deletion_decision')",
            name="ck_notifications_type",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notification_type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    enquiry_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("enquiries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship()
