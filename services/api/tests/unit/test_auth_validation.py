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


def test_register_request_rejects_passwords_exceeding_bcrypt_byte_limit():
    password = "Aa1!" + ("é" * 35)
    assert len(password) < 72
    assert len(password.encode("utf-8")) > 72

    with pytest.raises(ValidationError):
        RegisterRequest(
            email="student@example.com",
            password=password,
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


def test_register_request_rejects_password_without_uppercase():
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(
            email="student@example.com",
            password="alllowercase1!",
        )
    assert "uppercase" in str(exc_info.value).lower()


def test_register_request_rejects_password_without_lowercase():
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(
            email="student@example.com",
            password="ALLUPPERCASE1!",
        )
    assert "lowercase" in str(exc_info.value).lower()


def test_register_request_rejects_password_without_number():
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(
            email="student@example.com",
            password="NoNumberHere!",
        )
    assert "number" in str(exc_info.value).lower()


def test_register_request_rejects_password_without_special_character():
    with pytest.raises(ValidationError) as exc_info:
        RegisterRequest(
            email="student@example.com",
            password="NoSpecial123",
        )
    assert "special" in str(exc_info.value).lower()


def test_login_request_accepts_any_non_empty_password():
    payload = LoginRequest(
        email="student@example.com",
        password="w",
    )
    assert payload.password == "w"


def test_login_request_normalizes_email_to_lowercase():
    payload = LoginRequest(
        email="Student@Example.COM",
        password="AnyPass1!",
    )
    assert payload.email == "student@example.com"


def test_login_request_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        LoginRequest.model_validate(
            {
                "email": "student@example.com",
                "password": "AnyPass1!",
                "role": "admin",
            }
        )
