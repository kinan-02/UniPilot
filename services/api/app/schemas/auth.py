import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.security.password import BCRYPT_MAX_PASSWORD_BYTES, password_utf8_byte_length

PASSWORD_MIN_LENGTH = 8

_UPPERCASE_PATTERN = re.compile(r"[A-Z]")
_LOWERCASE_PATTERN = re.compile(r"[a-z]")
_NUMBER_PATTERN = re.compile(r"[0-9]")
_SPECIAL_PATTERN = re.compile(r"[^A-Za-z0-9]")


def normalize_email_value(value: str) -> str:
    return str(value).strip().lower()


def validate_password_strength(password: str) -> str:
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError("Password must be at least 8 characters long")
    if password_utf8_byte_length(password) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError("Password must be at most 72 bytes long")
    if not _UPPERCASE_PATTERN.search(password):
        raise ValueError("Password must include at least one uppercase letter")
    if not _LOWERCASE_PATTERN.search(password):
        raise ValueError("Password must include at least one lowercase letter")
    if not _NUMBER_PATTERN.search(password):
        raise ValueError("Password must include at least one number")
    if not _SPECIAL_PATTERN.search(password):
        raise ValueError("Password must include at least one special character")
    return password


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=254)
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return normalize_email_value(value)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_password_strength(value)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return normalize_email_value(value)
