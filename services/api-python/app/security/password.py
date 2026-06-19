import bcrypt

from app.config import get_settings

BCRYPT_MAX_PASSWORD_BYTES = 72


def resolve_salt_rounds() -> int:
    return get_settings().resolved_bcrypt_salt_rounds()


def hash_password(plain_text_password: str) -> str:
    password_bytes = str(plain_text_password).encode("utf-8")
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt(rounds=resolve_salt_rounds()))
    return hashed.decode("utf-8")


def verify_password(plain_text_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        str(plain_text_password).encode("utf-8"),
        str(hashed_password).encode("utf-8"),
    )


def is_password_within_bcrypt_limit(password: str) -> bool:
    return len(password.encode("utf-8")) <= BCRYPT_MAX_PASSWORD_BYTES
