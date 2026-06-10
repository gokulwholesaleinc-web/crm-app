"""Field-level encryption for marketing platform OAuth/access tokens at rest.

A dedicated clone of ``onboarding/crypto.py`` keyed by a NEW ``MARKETING_TOKEN_KEY``
env var — NEVER ``SECRET_KEY`` and NEVER ``ONBOARDING_FIELD_KEY`` (blast-radius
isolation, plan cluster D). Fernet / ``MultiFernet`` (AES-128-CBC + HMAC-SHA256);
comma-separated keys enable zero-downtime rotation (first key encrypts, all keys
decrypt). A platform token NEVER reaches the warehouse in plaintext.

If a token is handled while ``MARKETING_TOKEN_KEY`` is unset, encryption raises
loudly (``MarketingCryptoError``) — fail closed, never silently store plaintext.

Self-contained leaf module (stdlib + ``cryptography`` only) so ingestion fetchers
can reuse it without dragging the app graph into their import chain.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

ENV_VAR = "MARKETING_TOKEN_KEY"

# Stored with every ciphertext; ``1`` = the current primary (first) key. A future
# hard re-key bumps this so stale tokens are findable for re-encryption.
PRIMARY_KEY_VERSION = 1


class MarketingCryptoError(RuntimeError):
    """Encryption/decryption misconfiguration or failure (always fail closed)."""


def is_configured() -> bool:
    """True iff ``MARKETING_TOKEN_KEY`` is set (a platform token is storable)."""
    return bool(os.getenv(ENV_VAR, "").strip())


def _multifernet() -> MultiFernet:
    raw = os.getenv(ENV_VAR, "").strip()
    if not raw:
        raise MarketingCryptoError(
            f"{ENV_VAR} is not set; refusing to handle a marketing platform "
            "token (never store/accept plaintext)."
        )
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise MarketingCryptoError(f"{ENV_VAR} is empty after parsing.")
    try:
        return MultiFernet([Fernet(k.encode("ascii")) for k in keys])
    except (ValueError, TypeError) as exc:
        raise MarketingCryptoError(
            f"{ENV_VAR} contains an invalid Fernet key."
        ) from exc


def encrypt_token(plaintext: str) -> tuple[bytes, int]:
    """Encrypt with the primary key. Returns ``(ciphertext, key_version)``."""
    if plaintext is None:
        raise MarketingCryptoError("Cannot encrypt a null platform token.")
    token = _multifernet().encrypt(plaintext.encode("utf-8"))
    return token, PRIMARY_KEY_VERSION


def decrypt_token(ciphertext: bytes) -> str:
    """Decrypt with any configured key. Raises ``MarketingCryptoError`` on failure."""
    try:
        return _multifernet().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        raise MarketingCryptoError(
            "Could not decrypt marketing token (key rotated out or corrupt)."
        ) from exc


def generate_key() -> str:
    """Ops helper: a fresh urlsafe Fernet key to set as ``MARKETING_TOKEN_KEY``."""
    return Fernet.generate_key().decode("ascii")
