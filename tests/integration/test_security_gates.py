"""Integration tests verifying the security gates added in PR #280.

Tests confirm that unauthorized callers are rejected — not merely that
the happy-path works. Each test hits the real test DB via the client fixture.
"""

import io
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import create_access_token
from src.opportunities.models import Opportunity, PipelineStage
from src.sequences.models import Sequence


# =============================================================================
# move_opportunity: non-owner sales_rep → 403
# =============================================================================

class TestMoveOpportunityOwnership:
    """move_opportunity must reject callers who don't own the opportunity."""

    async def test_non_owner_sales_rep_cannot_move_opportunity(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_opportunity: Opportunity,
        test_pipeline_stage: PipelineStage,
        _sales_rep_user: User,
        seed_roles: list,
    ):
        """Sales rep who does not own an opportunity should receive 403 on move."""
        # _sales_rep_user is a different user from test_user (who owns test_opportunity)
        token = create_access_token(data={"sub": str(_sales_rep_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.post(
            f"/api/opportunities/{test_opportunity.id}/move",
            headers=headers,
            json={"new_stage_id": test_pipeline_stage.id},
        )
        assert response.status_code == 403

    async def test_owner_can_move_opportunity(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_opportunity: Opportunity,
        test_pipeline_stage: PipelineStage,
        auth_headers: dict,
    ):
        """Owner should be able to move their own opportunity."""
        response = await client.post(
            f"/api/opportunities/{test_opportunity.id}/move",
            headers=auth_headers,
            json={"new_stage_id": test_pipeline_stage.id},
        )
        # 200 OK (same stage is a no-op, still succeeds)
        assert response.status_code == 200


# =============================================================================
# sequences PUT/DELETE: non-manager (sales_rep) → 403
# =============================================================================

class TestSequenceOwnershipGate:
    """PUT/DELETE on sequences must require manager-or-above."""

    async def _create_sequence(self, db_session: AsyncSession, user: User) -> Sequence:
        seq = Sequence(
            name="Test Sequence",
            description="A test sequence",
            steps=[],
            is_active=True,
            created_by_id=user.id,
        )
        db_session.add(seq)
        await db_session.commit()
        await db_session.refresh(seq)
        return seq

    async def test_sales_rep_cannot_update_sequence(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        _sales_rep_user: User,
        seed_roles: list,
    ):
        """Sales rep should receive 403 on sequence PUT."""
        seq = await self._create_sequence(db_session, test_user)
        token = create_access_token(data={"sub": str(_sales_rep_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.put(
            f"/api/sequences/{seq.id}",
            headers=headers,
            json={"name": "Attempted rename"},
        )
        assert response.status_code == 403

    async def test_sales_rep_cannot_delete_sequence(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        _sales_rep_user: User,
        seed_roles: list,
    ):
        """Sales rep should receive 403 on sequence DELETE."""
        seq = await self._create_sequence(db_session, test_user)
        token = create_access_token(data={"sub": str(_sales_rep_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.delete(
            f"/api/sequences/{seq.id}",
            headers=headers,
        )
        assert response.status_code == 403

    async def test_manager_can_update_sequence(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        _manager_user: User,
        seed_roles: list,
    ):
        """Manager should be able to update a sequence."""
        seq = await self._create_sequence(db_session, test_user)
        token = create_access_token(data={"sub": str(_manager_user.id)})
        headers = {"Authorization": f"Bearer {token}"}

        response = await client.put(
            f"/api/sequences/{seq.id}",
            headers=headers,
            json={"name": "Manager Renamed"},
        )
        assert response.status_code == 200


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
        from src.attachments import service as attachment_service
        from fastapi import UploadFile
        import io as _io

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
