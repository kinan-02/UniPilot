import bcrypt

from app.config import get_settings

BCRYPT_MAX_PASSWORD_BYTES = 72


def password_utf8_byte_length(password: str) -> int:
    return len(str(password).encode("utf-8"))


def resolve_salt_rounds() -> int:
    return get_settings().resolved_bcrypt_salt_rounds()


def hash_password(plain_text_password: str) -> str:
    password_bytes = str(plain_text_password).encode("utf-8")
    if len(password_bytes) > BCRYPT_MAX_PASSWORD_BYTES:
        raise ValueError("Password must be at most 72 bytes long")

    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=resolve_salt_rounds()))
    return hashed.decode("utf-8")


def verify_password(plain_text_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        str(plain_text_password).encode("utf-8"),
        str(hashed_password).encode("utf-8"),
    )


def is_password_within_bcrypt_limit(password: str) -> bool:
    return password_utf8_byte_length(password) <= BCRYPT_MAX_PASSWORD_BYTES
