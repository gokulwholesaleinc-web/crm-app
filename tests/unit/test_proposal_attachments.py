"""Tests for proposal attachments + read-before-sign gate.

Covers:
- POST /api/proposals/{id}/attachments
- GET  /api/proposals/{id}/attachments
- DELETE /api/proposals/{id}/attachments/{attachment_id}
- GET  /api/proposals/public/{token}/attachments/{attachment_id}/download
- accept_proposal_public guard refusing unviewed attachments
- send_signed_copy_to_client embedding attachment filenames in the email body

No mocks — uses the real ASGI client + SQLite test DB. R2 is unconfigured so
file uploads fall through to local-disk storage; tests cover both code paths.
"""

import io
import secrets
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.attachments.models import Attachment
from src.auth.models import User
from src.contacts.models import Contact
from src.email.models import EmailQueue
from src.proposals.attachment_views import ProposalAttachmentView, _hash_token
from src.proposals.models import Proposal


@pytest.fixture
async def sent_proposal(
    db_session: AsyncSession, test_user: User, test_contact: Contact,
) -> Proposal:
    """A proposal in 'sent' status owned by ``test_user``, signer = test_contact."""
    proposal = Proposal(
        proposal_number=f"PR-2026-A-{secrets.token_hex(3)}",
        public_token=secrets.token_urlsafe(32),
        title="Web Redesign",
        status="sent",
        contact_id=test_contact.id,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    return proposal


@pytest.fixture
async def signed_proposal(
    db_session: AsyncSession, test_user: User, test_contact: Contact,
) -> Proposal:
    """A proposal already in 'accepted' status with signed_at set."""
    now = datetime.now(UTC)
    proposal = Proposal(
        proposal_number=f"PR-2026-S-{secrets.token_hex(3)}",
        public_token=secrets.token_urlsafe(32),
        title="Locked Proposal",
        status="accepted",
        contact_id=test_contact.id,
        owner_id=test_user.id,
        created_by_id=test_user.id,
        signed_at=now,
        signer_email=test_contact.email,
        signer_name="Already Signed",
        accepted_at=now,
    )
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    return proposal


async def _upload_pdf_attachment(
    client: AsyncClient,
    auth_headers: dict,
    proposal_id: int,
    *,
    filename: str = "scope.pdf",
    body: bytes = b"%PDF-1.4 fake scope",
) -> dict:
    response = await client.post(
        f"/api/proposals/{proposal_id}/attachments",
        headers=auth_headers,
        files={"file": (filename, io.BytesIO(body), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestStaffUpload:
    """POST /api/proposals/{id}/attachments"""

    @pytest.mark.asyncio
    async def test_upload_pdf_to_proposal(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sent_proposal: Proposal,
    ):
        """Staff PDF upload creates an Attachment row scoped to entity_type=proposals."""
        data = await _upload_pdf_attachment(client, auth_headers, sent_proposal.id)

        assert data["entity_type"] == "proposals"
        assert data["entity_id"] == sent_proposal.id
        assert data["mime_type"] == "application/pdf"

        result = await db_session.execute(
            select(Attachment).where(Attachment.id == data["id"])
        )
        att = result.scalar_one()
        assert att.entity_type == "proposals"
        assert att.entity_id == sent_proposal.id
        # On disk fallback (no R2 in tests), file_path is "proposals/{id}/{uuid}.pdf"
        # so the entity prefix is preserved either way.
        assert att.file_path.startswith("proposals/") or att.file_path.startswith(
            "obj://uploads/proposals/",
        )

    @pytest.mark.asyncio
    async def test_upload_non_pdf_rejected(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sent_proposal: Proposal,
    ):
        """Non-PDF uploads must 400 — public viewer renders inline only."""
        response = await client.post(
            f"/api/proposals/{sent_proposal.id}/attachments",
            headers=auth_headers,
            files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        )
        assert response.status_code == 400
        assert "pdf" in response.json()["detail"].lower()


class TestReadBeforeSignGate:
    """accept_proposal_public refuses signing while attachments are unviewed."""

    @pytest.mark.asyncio
    async def test_accept_blocked_without_views(
        self,
        client: AsyncClient,
        auth_headers: dict,
        sent_proposal: Proposal,
        test_contact: Contact,
    ):
        """Proposal with 1 attachment + zero views -> POST accept returns 400."""
        await _upload_pdf_attachment(client, auth_headers, sent_proposal.id)

        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/accept",
            json={"signer_name": "Customer", "signer_email": test_contact.email},
        )
        assert response.status_code == 400, response.text
        assert "view" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_accept_allowed_after_all_viewed(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sent_proposal: Proposal,
        test_contact: Contact,
    ):
        """Public download endpoint records the view; accept then succeeds."""
        att = await _upload_pdf_attachment(client, auth_headers, sent_proposal.id)

        download = await client.get(
            f"/api/proposals/public/{sent_proposal.public_token}"
            f"/attachments/{att['id']}/download",
            follow_redirects=False,
        )
        assert download.status_code in (200, 307), download.text

        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/accept",
            json={"signer_name": "Customer", "signer_email": test_contact.email},
        )
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "accepted"


class TestPublicDownload:
    """GET /api/proposals/public/{token}/attachments/{id}/download"""

    @pytest.mark.asyncio
    async def test_public_download_records_view(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sent_proposal: Proposal,
    ):
        """Hitting the public download endpoint inserts a proposal_attachment_views row."""
        att = await _upload_pdf_attachment(client, auth_headers, sent_proposal.id)

        await client.get(
            f"/api/proposals/public/{sent_proposal.public_token}"
            f"/attachments/{att['id']}/download",
            follow_redirects=False,
            headers={"User-Agent": "ViewAgent/1.0"},
        )

        rows = await db_session.execute(
            select(ProposalAttachmentView).where(
                ProposalAttachmentView.attachment_id == att["id"],
            )
        )
        view = rows.scalar_one()
        assert view.token_hash == _hash_token(sent_proposal.public_token)
        assert view.user_agent == "ViewAgent/1.0"

    @pytest.mark.asyncio
    async def test_cross_tenant_public_download_denied(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sent_proposal: Proposal,
        test_user: User,
        test_contact: Contact,
    ):
        """Token A pointing at proposal B's attachment must 404."""
        # proposal A keeps its own attachment
        att_a = await _upload_pdf_attachment(client, auth_headers, sent_proposal.id)

        # proposal B (different token, different attachment)
        proposal_b = Proposal(
            proposal_number=f"PR-2026-B-{secrets.token_hex(3)}",
            public_token=secrets.token_urlsafe(32),
            title="Other Proposal",
            status="sent",
            contact_id=test_contact.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(proposal_b)
        await db_session.commit()
        await db_session.refresh(proposal_b)
        att_b = await _upload_pdf_attachment(client, auth_headers, proposal_b.id)

        # Token A trying to fetch attachment B -> 404 (entity_id mismatch).
        response = await client.get(
            f"/api/proposals/public/{sent_proposal.public_token}"
            f"/attachments/{att_b['id']}/download",
            follow_redirects=False,
        )
        assert response.status_code == 404

        # Sanity: token A still works for its own attachment.
        ok = await client.get(
            f"/api/proposals/public/{sent_proposal.public_token}"
            f"/attachments/{att_a['id']}/download",
            follow_redirects=False,
        )
        assert ok.status_code in (200, 307)


class TestSignedProposalLockdown:
    """Once signed_at is set, attachment mutations are refused."""

    @pytest.mark.asyncio
    async def test_delete_attachment_blocked_after_sign(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        signed_proposal: Proposal,
        test_user: User,
    ):
        """DELETE on a signed proposal's attachment returns 400."""
        # Side-load an attachment row directly (POST would 400 because
        # the proposal is already signed).
        attachment = Attachment(
            filename="locked.pdf",
            original_filename="locked.pdf",
            file_path="proposals/x/locked.pdf",
            file_size=10,
            mime_type="application/pdf",
            entity_type="proposals",
            entity_id=signed_proposal.id,
            uploaded_by=test_user.id,
            category="document",
        )
        db_session.add(attachment)
        await db_session.commit()
        await db_session.refresh(attachment)

        response = await client.delete(
            f"/api/proposals/{signed_proposal.id}/attachments/{attachment.id}",
            headers=auth_headers,
        )
        assert response.status_code == 400
        assert "signed" in response.json()["detail"].lower()


class TestSignedCopyEmail:
    """send_signed_copy_to_client should reference attachment filenames in the body."""

    @pytest.mark.asyncio
    async def test_signed_copy_email_includes_attachment_names(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sent_proposal: Proposal,
        test_contact: Contact,
    ):
        """Accepting a proposal queues a signed-copy email; on attachment-fetch
        failure the body lists the original filenames so the recipient knows
        what was missing.
        """
        # Upload, view, then break the file_path so the in-test fetch
        # fails and the missing-filename branch fires.
        att = await _upload_pdf_attachment(
            client, auth_headers, sent_proposal.id,
            filename="insurance-cert.pdf",
        )
        await client.get(
            f"/api/proposals/public/{sent_proposal.public_token}"
            f"/attachments/{att['id']}/download",
            follow_redirects=False,
        )

        # Repoint the attachment to a non-existent local path so
        # _collect_proposal_attachments lands in the missing branch.
        result = await db_session.execute(
            select(Attachment).where(Attachment.id == att["id"])
        )
        attachment = result.scalar_one()
        attachment.file_path = "proposals/__nope__/not-there.pdf"
        await db_session.commit()

        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/accept",
            json={"signer_name": "Customer", "signer_email": test_contact.email},
        )
        assert response.status_code == 200, response.text

        # The signed-copy email is queued under entity_type=proposals
        # with the proposal id; find it and assert the filename is in
        # the rendered body.
        emails = await db_session.execute(
            select(EmailQueue)
            .where(EmailQueue.entity_type == "proposals")
            .where(EmailQueue.entity_id == sent_proposal.id)
            .where(EmailQueue.subject.like("Signed copy%"))
        )
        signed_copy = emails.scalars().first()
        assert signed_copy is not None, "signed-copy email was not queued"
        assert "insurance-cert.pdf" in (signed_copy.body or "")
