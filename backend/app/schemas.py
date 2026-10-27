from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator, model_validator
from uuid import UUID

from app.models import EnquiryStatus, UserRole


class LoginRequest(BaseModel):
    user_id: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    password: SecretStr

    @field_validator("user_id")
    @classmethod
    def normalize_user_id(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("password")
    @classmethod
    def limit_login_password_size(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) > 128:
            raise ValueError("Password must contain at most 128 characters")
        return value


class CreateStaffRequest(BaseModel):
    user_id: str = Field(min_length=3, max_length=50, pattern=r"^[A-Za-z0-9._-]+$")
    email: EmailStr
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    password: SecretStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: EmailStr) -> str:
        return str(value).strip().lower()

    @field_validator("user_id")
    @classmethod
    def normalize_user_id(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("display_name")
    @classmethod
    def trim_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if len(normalized) < 2:
            raise ValueError("Display name must contain at least 2 characters")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: SecretStr) -> SecretStr:
        password = value.get_secret_value()
        if len(password) < 12:
            raise ValueError("Password must contain at least 12 characters")
        if len(password) > 128:
            raise ValueError("Password must contain at most 128 characters")
        return value


class StaffStatusUpdate(BaseModel):
    is_active: bool


class UserResponse(BaseModel):
    id: UUID
    user_id: str
    email: EmailStr
    display_name: str
    role: UserRole
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class AuthResponse(BaseModel):
    user: UserResponse
    csrf_token: str


class CustomerInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=3, max_length=40)
    email: EmailStr | None = None

    @field_validator("name", "phone")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise ValueError("This field must contain at least 2 characters")
        return value

    @field_validator("email")
    @classmethod
    def normalize_optional_email(cls, value: EmailStr | None) -> str | None:
        return str(value).strip().lower() if value is not None else None


class CreateEnquiryRequest(BaseModel):
    customer_id: UUID | None = None
    customer: CustomerInput | None = None
    service_type: str = Field(min_length=2, max_length=80)
    source: str = Field(min_length=2, max_length=40)

    @field_validator("service_type", "source")
    @classmethod
    def trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value

    @model_validator(mode="after")
    def require_customer(self):
        if (self.customer_id is None) == (self.customer is None):
            raise ValueError("Provide either customer_id or customer details")
        return self


class CreatePublicEnquiryRequest(BaseModel):
    customer: CustomerInput
    service_type: str = Field(min_length=2, max_length=80)

    @field_validator("service_type")
    @classmethod
    def trim_service_type(cls, value: str) -> str:
        return value.strip()


class MergeCustomerRequest(BaseModel):
    source_customer_id: UUID


class PublicEnquiryAccepted(BaseModel):
    accepted: bool = True


class UpdateEnquiryStatusRequest(BaseModel):
    status: EnquiryStatus
    outcome_reason: str | None = Field(default=None, max_length=2000)
    do_not_contact: bool = False

    @field_validator("outcome_reason")
    @classmethod
    def trim_outcome_reason(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class UpdateEnquiryHandlerRequest(BaseModel):
    handled_by_id: UUID | None


class ScheduleFollowUpRequest(BaseModel):
    next_follow_up_at: datetime | None

    @field_validator("next_follow_up_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Follow-up date and time must include a timezone")
        return value.astimezone(timezone.utc) if value is not None else None


class CompleteFollowUpRequest(BaseModel):
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("completed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Completed date and time must include a timezone")
        return value.astimezone(timezone.utc)


class CustomerResponse(BaseModel):
    id: UUID
    name: str
    phone: str
    email: EmailStr | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EnquiryResponse(BaseModel):
    id: UUID
    customer: CustomerResponse
    service_type: str
    source: str
    status: EnquiryStatus
    handled_by_id: UUID | None
    handled_by_name: str | None
    outcome_reason: str | None
    do_not_contact: bool
    next_follow_up_at: datetime | None
    completed_follow_up_count: int
    created_at: datetime
    updated_at: datetime


class FollowUpResponse(BaseModel):
    id: UUID
    enquiry_id: UUID
    completed_at: datetime
    created_by_user_id: UUID | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("completed_at", "created_at", mode="before")
    @classmethod
    def ensure_utc_response_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class FollowUpPage(BaseModel):
    bucket: str
    items: list[EnquiryResponse]
    total: int
    limit: int
    offset: int


class FollowUpHistoryPage(BaseModel):
    items: list[FollowUpResponse]
    total: int
    limit: int
    offset: int


class EnquiryPage(BaseModel):
    items: list[EnquiryResponse]
    total: int
    limit: int
    offset: int
