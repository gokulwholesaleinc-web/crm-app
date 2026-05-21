"""Tests for proposal billing remnants after sign-to-confirm stopped billing.

Covers:
- accept_proposal_public never spawns Stripe artifacts.
- Stripe webhooks can still mark proposals paid when artifacts already exist.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.models import User
from src.contacts.models import Contact
from src.payments.webhook_processor import WebhookProcessor
from src.proposals.models import Proposal
from src.proposals.service import ProposalService

# Smallest possible valid PNG (1x1 transparent); used as the drawn
# signature payload for service-level Sign-to-Confirm calls that
# bypass the HTTP layer's base64 decode.
_ONE_PIXEL_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63000000000005000158a8c4d70000000049454e44ae426082"
)


@pytest.fixture
async def billing_proposal(
    db_session: AsyncSession,
    test_user: User,
    test_contact: Contact,
) -> Proposal:
    proposal = Proposal(
        proposal_number="PR-2026-BILL-001",
        public_token=secrets.token_urlsafe(32),
        title="Monthly retainer",
        status="sent",
        contact_id=test_contact.id,
        owner_id=test_user.id,
        created_by_id=test_user.id,
        amount=Decimal("500.00"),
        currency="USD",
        payment_type="one_time",
    )
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)
    return proposal


class TestAcceptNeverSpawnsBilling:
    """Signature acceptance records the signature; billing remains manual."""

    @pytest.mark.asyncio
    async def test_one_time_accept_does_not_create_invoice(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
        test_contact: Contact,
    ):
        with patch("src.payments.service._get_stripe") as mock_stripe:
            service = ProposalService(db_session)
            accepted = await service.accept_proposal_public(
                billing_proposal,
                signer_name="Jane Client",
                signer_email=test_contact.email,
                signature_image=_ONE_PIXEL_PNG,
                agreed_to_terms=True,
            )
            mock_stripe.assert_not_called()

        assert accepted.status == "accepted"
        assert accepted.stripe_invoice_id is None
        assert accepted.stripe_payment_url is None
        assert accepted.invoice_sent_at is None

    @pytest.mark.asyncio
    async def test_subscription_accept_does_not_create_checkout_session(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
        test_contact: Contact,
    ):
        billing_proposal.payment_type = "subscription"
        billing_proposal.recurring_interval = "month"
        billing_proposal.recurring_interval_count = 3
        await db_session.commit()
        await db_session.refresh(billing_proposal)

        with patch("src.payments.service._get_stripe") as mock_stripe:
            service = ProposalService(db_session)
            accepted = await service.accept_proposal_public(
                billing_proposal,
                signer_name="Jane Client",
                signer_email=test_contact.email,
                signature_image=_ONE_PIXEL_PNG,
                agreed_to_terms=True,
            )
            mock_stripe.assert_not_called()

        assert accepted.status == "accepted"
        assert accepted.stripe_checkout_session_id is None
        assert accepted.stripe_payment_url is None

    @pytest.mark.asyncio
    async def test_accept_without_amount_stays_accepted(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
        test_contact: Contact,
    ):
        billing_proposal.amount = None
        await db_session.commit()
        await db_session.refresh(billing_proposal)

        with patch("src.payments.service._get_stripe") as mock_stripe:
            service = ProposalService(db_session)
            accepted = await service.accept_proposal_public(
                billing_proposal,
                signer_name="Jane Client",
                signer_email=test_contact.email,
                signature_image=_ONE_PIXEL_PNG,
                agreed_to_terms=True,
            )
            mock_stripe.assert_not_called()

        assert accepted.status == "accepted"
        assert accepted.stripe_invoice_id is None
        assert accepted.stripe_checkout_session_id is None


class TestWebhookFlipsProposalPaid:
    @pytest.mark.asyncio
    async def test_invoice_paid_flips_linked_proposal(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        invoice_id = "in_test_webhook"
        proposal = Proposal(
            proposal_number="PR-2026-WH-001",
            public_token=secrets.token_urlsafe(32),
            title="Webhook test",
            status="awaiting_payment",
            owner_id=test_user.id,
            created_by_id=test_user.id,
            amount=Decimal("100.00"),
            currency="USD",
            payment_type="one_time",
            stripe_invoice_id=invoice_id,
        )
        db_session.add(proposal)
        await db_session.commit()
        await db_session.refresh(proposal)

        processor = WebhookProcessor(db_session)
        await processor._mark_proposal_paid_from_invoice(invoice_id)

        await db_session.refresh(proposal)
        assert proposal.status == "paid"
        assert proposal.paid_at is not None

    @pytest.mark.asyncio
    async def test_checkout_session_completed_marks_proposal_paid(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        proposal = Proposal(
            proposal_number="PR-2026-WH-002",
            public_token=secrets.token_urlsafe(32),
            title="Webhook sub test",
            status="awaiting_payment",
            owner_id=test_user.id,
            created_by_id=test_user.id,
            amount=Decimal("100.00"),
            currency="USD",
            payment_type="subscription",
            recurring_interval="month",
            recurring_interval_count=1,
            stripe_checkout_session_id="cs_test_done",
        )
        db_session.add(proposal)
        await db_session.commit()
        await db_session.refresh(proposal)

        processor = WebhookProcessor(db_session)
        await processor._mark_proposal_paid_from_session({
            "id": "cs_test_done",
            "metadata": {"proposal_id": str(proposal.id)},
            "subscription": "sub_test_webhook",
            "payment_status": "paid",
        })

        await db_session.refresh(proposal)
        assert proposal.status == "paid"
        assert proposal.stripe_subscription_id == "sub_test_webhook"
        assert proposal.paid_at is not None

    @pytest.mark.asyncio
    async def test_checkout_session_without_metadata_is_noop(
        self,
        db_session: AsyncSession,
    ):
        processor = WebhookProcessor(db_session)
        await processor._mark_proposal_paid_from_session({"id": "cs_other"})

    @pytest.mark.asyncio
    async def test_invoice_paid_idempotent(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        invoice_id = "in_test_idem"
        proposal = Proposal(
            proposal_number="PR-2026-WH-003",
            public_token=secrets.token_urlsafe(32),
            title="Idempotency test",
            status="paid",
            paid_at=datetime(2026, 1, 1, tzinfo=UTC),
            owner_id=test_user.id,
            created_by_id=test_user.id,
            amount=Decimal("100.00"),
            currency="USD",
            payment_type="one_time",
            stripe_invoice_id=invoice_id,
        )
        db_session.add(proposal)
        await db_session.commit()
        await db_session.refresh(proposal)

        original_paid_at = proposal.paid_at
        processor = WebhookProcessor(db_session)
        await processor._mark_proposal_paid_from_invoice(invoice_id)

        await db_session.refresh(proposal)
        assert proposal.paid_at == original_paid_at
