"""Tests for the proposal -> Stripe billing wiring.

Covers:
- ProposalBillingMixin schema validation (one_time vs subscription)
- _resolve_billing picks proposal.amount over quote.total
- accept_proposal_public spawns Stripe Invoice for one_time proposals
- accept_proposal_public spawns Stripe Checkout Session for subscriptions
- webhook invoice.paid flips proposal to 'paid'
- webhook checkout.session.completed stores subscription_id + flips to 'paid'

Stripe is stubbed at the _get_stripe() boundary (same pattern as
test_payments_webhook.py). Everything else uses real DB operations.
"""
from __future__ import annotations

import secrets
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.contacts.models import Contact
from src.payments.webhook_processor import WebhookProcessor
from src.proposals.models import Proposal
from src.proposals.schemas import ProposalBillingMixin
from src.proposals.service import ProposalService, _resolve_billing


# ---------------------------------------------------------------------------
# Stripe stub — a tiny object graph that mirrors the bits of the SDK
# our production code touches. Keeps tests hermetic without mocking
# internal business logic.
# ---------------------------------------------------------------------------


class _InvoiceRegistry:
    """Tracks every fake Stripe invoice the tests spawn so assertions can
    inspect the inputs the production code handed to Stripe.
    """

    def __init__(self) -> None:
        self.created: list[dict] = []
        self.items: list[dict] = []
        self.finalized: list[str] = []
        self.sent: list[str] = []


def _make_stripe_stub(invoice_registry: _InvoiceRegistry, session_url: str = "https://checkout.stripe.test/sess"):
    """Build a fake `stripe` module with the handful of entry points the
    proposal billing path uses.
    """

    class FakeInvoice:
        @staticmethod
        def create(**kwargs):
            invoice_registry.created.append(kwargs)
            return SimpleNamespace(
                id=f"in_test_{len(invoice_registry.created)}",
                hosted_invoice_url=f"https://invoice.stripe.test/{len(invoice_registry.created)}",
            )

        @staticmethod
        def finalize_invoice(invoice_id):
            invoice_registry.finalized.append(invoice_id)
            return SimpleNamespace(
                id=invoice_id,
                hosted_invoice_url=f"https://invoice.stripe.test/final_{invoice_id}",
            )

        @staticmethod
        def send_invoice(invoice_id):
            invoice_registry.sent.append(invoice_id)
            return SimpleNamespace(
                id=invoice_id,
                hosted_invoice_url=f"https://invoice.stripe.test/sent_{invoice_id}",
            )

        @staticmethod
        def void_invoice(invoice_id):
            return SimpleNamespace(id=invoice_id)

    class FakeInvoiceItem:
        @staticmethod
        def create(**kwargs):
            invoice_registry.items.append(kwargs)
            return SimpleNamespace(id=f"ii_test_{len(invoice_registry.items)}")

    class FakeCustomer:
        @staticmethod
        def create(**kwargs):
            return SimpleNamespace(id="cus_stub_1")

    class FakeSession:
        created: list[dict] = []

        @classmethod
        def create(cls, **kwargs):
            cls.created.append(kwargs)
            return SimpleNamespace(
                id=f"cs_test_{len(cls.created)}",
                url=session_url,
            )

    # Reset class-level storage between tests to avoid cross-test bleed.
    FakeSession.created = []

    checkout = SimpleNamespace(Session=FakeSession)

    return SimpleNamespace(
        api_key="sk_test_stub",
        Invoice=FakeInvoice,
        InvoiceItem=FakeInvoiceItem,
        Customer=FakeCustomer,
        checkout=checkout,
    )


# ---------------------------------------------------------------------------
# ProposalBillingMixin
# ---------------------------------------------------------------------------


class TestProposalBillingMixin:
    def test_one_time_accepts_plain_amount(self):
        m = ProposalBillingMixin(payment_type="one_time", amount=Decimal("500"))
        assert m.payment_type == "one_time"
        assert m.amount == Decimal("500")

    def test_subscription_requires_interval(self):
        with pytest.raises(ValueError):
            ProposalBillingMixin(payment_type="subscription", amount=Decimal("100"))

    def test_subscription_rejects_zero_count(self):
        with pytest.raises(ValueError):
            ProposalBillingMixin(
                payment_type="subscription",
                amount=Decimal("100"),
                recurring_interval="month",
                recurring_interval_count=0,
            )

    def test_one_time_rejects_recurring_hints(self):
        with pytest.raises(ValueError):
            ProposalBillingMixin(
                payment_type="one_time",
                amount=Decimal("100"),
                recurring_interval="month",
                recurring_interval_count=1,
            )

    def test_amount_must_be_positive(self):
        with pytest.raises(ValueError):
            ProposalBillingMixin(payment_type="one_time", amount=Decimal("0"))


# ---------------------------------------------------------------------------
# _resolve_billing
# ---------------------------------------------------------------------------


class TestResolveBilling:
    def test_prefers_proposal_amount_over_quote(self):
        quote = SimpleNamespace(
            total=Decimal("1000"),
            currency="USD",
            payment_type="one_time",
            recurring_interval=None,
            recurring_interval_count=None,
        )
        proposal = SimpleNamespace(
            amount=Decimal("500"),
            currency="USD",
            payment_type="one_time",
            recurring_interval=None,
            recurring_interval_count=None,
            quote=quote,
            title="Proposal title",
        )
        result = _resolve_billing(proposal)  # type: ignore[arg-type]
        assert result is not None
        assert result["amount"] == Decimal("500")
        assert result["payment_type"] == "one_time"

    def test_falls_back_to_quote_when_no_proposal_amount(self):
        quote = SimpleNamespace(
            total=Decimal("1000"),
            currency="USD",
            payment_type="subscription",
            recurring_interval="month",
            recurring_interval_count=3,
        )
        proposal = SimpleNamespace(
            amount=None,
            currency="USD",
            payment_type="one_time",
            recurring_interval=None,
            recurring_interval_count=None,
            quote=quote,
            title="Proposal title",
        )
        result = _resolve_billing(proposal)  # type: ignore[arg-type]
        assert result is not None
        assert result["amount"] == Decimal("1000")
        assert result["payment_type"] == "subscription"
        assert result["interval"] == "month"
        assert result["interval_count"] == 3

    def test_returns_none_when_no_amount_anywhere(self):
        proposal = SimpleNamespace(
            amount=None,
            currency="USD",
            payment_type="one_time",
            recurring_interval=None,
            recurring_interval_count=None,
            quote=None,
            title="Proposal title",
        )
        assert _resolve_billing(proposal) is None  # type: ignore[arg-type]

    def test_downgrades_subscription_without_interval(self):
        proposal = SimpleNamespace(
            amount=Decimal("500"),
            currency="USD",
            payment_type="subscription",
            recurring_interval=None,
            recurring_interval_count=None,
            quote=None,
            title="Proposal title",
        )
        result = _resolve_billing(proposal)  # type: ignore[arg-type]
        assert result is not None
        assert result["payment_type"] == "one_time"


# ---------------------------------------------------------------------------
# accept_proposal_public -> Stripe spawn
# ---------------------------------------------------------------------------


@pytest.fixture
async def billing_proposal(
    db_session: AsyncSession, test_user: User, test_contact: Contact,
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


class TestAcceptSpawnsBilling:
    @pytest.mark.asyncio
    async def test_one_time_accept_creates_invoice(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
        test_contact: Contact,
    ):
        registry = _InvoiceRegistry()
        stub = _make_stripe_stub(registry)

        with patch("src.payments.service._get_stripe", return_value=stub):
            service = ProposalService(db_session)
            accepted = await service.accept_proposal_public(
                billing_proposal,
                signer_name="Jane Client",
                signer_email=test_contact.email,
            )

        assert accepted.status == "awaiting_payment"
        assert accepted.stripe_invoice_id is not None
        assert accepted.stripe_payment_url is not None
        assert accepted.invoice_sent_at is not None
        # The invoice item should carry 50000 cents ($500.00).
        assert registry.items[0]["amount"] == 50000

    @pytest.mark.asyncio
    async def test_subscription_accept_creates_checkout_session(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
        test_contact: Contact,
    ):
        billing_proposal.payment_type = "subscription"
        billing_proposal.recurring_interval = "month"
        billing_proposal.recurring_interval_count = 3  # quarterly
        await db_session.commit()
        await db_session.refresh(billing_proposal)

        registry = _InvoiceRegistry()
        stub = _make_stripe_stub(registry)

        with patch("src.payments.service._get_stripe", return_value=stub), \
             patch("src.proposals.service.settings") as mock_settings:
            mock_settings.FRONTEND_BASE_URL = "https://crm.test"
            service = ProposalService(db_session)
            accepted = await service.accept_proposal_public(
                billing_proposal,
                signer_name="Jane Client",
                signer_email=test_contact.email,
            )

        assert accepted.status == "awaiting_payment"
        assert accepted.stripe_checkout_session_id is not None
        assert accepted.stripe_payment_url == "https://checkout.stripe.test/sess"
        sessions = stub.checkout.Session.created
        assert len(sessions) == 1
        line_item = sessions[0]["line_items"][0]
        assert line_item["price_data"]["recurring"] == {"interval": "month", "interval_count": 3}
        assert line_item["price_data"]["unit_amount"] == 50000

    @pytest.mark.asyncio
    async def test_accept_without_amount_stays_accepted(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
        test_contact: Contact,
    ):
        """Proposal with no amount and no quote -> no Stripe call, status stays accepted."""
        billing_proposal.amount = None
        await db_session.commit()
        await db_session.refresh(billing_proposal)

        # Even with Stripe configured, the billing helper should skip
        # because _resolve_billing returns None.
        with patch("src.payments.service._get_stripe") as mock_stripe:
            service = ProposalService(db_session)
            accepted = await service.accept_proposal_public(
                billing_proposal,
                signer_name="Jane Client",
                signer_email=test_contact.email,
            )
            mock_stripe.assert_not_called()

        assert accepted.status == "accepted"
        assert accepted.stripe_invoice_id is None
        assert accepted.stripe_checkout_session_id is None


# ---------------------------------------------------------------------------
# Webhook -> proposal paid
# ---------------------------------------------------------------------------


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
        # Should not raise even with no metadata.
        await processor._mark_proposal_paid_from_session({"id": "cs_other"})

    @pytest.mark.asyncio
    async def test_invoice_paid_idempotent(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Second invoice.paid for an already-paid proposal doesn't re-timestamp."""
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


# ---------------------------------------------------------------------------
# Resend payment link (idempotent, never spawns a duplicate invoice)
# ---------------------------------------------------------------------------


class _ResendStripeStub:
    """Stripe stub for resend tests; Invoice.create raises so any duplicate is caught."""

    def __init__(self, *, status: str = "open"):
        self._status = status
        self.retrieved: list[str] = []
        self.sent: list[str] = []
        self.created: list[dict] = []

    @property
    def Invoice(self):
        outer = self

        class _Invoice:
            @staticmethod
            def retrieve(invoice_id):
                outer.retrieved.append(invoice_id)
                return SimpleNamespace(
                    id=invoice_id,
                    status=outer._status,
                    hosted_invoice_url=f"https://invoice.stripe.test/{invoice_id}",
                )

            @staticmethod
            def send_invoice(invoice_id):
                outer.sent.append(invoice_id)
                return SimpleNamespace(id=invoice_id)

            @staticmethod
            def create(**kwargs):  # pragma: no cover - failing test signal
                outer.created.append(kwargs)
                raise AssertionError(
                    "resend_payment_link must never create a new Invoice",
                )

        return _Invoice


class TestResendPaymentLink:
    @pytest.mark.asyncio
    async def test_open_invoice_resend_calls_send_only(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
    ):
        billing_proposal.status = "awaiting_payment"
        billing_proposal.stripe_invoice_id = "in_existing_123"
        billing_proposal.stripe_payment_url = "https://invoice.stripe.test/in_existing_123"
        await db_session.commit()

        stub = _ResendStripeStub(status="open")
        with patch("src.payments.service._get_stripe", return_value=stub):
            service = ProposalService(db_session)
            result = await service.resend_payment_link(billing_proposal)

        assert stub.retrieved == ["in_existing_123"]
        assert stub.sent == ["in_existing_123"]
        assert stub.created == []  # critical: no duplicate invoice
        assert result["action"] == "resent"
        assert result["stripe_invoice_id"] == "in_existing_123"

    @pytest.mark.asyncio
    async def test_already_paid_reconciles_db(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
    ):
        billing_proposal.status = "awaiting_payment"
        billing_proposal.stripe_invoice_id = "in_paid_456"
        await db_session.commit()

        stub = _ResendStripeStub(status="paid")
        with patch("src.payments.service._get_stripe", return_value=stub):
            service = ProposalService(db_session)
            result = await service.resend_payment_link(billing_proposal)

        await db_session.refresh(billing_proposal)
        assert billing_proposal.status == "paid"
        assert billing_proposal.paid_at is not None
        assert stub.sent == []  # don't re-email when already paid
        assert result["action"] == "already_paid_reconciled"

    @pytest.mark.asyncio
    async def test_voided_invoice_refuses(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
    ):
        billing_proposal.status = "awaiting_payment"
        billing_proposal.stripe_invoice_id = "in_void_789"
        await db_session.commit()

        stub = _ResendStripeStub(status="void")
        with patch("src.payments.service._get_stripe", return_value=stub):
            service = ProposalService(db_session)
            with pytest.raises(ValueError, match="void"):
                await service.resend_payment_link(billing_proposal)

        assert stub.sent == []  # never re-emit a voided invoice
        assert stub.created == []

    @pytest.mark.asyncio
    async def test_already_paid_proposal_refuses(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
    ):
        billing_proposal.status = "paid"
        billing_proposal.paid_at = datetime.now(UTC)
        billing_proposal.stripe_invoice_id = "in_paid_999"
        await db_session.commit()

        stub = _ResendStripeStub(status="paid")
        with patch("src.payments.service._get_stripe", return_value=stub):
            service = ProposalService(db_session)
            with pytest.raises(ValueError, match="already paid"):
                await service.resend_payment_link(billing_proposal)

        assert stub.retrieved == []  # short-circuit before touching Stripe

    @pytest.mark.asyncio
    async def test_resend_cooldown_blocks_rapid_repeats(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
    ):
        """A second Resend within the cooldown window must be refused without
        touching Stripe — protects the customer's inbox from rapid clicks."""
        billing_proposal.status = "awaiting_payment"
        billing_proposal.stripe_invoice_id = "in_cool_001"
        billing_proposal.invoice_sent_at = datetime.now(UTC)  # just sent
        await db_session.commit()

        stub = _ResendStripeStub(status="open")
        with patch("src.payments.service._get_stripe", return_value=stub):
            service = ProposalService(db_session)
            with pytest.raises(ValueError, match="please wait"):
                await service.resend_payment_link(billing_proposal)

        assert stub.retrieved == []
        assert stub.sent == []

    @pytest.mark.asyncio
    async def test_resend_after_cooldown_succeeds_and_bumps_timestamp(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
    ):
        """After the cooldown elapses, resend works AND bumps invoice_sent_at
        so the next cooldown is measured from this resend, not the original."""
        from datetime import timedelta
        old_sent = datetime.now(UTC) - timedelta(seconds=120)
        billing_proposal.status = "awaiting_payment"
        billing_proposal.stripe_invoice_id = "in_cool_002"
        billing_proposal.invoice_sent_at = old_sent
        await db_session.commit()

        stub = _ResendStripeStub(status="open")
        with patch("src.payments.service._get_stripe", return_value=stub):
            service = ProposalService(db_session)
            result = await service.resend_payment_link(billing_proposal)

        assert result["action"] == "resent"
        assert stub.sent == ["in_cool_002"]
        await db_session.refresh(billing_proposal)
        # SQLite drops tzinfo on roundtrip; normalize both to naive UTC for
        # the comparison. The semantic check is "the timestamp moved forward".
        bumped = billing_proposal.invoice_sent_at
        if bumped.tzinfo is None:
            bumped = bumped.replace(tzinfo=UTC)
        assert bumped > old_sent


class TestRetryBilling:
    """retry-billing must refuse on any Stripe artifact, not just payment_url —
    a partial spawn that set invoice_id but missed the URL fetch can't be
    allowed to create a second invoice."""

    @pytest.mark.asyncio
    async def test_refuses_when_invoice_id_set_without_payment_url(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
    ):
        billing_proposal.status = "awaiting_payment"
        billing_proposal.stripe_invoice_id = "in_partial_777"
        billing_proposal.stripe_payment_url = None  # the gap
        await db_session.commit()

        registry = _InvoiceRegistry()
        stub = _make_stripe_stub(registry)
        with patch("src.payments.service._get_stripe", return_value=stub):
            service = ProposalService(db_session)
            with pytest.raises(ValueError, match="already has a Stripe artifact"):
                await service.retry_billing(billing_proposal)

        assert registry.created == []  # crucial: no second invoice attempted

    @pytest.mark.asyncio
    async def test_refuses_when_checkout_session_set(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
    ):
        billing_proposal.status = "awaiting_payment"
        billing_proposal.stripe_checkout_session_id = "cs_partial_888"
        billing_proposal.stripe_payment_url = None
        await db_session.commit()

        registry = _InvoiceRegistry()
        stub = _make_stripe_stub(registry)
        with patch("src.payments.service._get_stripe", return_value=stub):
            service = ProposalService(db_session)
            with pytest.raises(ValueError, match="already has a Stripe artifact"):
                await service.retry_billing(billing_proposal)

    @pytest.mark.asyncio
    async def test_retry_after_billing_error_spawns_invoice(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
    ):
        """The intended happy path: accept hit a Stripe outage, billing_error
        is set, no Stripe artifact landed. Retry should create the invoice
        and clear the error."""
        billing_proposal.status = "accepted"
        billing_proposal.billing_error = "Stripe is currently unavailable"
        billing_proposal.stripe_invoice_id = None
        billing_proposal.stripe_checkout_session_id = None
        billing_proposal.stripe_payment_url = None
        await db_session.commit()

        registry = _InvoiceRegistry()
        stub = _make_stripe_stub(registry)
        with patch("src.payments.service._get_stripe", return_value=stub):
            service = ProposalService(db_session)
            updated = await service.retry_billing(billing_proposal)

        assert updated.status == "awaiting_payment"
        assert updated.stripe_invoice_id is not None
        assert updated.stripe_payment_url is not None
        assert updated.billing_error is None
        assert len(registry.created) == 1


class _CheckoutResendStub:
    """Stripe stub for the subscription/checkout resend path.

    Tracks the one or two sessions returned by `Session.retrieve` (keyed
    by id) and the args every `Session.create` was called with — so tests
    can assert "the second call used a different idempotency key".
    """

    def __init__(self, sessions: dict[str, str]):
        self._sessions = sessions
        self.retrieved: list[str] = []
        self.created: list[dict] = []
        outer = self

        class _Session:
            @staticmethod
            def retrieve(session_id):
                outer.retrieved.append(session_id)
                return SimpleNamespace(
                    id=session_id,
                    status=outer._sessions.get(session_id, "expired"),
                )

            @staticmethod
            def create(**kwargs):
                outer.created.append(kwargs)
                new_id = f"cs_new_{len(outer.created)}"
                return SimpleNamespace(
                    id=new_id,
                    url=f"https://checkout.stripe.test/{new_id}",
                )

        class _Customer:
            @staticmethod
            def create(**kwargs):
                return SimpleNamespace(id="cus_stub_1")

        self.checkout = SimpleNamespace(Session=_Session)
        self.Customer = _Customer
        self.api_key = "sk_test_stub"


class TestResendCheckoutSession:
    """`resend_payment_link` for proposals on the subscription Checkout flow.

    Open sessions re-emit the existing URL via email; expired sessions
    spawn a replacement with a fresh idempotency key derived from the
    old session id."""

    @pytest.fixture
    async def sub_proposal(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
    ) -> Proposal:
        billing_proposal.payment_type = "subscription"
        billing_proposal.recurring_interval = "month"
        billing_proposal.recurring_interval_count = 1
        billing_proposal.status = "awaiting_payment"
        billing_proposal.stripe_checkout_session_id = "cs_old_111"
        billing_proposal.stripe_payment_url = "https://checkout.stripe.test/cs_old_111"
        await db_session.commit()
        await db_session.refresh(billing_proposal)
        return billing_proposal

    @pytest.mark.asyncio
    async def test_expired_session_regenerates(
        self, db_session: AsyncSession, sub_proposal: Proposal,
    ):
        stub = _CheckoutResendStub({"cs_old_111": "expired"})
        with patch("src.payments.service._get_stripe", return_value=stub), \
             patch("src.proposals.service.settings") as mock_settings:
            mock_settings.FRONTEND_BASE_URL = "https://crm.test"
            service = ProposalService(db_session)
            result = await service.resend_payment_link(sub_proposal)

        assert result["action"] == "regenerated"
        assert result["stripe_checkout_session_id"] == "cs_new_1"
        assert result["stripe_payment_url"].endswith("cs_new_1")
        assert len(stub.created) == 1
        assert stub.created[0]["idempotency_key"] == "proposal_sub_{}_after_cs_old_111".format(
            sub_proposal.id
        )

        await db_session.refresh(sub_proposal)
        assert sub_proposal.stripe_checkout_session_id == "cs_new_1"
        assert sub_proposal.stripe_payment_url.endswith("cs_new_1")

    @pytest.mark.asyncio
    async def test_open_session_emails_existing_url(
        self, db_session: AsyncSession, sub_proposal: Proposal,
    ):
        stub = _CheckoutResendStub({"cs_old_111": "open"})
        with patch("src.payments.service._get_stripe", return_value=stub), \
             patch("src.proposals.service.settings") as mock_settings:
            mock_settings.FRONTEND_BASE_URL = "https://crm.test"
            service = ProposalService(db_session)
            result = await service.resend_payment_link(sub_proposal)

        assert result["action"] == "resent"
        assert result["stripe_checkout_session_id"] == "cs_old_111"
        assert stub.created == []  # critical: no new session

    @pytest.mark.asyncio
    async def test_complete_session_reconciles_to_paid(
        self, db_session: AsyncSession, sub_proposal: Proposal,
    ):
        stub = _CheckoutResendStub({"cs_old_111": "complete"})
        with patch("src.payments.service._get_stripe", return_value=stub):
            service = ProposalService(db_session)
            result = await service.resend_payment_link(sub_proposal)

        assert result["action"] == "already_paid_reconciled"
        assert stub.created == []
        await db_session.refresh(sub_proposal)
        assert sub_proposal.status == "paid"
        assert sub_proposal.paid_at is not None

    @pytest.mark.asyncio
    async def test_consecutive_regenerations_use_distinct_idempotency_keys(
        self, db_session: AsyncSession, sub_proposal: Proposal,
    ):
        """Two deliberate regenerations (after waiting out the cooldown) must
        not share an idempotency key — otherwise Stripe would return the
        cached newly-created session and we'd never actually rotate."""
        from datetime import timedelta

        stub = _CheckoutResendStub({"cs_old_111": "expired"})
        with patch("src.payments.service._get_stripe", return_value=stub), \
             patch("src.proposals.service.settings") as mock_settings:
            mock_settings.FRONTEND_BASE_URL = "https://crm.test"
            service = ProposalService(db_session)
            await service.resend_payment_link(sub_proposal)

        await db_session.refresh(sub_proposal)
        # Mark the new session expired and back-date the cooldown so a
        # second resend is allowed.
        stub._sessions[sub_proposal.stripe_checkout_session_id] = "expired"
        sub_proposal.invoice_sent_at = datetime.now(UTC) - timedelta(seconds=120)
        await db_session.commit()

        with patch("src.payments.service._get_stripe", return_value=stub), \
             patch("src.proposals.service.settings") as mock_settings:
            mock_settings.FRONTEND_BASE_URL = "https://crm.test"
            service = ProposalService(db_session)
            await service.resend_payment_link(sub_proposal)

        assert len(stub.created) == 2
        keys = {call["idempotency_key"] for call in stub.created}
        assert len(keys) == 2, "second regenerate must use a fresh idempotency key"


class TestIdempotencyKeysAreDeterministic:
    """A uuid-randomized idempotency key defeats Stripe's dedup. Same logical
    operation (same proposal_id) must produce the same key so a Stripe-side
    retry returns the cached invoice instead of creating a duplicate."""

    @pytest.mark.asyncio
    async def test_proposal_invoice_idempotency_key_omits_uuid(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
        test_contact: Contact,
    ):
        registry = _InvoiceRegistry()
        stub = _make_stripe_stub(registry)
        with patch("src.payments.service._get_stripe", return_value=stub):
            service = ProposalService(db_session)
            await service.accept_proposal_public(
                billing_proposal,
                signer_name="Jane Client",
                signer_email=test_contact.email,
            )

        invoice_call = registry.created[0]
        assert invoice_call.get("idempotency_key") == f"proposal_{billing_proposal.id}_invoice_v1"
        item_call = registry.items[0]
        assert item_call.get("idempotency_key") == f"proposal_{billing_proposal.id}_invoice_v1_item"

    @pytest.mark.asyncio
    async def test_proposal_subscription_idempotency_key_omits_uuid(
        self,
        db_session: AsyncSession,
        billing_proposal: Proposal,
        test_contact: Contact,
    ):
        billing_proposal.payment_type = "subscription"
        billing_proposal.recurring_interval = "month"
        billing_proposal.recurring_interval_count = 1
        await db_session.commit()
        await db_session.refresh(billing_proposal)

        registry = _InvoiceRegistry()
        stub = _make_stripe_stub(registry)
        with patch("src.payments.service._get_stripe", return_value=stub), \
             patch("src.proposals.service.settings") as mock_settings:
            mock_settings.FRONTEND_BASE_URL = "https://crm.test"
            service = ProposalService(db_session)
            await service.accept_proposal_public(
                billing_proposal,
                signer_name="Jane Client",
                signer_email=test_contact.email,
            )

        sessions = stub.checkout.Session.created
        assert sessions[0].get("idempotency_key") == f"proposal_sub_{billing_proposal.id}_v1"
