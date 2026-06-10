"""Field-level encryption for the Meta integration's stored OAuth tokens (C4).

A dedicated clone of ``onboarding/crypto.py`` / ``marketing/crypto.py`` keyed by a
NEW ``META_TOKEN_KEY`` env var — NEVER ``SECRET_KEY``, ``ONBOARDING_FIELD_KEY`` or
``MARKETING_TOKEN_KEY`` (blast-radius isolation). Fernet / ``MultiFernet``
(AES-128-CBC + HMAC-SHA256); comma-separated keys enable zero-downtime rotation
(first key encrypts, all keys decrypt).

This backs the C4 retrofit of the ``meta_credentials.access_token`` column, which
is stored in PLAINTEXT today. Encryption is fail-closed: handling a token while
``META_TOKEN_KEY`` is unset raises (``MetaCryptoError``) rather than silently
storing plaintext. During the multi-deploy rollout the service keeps writing the
legacy plaintext column too (write-both) and only requires this key once
``META_TOKEN_ENCRYPTION_STRICT`` is on; see ``meta/service.py``.

Self-contained leaf module (stdlib + ``cryptography`` only).
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

ENV_VAR = "META_TOKEN_KEY"

# Stored with every ciphertext; ``1`` = the current primary (first) key.
PRIMARY_KEY_VERSION = 1


class MetaCryptoError(RuntimeError):
    """Encryption/decryption misconfiguration or failure (always fail closed)."""


def is_configured() -> bool:
    """True iff ``META_TOKEN_KEY`` is set (a Meta token is encryptable)."""
    return bool(os.getenv(ENV_VAR, "").strip())


def _multifernet() -> MultiFernet:
    raw = os.getenv(ENV_VAR, "").strip()
    if not raw:
        raise MetaCryptoError(
            f"{ENV_VAR} is not set; refusing to handle a Meta token "
            "(never store/accept plaintext)."
        )
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise MetaCryptoError(f"{ENV_VAR} is empty after parsing.")
    try:
        return MultiFernet([Fernet(k.encode("ascii")) for k in keys])
    except (ValueError, TypeError) as exc:
        raise MetaCryptoError(f"{ENV_VAR} contains an invalid Fernet key.") from exc


def encrypt_token(plaintext: str) -> tuple[bytes, int]:
    """Encrypt with the primary key. Returns ``(ciphertext, key_version)``."""
    if plaintext is None:
        raise MetaCryptoError("Cannot encrypt a null Meta token.")
    token = _multifernet().encrypt(plaintext.encode("utf-8"))
    return token, PRIMARY_KEY_VERSION


def decrypt_token(ciphertext: bytes) -> str:
    """Decrypt with any configured key. Raises ``MetaCryptoError`` on failure."""
    try:
        return _multifernet().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        raise MetaCryptoError(
            "Could not decrypt Meta token (key rotated out or corrupt)."
        ) from exc


def generate_key() -> str:
    """Ops helper: a fresh urlsafe Fernet key to set as ``META_TOKEN_KEY``."""
    return Fernet.generate_key().decode("ascii")
