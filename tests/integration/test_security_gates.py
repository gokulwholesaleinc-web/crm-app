"""Integration tests verifying the security gates added in PR #280.

Tests confirm that unauthorized callers are rejected — not merely that
the happy-path works. Each test hits the real test DB via the client fixture.
"""

import io

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# =============================================================================
# Opportunities router retired (PR #328, 2026-05-14) — ownership-gate
# tests removed. Sequences feature removed in PR #309 — ditto. Both
# asserted 403 from now-404 endpoints, which was meaningless after the
# removals.
# =============================================================================
# File upload: oversized upload → 400 (ValueError from service layer)
# =============================================================================

class TestFileUploadSizeGuard:
    """File upload endpoint must reject files exceeding MAX_UPLOAD_SIZE."""

    async def test_oversized_upload_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact,
        monkeypatch,
    ):
        """Upload larger than MAX_UPLOAD_SIZE should be rejected with 400."""
        from src.attachments import service as attachment_service
        # Set a tiny cap so we don't need to allocate a real 10 MB buffer.
        monkeypatch.setattr(attachment_service, "MAX_UPLOAD_SIZE", 10)

        big_content = b"x" * 11  # 11 bytes > 10 byte cap
        response = await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("big.txt", io.BytesIO(big_content), "text/plain")},
            data={"entity_type": "contacts", "entity_id": str(test_contact.id)},
        )
        assert response.status_code == 400

    async def test_upload_without_content_length_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact,
    ):
        """Upload with file.size=None (chunked) should be rejected with 400."""
        import io as _io

        from src.attachments import service as attachment_service

        # Simulate a chunked upload by patching file.size to None at the service layer.
        original_upload = attachment_service.AttachmentService.upload_file

        async def patched_upload(self, file, entity_type, entity_id, user_id, category=None):
            file.size = None  # simulate missing Content-Length
            return await original_upload(self, file, entity_type, entity_id, user_id, category)

        attachment_service.AttachmentService.upload_file = patched_upload

        try:
            response = await client.post(
                "/api/attachments/upload",
                headers=auth_headers,
                files={"file": ("test.txt", _io.BytesIO(b"hello"), "text/plain")},
                data={"entity_type": "contacts", "entity_id": str(test_contact.id)},
            )
            assert response.status_code == 400
        finally:
            attachment_service.AttachmentService.upload_file = original_upload


# =============================================================================
# Meta POST webhook: unconfigured (both secrets empty) → 503
# =============================================================================

class TestMetaWebhookPostGuard:
    """Meta POST webhook must reject when META_WEBHOOK_VERIFY_TOKEN is unset."""

    async def test_post_webhook_unconfigured_returns_503(
        self,
        client: AsyncClient,
        monkeypatch,
    ):
        """POST to Meta webhook when verify token is empty should return 503."""
        from src.config import settings
        monkeypatch.setattr(settings, "META_WEBHOOK_VERIFY_TOKEN", "")
        monkeypatch.setattr(settings, "META_APP_SECRET", "")

        response = await client.post(
            "/api/meta/webhook",
            json={"object": "page", "entry": []},
        )
        assert response.status_code == 503

    async def test_post_webhook_secret_set_but_no_token_returns_503(
        self,
        client: AsyncClient,
        monkeypatch,
    ):
        """POST to Meta webhook when app secret set but verify token empty → 503."""
        from src.config import settings
        monkeypatch.setattr(settings, "META_WEBHOOK_VERIFY_TOKEN", "")
        monkeypatch.setattr(settings, "META_APP_SECRET", "some_secret")

        response = await client.post(
            "/api/meta/webhook",
            json={"object": "page", "entry": []},
        )
        assert response.status_code == 503
