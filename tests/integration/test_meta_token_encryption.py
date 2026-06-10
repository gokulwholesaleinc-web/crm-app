"""Meta token encryption retrofit (C4) — crypto + write-both/read-fallback/strict.

The Meta integration stored OAuth tokens in PLAINTEXT; these pin the multi-deploy
retrofit: a fail-closed Fernet round-trip, write-both during the expand phase, the
read-new-fallback-old helper, strict-phase behavior (ciphertext-only, no plaintext),
and the resumable backfill. Runs on the in-memory SQLite harness (LargeBinary works
there); no network — exchange_code's httpx OAuth exchange is out of scope, the
retrofit logic under test is the token storage/read helpers.
"""

from __future__ import annotations

import pytest

# A real, importable scripts module (backend/ is on sys.path via tests/conftest).
from scripts.backfill_meta_token_encryption import backfill_meta_tokens
from src.config import settings
from src.meta import crypto
from src.meta.models import MetaCredential
from src.meta.service import MetaService


@pytest.fixture
def meta_key(monkeypatch):
    """Configure a fresh META_TOKEN_KEY for the test."""
    monkeypatch.setenv(crypto.ENV_VAR, crypto.generate_key())


class TestMetaCrypto:
    def test_round_trip(self, meta_key):
        ct, version = crypto.encrypt_token("EAAB-secret-token")
        assert version == crypto.PRIMARY_KEY_VERSION
        assert isinstance(ct, bytes) and ct != b"EAAB-secret-token"
        assert crypto.decrypt_token(ct) == "EAAB-secret-token"

    def test_fail_closed_when_key_unset(self, monkeypatch):
        monkeypatch.delenv(crypto.ENV_VAR, raising=False)
        assert crypto.is_configured() is False
        with pytest.raises(crypto.MetaCryptoError):
            crypto.encrypt_token("x")

    def test_uses_its_own_key_not_marketing(self, monkeypatch):
        # blast-radius isolation: MARKETING_TOKEN_KEY must NOT satisfy meta crypto.
        monkeypatch.delenv(crypto.ENV_VAR, raising=False)
        monkeypatch.setenv("MARKETING_TOKEN_KEY", crypto.generate_key())
        assert crypto.is_configured() is False


class TestStoreAccessToken:
    def test_write_both_in_expand_phase(self, meta_key, monkeypatch):
        monkeypatch.setattr(settings, "META_TOKEN_ENCRYPTION_STRICT", False)
        cred = MetaCredential(user_id=1)
        MetaService._store_access_token(cred, "tok-123")
        # both columns written; ciphertext decrypts back to the token
        assert cred.access_token == "tok-123"
        assert cred.access_token_ciphertext is not None
        assert crypto.decrypt_token(cred.access_token_ciphertext) == "tok-123"
        assert cred.token_key_version == crypto.PRIMARY_KEY_VERSION

    def test_expand_without_key_writes_plaintext_only(self, monkeypatch):
        monkeypatch.delenv(crypto.ENV_VAR, raising=False)
        monkeypatch.setattr(settings, "META_TOKEN_ENCRYPTION_STRICT", False)
        cred = MetaCredential(user_id=1)
        MetaService._store_access_token(cred, "tok-123")
        # graceful: deploy before the key is set doesn't break the OAuth callback
        assert cred.access_token == "tok-123"
        assert cred.access_token_ciphertext is None

    def test_strict_phase_ciphertext_only(self, meta_key, monkeypatch):
        monkeypatch.setattr(settings, "META_TOKEN_ENCRYPTION_STRICT", True)
        cred = MetaCredential(user_id=1)
        MetaService._store_access_token(cred, "tok-123")
        assert cred.access_token is None  # plaintext no longer written
        assert crypto.decrypt_token(cred.access_token_ciphertext) == "tok-123"

    def test_strict_without_key_fails_closed(self, monkeypatch):
        monkeypatch.delenv(crypto.ENV_VAR, raising=False)
        monkeypatch.setattr(settings, "META_TOKEN_ENCRYPTION_STRICT", True)
        with pytest.raises(crypto.MetaCryptoError):
            MetaService._store_access_token(MetaCredential(user_id=1), "tok-123")

    def test_expand_without_key_clears_stale_ciphertext(self, monkeypatch):
        # C4-1: a reconnect while the key is unset must clear a prior ciphertext, else
        # _effective_token would prefer the STALE ciphertext and return the old token.
        monkeypatch.setenv(crypto.ENV_VAR, crypto.generate_key())
        old_ct, _ = crypto.encrypt_token("OLD")
        monkeypatch.delenv(crypto.ENV_VAR, raising=False)  # key now unset
        monkeypatch.setattr(settings, "META_TOKEN_ENCRYPTION_STRICT", False)
        cred = MetaCredential(user_id=1, access_token="OLD", access_token_ciphertext=old_ct, token_key_version=1)
        MetaService._store_access_token(cred, "NEW")
        assert cred.access_token == "NEW"
        assert cred.access_token_ciphertext is None and cred.token_key_version is None
        assert MetaService._effective_token(cred) == "NEW"  # not the stale "OLD"


class TestEffectiveToken:
    def test_prefers_ciphertext(self, meta_key, monkeypatch):
        monkeypatch.setattr(settings, "META_TOKEN_ENCRYPTION_STRICT", False)
        ct, _ = crypto.encrypt_token("cipher-tok")
        cred = MetaCredential(user_id=1, access_token="stale-plain", access_token_ciphertext=ct)
        assert MetaService._effective_token(cred) == "cipher-tok"

    def test_plaintext_fallback_in_expand_phase(self, monkeypatch):
        monkeypatch.setattr(settings, "META_TOKEN_ENCRYPTION_STRICT", False)
        cred = MetaCredential(user_id=1, access_token="plain-tok", access_token_ciphertext=None)
        assert MetaService._effective_token(cred) == "plain-tok"

    def test_strict_ignores_plaintext_fallback(self, monkeypatch):
        monkeypatch.setattr(settings, "META_TOKEN_ENCRYPTION_STRICT", True)
        cred = MetaCredential(user_id=1, access_token="plain-tok", access_token_ciphertext=None)
        assert MetaService._effective_token(cred) is None


class TestBackfill:
    async def test_encrypts_plaintext_and_is_idempotent(self, meta_key, db_session, test_superuser):
        # a legacy plaintext-only credential (pre-retrofit row)
        cred = MetaCredential(user_id=test_superuser.id, access_token="legacy-plain")
        db_session.add(cred)
        await db_session.commit()

        result = await backfill_meta_tokens(db_session)
        assert result["encrypted"] == 1

        await db_session.refresh(cred)
        assert cred.access_token_ciphertext is not None
        assert crypto.decrypt_token(cred.access_token_ciphertext) == "legacy-plain"
        assert cred.access_token == "legacy-plain"  # plaintext kept until contract phase

        # idempotent: a second pass encrypts nothing new
        again = await backfill_meta_tokens(db_session)
        assert again["encrypted"] == 0

    async def test_fail_closed_without_key(self, monkeypatch, db_session):
        monkeypatch.delenv(crypto.ENV_VAR, raising=False)
        with pytest.raises(crypto.MetaCryptoError):
            await backfill_meta_tokens(db_session)

    async def test_empty_string_token_does_not_livelock(self, meta_key, db_session, test_superuser):
        # '' satisfies IS NOT NULL — without the length>0 filter this row would be
        # re-selected forever (livelock). It must terminate and leave the row untouched.
        cred = MetaCredential(user_id=test_superuser.id, access_token="")
        db_session.add(cred)
        await db_session.commit()
        result = await backfill_meta_tokens(db_session)
        assert result["encrypted"] == 0
        await db_session.refresh(cred)
        assert cred.access_token_ciphertext is None


class TestDecryptFailureSurfaced:
    async def test_undecryptable_token_sets_token_error_not_silent(self, db_session, test_superuser, monkeypatch):
        # C4-2: a ciphertext encrypted under a DIFFERENT key must surface token_error,
        # NOT a green connected/0-pages. Encrypt under key A, then switch to key B.
        monkeypatch.setenv(crypto.ENV_VAR, crypto.generate_key())
        ct, ver = crypto.encrypt_token("tok")
        cred = MetaCredential(
            user_id=test_superuser.id, access_token=None,
            access_token_ciphertext=ct, token_key_version=ver, is_active=True,
        )
        db_session.add(cred)
        await db_session.commit()
        monkeypatch.setenv(crypto.ENV_VAR, crypto.generate_key())  # key rotated → can't decrypt
        monkeypatch.setattr(settings, "META_TOKEN_ENCRYPTION_STRICT", True)

        status = await MetaService(db_session).get_connection_status(test_superuser.id)
        assert status["connected"] is True
        assert status["token_error"] is True  # decrypt failure surfaced, not swallowed
        assert status["pages"] == []


class TestStrictReadiness:
    async def test_counts_plaintext_only_and_pages(self, meta_key, db_session, test_superuser):
        from scripts.backfill_meta_token_encryption import strict_readiness
        cred = MetaCredential(user_id=test_superuser.id, access_token="legacy")  # plaintext-only
        db_session.add(cred)
        await db_session.commit()
        gates = await strict_readiness(db_session)
        assert gates["plaintext_only"] == 1  # NOT strict-ready until backfilled
        # after backfill, 0 remain
        await backfill_meta_tokens(db_session)
        assert (await strict_readiness(db_session))["plaintext_only"] == 0
