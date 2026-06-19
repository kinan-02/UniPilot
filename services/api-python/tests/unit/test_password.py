from app.security.password import hash_password, verify_password


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
