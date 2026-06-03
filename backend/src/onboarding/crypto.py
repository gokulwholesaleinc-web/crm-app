"""Field-level encryption for sensitive onboarding answers (P0-7; F4 passwords).

Fernet / ``MultiFernet`` (AES-128-CBC + HMAC-SHA256) keyed by a NEW
``ONBOARDING_FIELD_KEY`` env var — NEVER ``SECRET_KEY``. Comma-separated keys
enable rotation: the FIRST key encrypts; ALL keys can decrypt (``MultiFernet``
tries each), so a new key is prepended and old ciphertexts still decrypt.

A sensitive field's plaintext NEVER enters ``field_values`` JSONB nor any
generated PDF — only the ciphertext (in ``onboarding_secret_values``) does. If a
sensitive field is submitted while ``ONBOARDING_FIELD_KEY`` is unset, encryption
raises loudly (``OnboardingCryptoError``) — fail closed, never silently store or
accept plaintext.

Self-contained leaf module: imports only stdlib + ``cryptography`` so the kind
handlers can reuse it without dragging the app graph into their import chain.
"""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

ENV_VAR = "ONBOARDING_FIELD_KEY"

# Stored with every ciphertext; ``1`` = the current primary (first) key. A
# future hard re-key bumps this so stale tokens are findable.
PRIMARY_KEY_VERSION = 1


class OnboardingCryptoError(RuntimeError):
    """Encryption/decryption misconfiguration or failure (always fail closed)."""


def is_configured() -> bool:
    """True iff ``ONBOARDING_FIELD_KEY`` is set (a sensitive field is usable)."""
    return bool(os.getenv(ENV_VAR, "").strip())


def _multifernet() -> MultiFernet:
    raw = os.getenv(ENV_VAR, "").strip()
    if not raw:
        raise OnboardingCryptoError(
            f"{ENV_VAR} is not set; refusing to handle a sensitive onboarding "
            "field (never store/accept plaintext)."
        )
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise OnboardingCryptoError(f"{ENV_VAR} is empty after parsing.")
    try:
        return MultiFernet([Fernet(k.encode("ascii")) for k in keys])
    except (ValueError, TypeError) as exc:
        raise OnboardingCryptoError(
            f"{ENV_VAR} contains an invalid Fernet key."
        ) from exc


def encrypt_field(plaintext: str) -> tuple[bytes, int]:
    """Encrypt with the primary key. Returns ``(ciphertext, key_version)``."""
    if plaintext is None:
        raise OnboardingCryptoError("Cannot encrypt a null sensitive value.")
    token = _multifernet().encrypt(plaintext.encode("utf-8"))
    return token, PRIMARY_KEY_VERSION


def decrypt_field(ciphertext: bytes) -> str:
    """Decrypt with any configured key. Raises ``OnboardingCryptoError`` on failure."""
    try:
        return _multifernet().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        raise OnboardingCryptoError(
            "Could not decrypt onboarding secret (key rotated out or corrupt)."
        ) from exc


def generate_key() -> str:
    """Ops helper: a fresh urlsafe Fernet key to set as ``ONBOARDING_FIELD_KEY``."""
    return Fernet.generate_key().decode("ascii")
