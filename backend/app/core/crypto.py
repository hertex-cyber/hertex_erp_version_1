"""Symmetric encryption for settings secrets (module 15A, M5).

AES-256-GCM with a per-value random nonce and a key version, so a key can be
rotated without re-reading every ciphertext on the request path:

* ``encrypt(plaintext) -> (ciphertext, nonce, key_version)``
* ``decrypt(ciphertext, nonce, key_version)`` — raises ``SecretDecryptionError``
  when the key version is unknown or the authentication tag fails.

The key never leaves ``app.core.config``; the only thing persisted is ciphertext.
"""

from __future__ import annotations

import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

NONCE_BYTES = 12


class SecretDecryptionError(Exception):
    """Raised when a secret cannot be decrypted with the configured key."""


def _aesgcm(key_version: int) -> AESGCM:
    key = settings.encryption_keys().get(key_version)
    if key is None:
        raise SecretDecryptionError(
            f"No key material for settings encryption key version {key_version}"
        )
    return AESGCM(key)


def encrypt(plaintext: str, *, key_version: int | None = None) -> tuple[bytes, bytes, int]:
    version = settings.SETTINGS_ENCRYPTION_KEY_VERSION if key_version is None else key_version
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = _aesgcm(version).encrypt(nonce, plaintext.encode("utf-8"), None)
    return ciphertext, nonce, version


def decrypt(ciphertext: bytes, nonce: bytes, key_version: int) -> str:
    try:
        plaintext = _aesgcm(key_version).decrypt(nonce, ciphertext, None)
    except SecretDecryptionError:
        raise
    except (InvalidTag, ValueError) as exc:
        raise SecretDecryptionError("Secret authentication failed") from exc
    return plaintext.decode("utf-8")


def rewrap(
    ciphertext: bytes,
    nonce: bytes,
    from_version: int,
    to_version: int | None = None,
) -> tuple[bytes, bytes, int]:
    plaintext = decrypt(ciphertext, nonce, from_version)
    target = settings.SETTINGS_ENCRYPTION_KEY_VERSION if to_version is None else to_version
    return encrypt(plaintext, key_version=target)


def mask(value: str) -> str:
    """Mask a secret for API responses: ``sk_live_ab12cd34`` -> ``sk_••••cd34``."""
    if not value:
        return ""
    if len(value) <= 4:
        return "••••"
    prefix = value[:3] if len(value) > 12 else ""
    return f"{prefix}••••{value[-4:]}"
