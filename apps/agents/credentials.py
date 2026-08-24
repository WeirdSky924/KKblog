from __future__ import annotations

import base64
import hashlib

from django.conf import settings

MAX_API_KEY_LENGTH = 8_192


class AgentCredentialError(ValueError):
    """Raised when an encrypted provider credential cannot be used."""


def _fernet() -> object:
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise AgentCredentialError("agents.credential_unavailable.v1") from None
    secret_key = getattr(settings, "SECRET_KEY", "")
    if not isinstance(secret_key, str) or len(secret_key) < 32:
        raise AgentCredentialError("agents.credential_unavailable.v1")
    derived = hashlib.sha256(secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def validate_api_key(value: object) -> str:
    if not isinstance(value, str):
        raise AgentCredentialError("agents.api_key_invalid.v1")
    normalized = value.strip()
    if not 1 <= len(normalized) <= MAX_API_KEY_LENGTH or any(
        ord(character) < 33 or ord(character) > 126 for character in normalized
    ):
        raise AgentCredentialError("agents.api_key_invalid.v1")
    return normalized


def encrypt_api_key(value: object) -> str:
    normalized = validate_api_key(value)
    try:
        return _fernet().encrypt(normalized.encode("utf-8")).decode("ascii")
    except AgentCredentialError:
        raise
    except Exception:
        raise AgentCredentialError("agents.credential_unavailable.v1") from None


def decrypt_api_key(ciphertext: object) -> str:
    if not isinstance(ciphertext, str) or not ciphertext:
        raise AgentCredentialError("agents.credential_unavailable.v1")
    try:
        plaintext = (
            _fernet().decrypt(ciphertext.encode("ascii"), ttl=None).decode("utf-8")
        )
    except (UnicodeError, ValueError, AgentCredentialError):
        raise AgentCredentialError("agents.credential_unavailable.v1") from None
    except Exception:
        raise AgentCredentialError("agents.credential_unavailable.v1") from None
    return validate_api_key(plaintext)


__all__ = [
    "AgentCredentialError",
    "MAX_API_KEY_LENGTH",
    "decrypt_api_key",
    "encrypt_api_key",
    "validate_api_key",
]
