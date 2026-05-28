"""Tests for the Sign-to-Confirm e-signature flow (PR4).

Covers the new payload shape, validation gates, signature persistence,
and the no-Stripe-after-accept invariant introduced 2026-05-14 when
the typed-name accept form was replaced with a drawn-signature modal.

No mocks — uses the real ASGI client + SQLite test DB. R2 is
unconfigured in tests so the master-PDF stamp path is exercised at
the service-method level (validation only) and the pure stamper is
unit-tested in ``backend/src/proposals/tests/test_pdf_stamper.py``.
"""

import secrets
from base64 import b64encode

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.models import User
from src.contacts.models import Contact
from src.proposals.models import Proposal
from src.proposals.service import (
    PROPOSAL_ACCEPTANCE_METHOD_DRAWN_SIGNATURE,
    PROPOSAL_ESIGN_DISCLOSURE_VERSION,
    ProposalService,
)
from src.whitelabel.models import Tenant, TenantSettings, TenantUser

# Smallest possible valid PNG (1x1 transparent). Inline so tests don't
# need a binary fixture file on disk.
_ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63000000000005000158a8c4d70000000049454e44ae426082"
)
_VALID_SIGNATURE_B64 = "data:image/png;base64," + b64encode(_ONE_PIXEL_PNG).decode("ascii")


@pytest.fixture
async def sent_proposal(
    db_session: AsyncSession, test_user: User, test_contact: Contact,
) -> Proposal:
    proposal = Proposal(
        proposal_number=f"PR-2026-SIGN-{secrets.token_hex(4)}",
        public_token=secrets.token_urlsafe(32),
        title="Brand Refresh Engagement",
        status="sent",
        contact_id=test_contact.id,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    return proposal


def _accept_payload(
    email: str,
    *,
    signature: str = _VALID_SIGNATURE_B64,
    agreed: bool = True,
    signer_name: str = "Jane Customer",
) -> dict:
    return {
        "signer_name": signer_name,
        "signer_email": email,
        "signature_image": signature,
        "agreed_to_terms": agreed,
    }


class TestSignToConfirmAccept:
    """POST /api/proposals/public/{token}/accept (Sign-to-Confirm payload)."""

    @pytest.mark.asyncio
    async def test_persists_signature_image_bytes(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_proposal: Proposal,
        test_contact: Contact,
    ):
        """Drawn signature PNG is decoded and persisted on the proposal row."""
        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/accept",
            json=_accept_payload(test_contact.email),
        )
        assert response.status_code == 200, response.text

        await db_session.refresh(sent_proposal)
        assert sent_proposal.status == "accepted"
        assert sent_proposal.signature_image == _ONE_PIXEL_PNG

    @pytest.mark.asyncio
    async def test_persisted_disclosure_matches_what_signer_saw(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_proposal: Proposal,
        test_contact: Contact,
    ):
        """The persisted evidence snapshot is byte-identical to the
        disclosure the public page served — guards against the on-screen
        text and the stored record drifting apart."""
        sent_proposal.terms_and_conditions = "Per-proposal acceptance terms."
        await db_session.commit()

        # What the signer actually saw on the public page.
        view = await client.get(
            f"/api/proposals/public/{sent_proposal.public_token}",
        )
        assert view.status_code == 200, view.text
        served_disclosure = view.json()["esign_disclosure"]
        assert served_disclosure
        assert "recorded as acceptance" in served_disclosure

        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/accept",
            json=_accept_payload(test_contact.email),
        )
        assert response.status_code == 200, response.text

        await db_session.refresh(sent_proposal)
        assert sent_proposal.agreed_to_terms_at is not None
        assert sent_proposal.signed_at == sent_proposal.agreed_to_terms_at
        assert sent_proposal.terms_and_conditions_snapshot == (
            "Per-proposal acceptance terms."
        )
        assert sent_proposal.esign_disclosure_version == (
            PROPOSAL_ESIGN_DISCLOSURE_VERSION
        )
        # The whole point of the snapshot: it equals the served text.
        assert sent_proposal.esign_disclosure_snapshot == served_disclosure
        assert sent_proposal.acceptance_method == (
            PROPOSAL_ACCEPTANCE_METHOD_DRAWN_SIGNATURE
        )

    @pytest.mark.asyncio
    async def test_rejects_oversize_signature_image(
        self,
        client: AsyncClient,
        sent_proposal: Proposal,
        test_contact: Contact,
    ):
        """A signature blob over the 200 KB cap is rejected at the boundary,
        so it can never reach the embed step and silently drop from the
        countersigned PDF."""
        oversize = b"\x89PNG\r\n\x1a\n" + b"\x00" * 250_000  # valid magic, >200 KB
        payload = _accept_payload(
            test_contact.email,
            signature="data:image/png;base64," + b64encode(oversize).decode("ascii"),
        )
        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/accept",
            json=payload,
        )
        assert response.status_code == 400, response.text

    @pytest.mark.asyncio
    async def test_rejects_when_terms_not_agreed(
        self,
        client: AsyncClient,
        sent_proposal: Proposal,
        test_contact: Contact,
    ):
        """ESIGN Act consent must be ticked — 400 if agreed_to_terms is False."""
        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/accept",
            json=_accept_payload(test_contact.email, agreed=False),
        )
        assert response.status_code == 400
        assert "agree" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_rejects_invalid_base64_signature(
        self,
        client: AsyncClient,
        sent_proposal: Proposal,
        test_contact: Contact,
    ):
        """Garbage in signature_image produces a 400, not a 500."""
        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/accept",
            json=_accept_payload(test_contact.email, signature="not-base64!!!"),
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_rejects_non_png_signature(
        self,
        client: AsyncClient,
        sent_proposal: Proposal,
        test_contact: Contact,
    ):
        """A valid base64 payload that isn't a PNG produces a 400."""
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 64
        payload = "data:image/png;base64," + b64encode(fake_jpeg).decode("ascii")
        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/accept",
            json=_accept_payload(test_contact.email, signature=payload),
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_no_stripe_artifact_after_accept(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_proposal: Proposal,
        test_contact: Contact,
    ):
        """Lorenzo's ask 2026-05-14: accept never auto-spawns Stripe."""
        # Set a real billable amount so the OLD code path would have
        # invoked the Stripe-spawn helper. The new path must skip it.
        sent_proposal.payment_type = "one_time"
        sent_proposal.amount = 1500
        await db_session.commit()

        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/accept",
            json=_accept_payload(test_contact.email),
        )
        assert response.status_code == 200, response.text

        await db_session.refresh(sent_proposal)
        assert sent_proposal.stripe_invoice_id is None
        assert sent_proposal.stripe_checkout_session_id is None
        assert sent_proposal.stripe_payment_url is None
        assert sent_proposal.status == "accepted"  # not awaiting_payment
        assert sent_proposal.billing_error is None

    @pytest.mark.asyncio
    async def test_no_stamp_path_when_no_master_pdf(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_proposal: Proposal,
        test_contact: Contact,
    ):
        """Without a master contract on file, signed_pdf_path stays NULL —
        signature_image + audit row alone are ESIGN-compliant."""
        assert sent_proposal.master_contract_pdf_path is None

        response = await client.post(
            f"/api/proposals/public/{sent_proposal.public_token}/accept",
            json=_accept_payload(test_contact.email),
        )
        assert response.status_code == 200

        await db_session.refresh(sent_proposal)
        assert sent_proposal.signed_pdf_path is None


class TestEffectiveTermsResolver:
    """ProposalService.get_effective_terms_and_conditions"""

    @pytest.mark.asyncio
    async def test_per_proposal_override_wins(
        self,
        db_session: AsyncSession,
        sent_proposal: Proposal,
    ):
        sent_proposal.terms_and_conditions = "Per-proposal override body."
        await db_session.commit()

        service = ProposalService(db_session)
        body = await service.get_effective_terms_and_conditions(sent_proposal)
        assert body == "Per-proposal override body."

    @pytest.mark.asyncio
    async def test_falls_back_to_tenant_default(
        self,
        db_session: AsyncSession,
        sent_proposal: Proposal,
        test_user: User,
    ):
        tenant = Tenant(name="Test Co", slug="test-co")
        db_session.add(tenant)
        await db_session.flush()
        settings = TenantSettings(
            tenant_id=tenant.id,
            default_terms_and_conditions="Tenant-wide default body.",
        )
        membership = TenantUser(
            tenant_id=tenant.id, user_id=test_user.id, is_primary=True,
        )
        db_session.add_all([settings, membership])
        await db_session.commit()

        service = ProposalService(db_session)
        body = await service.get_effective_terms_and_conditions(sent_proposal)
        assert body == "Tenant-wide default body."

    @pytest.mark.asyncio
    async def test_returns_none_when_nothing_configured(
        self,
        db_session: AsyncSession,
        sent_proposal: Proposal,
    ):
        service = ProposalService(db_session)
        body = await service.get_effective_terms_and_conditions(sent_proposal)
        assert body is None


class TestMasterContractValidation:
    """ProposalService.upload_master_contract_pdf — input validation only.

    The R2 upload itself is exercised by the attachments harness; here
    we only assert the magic-byte sniff + size cap reject obviously
    bad payloads before any storage round-trip.
    """

    @pytest.mark.asyncio
    async def test_rejects_non_pdf_magic(
        self, db_session: AsyncSession, sent_proposal: Proposal,
    ):
        service = ProposalService(db_session)
        with pytest.raises(ValueError, match="PDF"):
            await service.upload_master_contract_pdf(
                sent_proposal,
                content=b"PK\x03\x04not-a-pdf",  # zip header (.docx)
                filename="contract.pdf",
            )

    @pytest.mark.asyncio
    async def test_rejects_empty_upload(
        self, db_session: AsyncSession, sent_proposal: Proposal,
    ):
        service = ProposalService(db_session)
        with pytest.raises(ValueError, match="empty"):
            await service.upload_master_contract_pdf(
                sent_proposal, content=b"", filename="empty.pdf",
            )

    @pytest.mark.asyncio
    async def test_rejects_oversized(
        self, db_session: AsyncSession, sent_proposal: Proposal,
    ):
        service = ProposalService(db_session)
        # 26 MB of valid-looking PDF — passes magic-byte sniff, fails cap.
        oversized = b"%PDF-1.7\n" + b"\x00" * (26 * 1024 * 1024)
        with pytest.raises(ValueError, match="25 MB"):
            await service.upload_master_contract_pdf(
                sent_proposal, content=oversized, filename="huge.pdf",
            )
