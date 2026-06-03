"""No-mock tests for the onboarding field-encryption primitive (crypto.py).

Env is controlled with ``monkeypatch.setenv``/``delenv`` (env control, NOT
mocking app code) so the real Fernet / MultiFernet path runs end to end. Covers
round-trip, fail-closed-when-unset, key rotation, invalid key, corrupt /
rotated-out token, and the rule that no exception message leaks the plaintext.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from src.onboarding import crypto
from src.onboarding.crypto import ENV_VAR, OnboardingCryptoError


def _key() -> str:
    return Fernet.generate_key().decode("ascii")


def test_roundtrip(monkeypatch):
    monkeypatch.setenv(ENV_VAR, _key())
    ciphertext, key_version = crypto.encrypt_field("hunter2-secret-pw")
    assert isinstance(ciphertext, bytes)
    assert key_version == 1
    # ciphertext must not leak the plaintext
    assert b"hunter2" not in ciphertext
    assert crypto.decrypt_field(ciphertext) == "hunter2-secret-pw"


def test_fail_closed_when_key_unset(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert crypto.is_configured() is False
    with pytest.raises(OnboardingCryptoError):
        crypto.encrypt_field("anything")


def test_empty_key_fails_closed(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "   ")
    assert crypto.is_configured() is False
    with pytest.raises(OnboardingCryptoError):
        crypto.encrypt_field("anything")


def test_rotation_old_ciphertext_still_decrypts(monkeypatch):
    key_a = _key()
    monkeypatch.setenv(ENV_VAR, key_a)
    ciphertext_a, _ = crypto.encrypt_field("rotate-me")

    # Prepend a new PRIMARY key B → "B,A": new writes use B, old tokens still
    # decrypt because A remains in the set.
    key_b = _key()
    monkeypatch.setenv(ENV_VAR, f"{key_b},{key_a}")
    assert crypto.decrypt_field(ciphertext_a) == "rotate-me"
    ciphertext_b, _ = crypto.encrypt_field("new-token")

    # ciphertext_b was written with B (the primary). B alone decrypts it; A
    # alone cannot (proves the primary actually rotated).
    monkeypatch.setenv(ENV_VAR, key_b)
    assert crypto.decrypt_field(ciphertext_b) == "new-token"
    monkeypatch.setenv(ENV_VAR, key_a)
    with pytest.raises(OnboardingCryptoError):
        crypto.decrypt_field(ciphertext_b)


def test_invalid_key_raises(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "not-a-valid-fernet-key")
    with pytest.raises(OnboardingCryptoError):
        crypto.encrypt_field("x")


def test_corrupt_or_rotated_out_token_raises(monkeypatch):
    monkeypatch.setenv(ENV_VAR, _key())
    ciphertext, _ = crypto.encrypt_field("data")

    # Rotate to an entirely fresh key set (the encrypting key is gone).
    monkeypatch.setenv(ENV_VAR, _key())
    with pytest.raises(OnboardingCryptoError):
        crypto.decrypt_field(ciphertext)

    # A non-Fernet token also fails closed (never returns garbage plaintext).
    with pytest.raises(OnboardingCryptoError):
        crypto.decrypt_field(b"garbage-not-a-fernet-token")


def test_exception_never_contains_plaintext(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)
    secret = "TopSecretPassw0rd!"
    with pytest.raises(OnboardingCryptoError) as exc:
        crypto.encrypt_field(secret)
    assert secret not in str(exc.value)


def test_generate_key_is_usable(monkeypatch):
    generated = crypto.generate_key()
    monkeypatch.setenv(ENV_VAR, generated)
    ciphertext, _ = crypto.encrypt_field("ok")
    assert crypto.decrypt_field(ciphertext) == "ok"
