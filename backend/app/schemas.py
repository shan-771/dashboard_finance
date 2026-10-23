from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator
from uuid import UUID

from app.models import UserRole


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
