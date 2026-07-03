"""Fernet encryption for OAuth tokens at rest."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class TokenCryptoError(Exception):
    pass


def derive_fernet_key(raw_key: bytes) -> bytes:
    digest = hashlib.sha256(raw_key).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(plaintext: str, *, raw_key: bytes) -> str:
    fernet = Fernet(derive_fernet_key(raw_key))
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(ciphertext: str, *, raw_key: bytes) -> str:
    fernet = Fernet(derive_fernet_key(raw_key))
    try:
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise TokenCryptoError("Token decryption failed") from exc
