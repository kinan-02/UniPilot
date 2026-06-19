import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest


def test_register_request_accepts_valid_payload():
    payload = RegisterRequest(
        email="student@example.com",
        password="StrongPass123!",
    )

    assert payload.email == "student@example.com"
    assert payload.password == "StrongPass123!"


def test_register_request_rejects_weak_password():
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="student@example.com",
            password="123",
        )


def test_register_request_rejects_passwords_longer_than_bcrypt_safe_length():
    with pytest.raises(ValidationError):
        RegisterRequest(
            email="student@example.com",
            password=f"{'A' * 71}1!",
        )


def test_login_request_rejects_invalid_email_format():
    with pytest.raises(ValidationError):
        LoginRequest(
            email="not-an-email",
            password="StrongPass123!",
        )


def test_register_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        RegisterRequest.model_validate(
            {
                "email": "student@example.com",
                "password": "StrongPass123!",
                "role": "admin",
            }
        )


def test_register_request_normalizes_email_to_lowercase():
    payload = RegisterRequest(
        email="Student@Example.com",
        password="StrongPass123!",
    )

    assert payload.email == "student@example.com"
