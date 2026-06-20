import pytest

from app.security.password import (
    BCRYPT_MAX_PASSWORD_BYTES,
    hash_password,
    is_password_within_bcrypt_limit,
    password_utf8_byte_length,
    verify_password,
)


def test_hash_password_returns_bcrypt_hash_and_not_plain_text():
    plain_text_password = "StrongPass123!"
    hashed_password = hash_password(plain_text_password)

    assert hashed_password != plain_text_password
    assert hashed_password.startswith("$2")


def test_verify_password_returns_true_for_matching_password():
    plain_text_password = "StrongPass123!"
    hashed_password = hash_password(plain_text_password)

    assert verify_password(plain_text_password, hashed_password) is True


def test_verify_password_returns_false_for_non_matching_password():
    plain_text_password = "StrongPass123!"
    hashed_password = hash_password(plain_text_password)

    assert verify_password("WrongPassword1!", hashed_password) is False


def test_password_utf8_byte_length_counts_multibyte_characters():
    password = "Aa1!" + ("é" * 35)
    assert len(password) < 72
    assert password_utf8_byte_length(password) == 74


def test_is_password_within_bcrypt_limit_uses_utf8_bytes():
    within_limit = "A" * BCRYPT_MAX_PASSWORD_BYTES
    over_limit = "A" * (BCRYPT_MAX_PASSWORD_BYTES - 3) + "éé"

    assert is_password_within_bcrypt_limit(within_limit) is True
    assert is_password_within_bcrypt_limit(over_limit) is False


def test_hash_password_rejects_passwords_exceeding_bcrypt_byte_limit():
    password = "Aa1!" + ("é" * 35)

    with pytest.raises(ValueError, match="72 bytes"):
        hash_password(password)
