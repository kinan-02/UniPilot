import re
from datetime import datetime, timedelta, timezone

import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from app.config import get_settings

_DURATION_PATTERN = re.compile(r"^(\d+)(ms|s|m|h|d)$")


def parse_expires_in(value: str) -> timedelta:
    match = _DURATION_PATTERN.match(value.strip())
    if not match:
        raise ValueError(f"Unsupported JWT expires format: {value}")

    amount = int(match.group(1))
    unit = match.group(2)

    if unit == "ms":
        return timedelta(milliseconds=amount)
    if unit == "s":
        return timedelta(seconds=amount)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    return timedelta(days=amount)


def create_access_token(*, user_id: str, email: str) -> str:
    settings = get_settings()
    secret = settings.require_jwt_secret()
    expires_delta = parse_expires_in(settings.jwt_expires_in)

    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.now(timezone.utc) + expires_delta,
    }

    return jwt.encode(payload, secret, algorithm="HS256")


def verify_access_token(token: str) -> dict:
    settings = get_settings()
    secret = settings.require_jwt_secret()

    return jwt.decode(
        str(token),
        secret,
        algorithms=["HS256"],
    )
