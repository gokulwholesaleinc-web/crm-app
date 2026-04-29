"""Proposal service layer."""

import logging
import os
import re
import secrets
from datetime import UTC, datetime
from decimal import Decimal
from html import escape

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import selectinload

from src.config import settings
from src.core.base_service import BaseService, CRUDService, StatusTransitionMixin
from src.core.constants import DEFAULT_PAGE_SIZE
from src.core.filtering import build_token_search
from src.core.url_safety import UnsafeUrlError, validate_public_url
from src.email.branded_templates import TenantBrandingHelper, render_proposal_email
from src.email.pdf_render import pdf_logo_allowed_hosts, render_html_to_pdf
from src.email.service import EmailService
from src.email.types import EmailAttachment
from src.payments.service import PaymentService
from src.proposals.models import Proposal, ProposalTemplate, ProposalView
from src.proposals.schemas import ProposalCreate, ProposalUpdate

logger = logging.getLogger(__name__)

_TEMPLATE_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def _resolve_billing(proposal: Proposal) -> dict | None:
    """Flatten a proposal's billable terms into a dict the PaymentService can act on.

    Preference order:
      1. Proposal's own structured pricing fields (amount + payment_type)
      2. Linked Quote's total + payment_type + recurring_interval(_count)

    Returns ``None`` when no billable amount can be derived, which tells
    ``_maybe_spawn_billing`` to skip Stripe entirely and leave the
    proposal in plain ``accepted`` state.
    """
    # Pick the source that carries a positive amount, preferring the
    # proposal's own fields over the linked quote's. The proposal and
    # quote share the same relevant attribute names (amount/total,
    # currency, payment_type, recurring_interval[_count]) so downstream
    # attribute lookups don't branch.
    source = None
    raw_amount = proposal.amount
    if raw_amount is not None and Decimal(str(raw_amount)) > 0:
        source = proposal
    elif proposal.quote is not None:
        q_total = getattr(proposal.quote, "total", None)
        if q_total is not None and Decimal(str(q_total)) > 0:
            source = proposal.quote
            raw_amount = q_total

    if source is None or raw_amount is None:
        return None

    amount = Decimal(str(raw_amount))
    currency = getattr(source, "currency", "USD") or "USD"
    payment_type = getattr(source, "payment_type", "one_time") or "one_time"
    interval = getattr(source, "recurring_interval", None)
    interval_count = getattr(source, "recurring_interval_count", None)

    if payment_type == "subscription":
        if not interval:
            # Mis-configured subscription (no interval). Fall back to a
            # one-time charge rather than silently emailing an endless
            # retainer that the client didn't agree to.
            payment_type = "one_time"
            interval = None
            interval_count = None
        else:
            interval_count = interval_count or 1

    return {
        "payment_type": payment_type,
        "amount": amount,
        "currency": currency,
        "interval": interval,
        "interval_count": interval_count,
        "description": proposal.title,
    }


def _designated_email_for(proposal: Proposal) -> str:
    """Lowercased email authorized to sign this proposal.

    Explicit ``designated_signer_email`` wins; otherwise fall back to the
    linked contact's email. Returns "" when neither is available.
    """
    if proposal.designated_signer_email:
        return proposal.designated_signer_email.strip().lower()
    if proposal.contact and proposal.contact.email:
        return proposal.contact.email.strip().lower()
    return ""


def _assert_signer_matches(proposal: Proposal, signer_email: str | None) -> None:
    """Guard: the supplied signer_email must match the proposal's designated
    recipient (case-insensitive). Shared by accept/reject so a forwarded
    public link can't be used by a third party to sign or reject.
    """
    expected = _designated_email_for(proposal)
    given = (signer_email or "").strip().lower()
    if not expected:
        raise ValueError("Proposal has no recipient email on file")
    if not given or given != expected:
        raise ValueError("Signer email does not match the proposal recipient")


class ProposalService(StatusTransitionMixin, CRUDService[Proposal, ProposalCreate, ProposalUpdate]):
    """Service for Proposal CRUD operations."""

    model = Proposal
    create_exclude_fields = set()
    update_exclude_fields = set()

    def _get_eager_load_options(self):
        return [
            selectinload(Proposal.opportunity),
            selectinload(Proposal.contact),
            selectinload(Proposal.company),
            selectinload(Proposal.quote),
            selectinload(Proposal.views),
        ]

    async def _generate_proposal_number(self) -> str:
        """Generate auto-incrementing proposal number: PR-{year}-{seq}."""
        year = datetime.now(UTC).year
        prefix = f"PR-{year}-"

        result = await self.db.execute(
            select(func.count(Proposal.id)).where(
                Proposal.proposal_number.like(f"{prefix}%")
            )
        )
        count = result.scalar() or 0
        seq = count + 1
        return f"{prefix}{seq:04d}"

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        search: str | None = None,
        status: str | None = None,
        contact_id: int | None = None,
        company_id: int | None = None,
        opportunity_id: int | None = None,
        owner_id: int | None = None,
        shared_entity_ids: list[int] | None = None,
    ) -> tuple[list[Proposal], int]:
        """Get paginated list of proposals with filters."""
        query = (
            select(Proposal)
            .options(
                selectinload(Proposal.opportunity),
                selectinload(Proposal.contact),
                selectinload(Proposal.company),
                selectinload(Proposal.quote),
            )
        )

        if search:
            search_condition = build_token_search(search, Proposal.title, Proposal.proposal_number)
            if search_condition is not None:
                query = query.where(search_condition)

        if status:
            query = query.where(Proposal.status == status)

        if contact_id:
            query = query.where(Proposal.contact_id == contact_id)

        if company_id:
            query = query.where(Proposal.company_id == company_id)

        if opportunity_id:
            query = query.where(Proposal.opportunity_id == opportunity_id)

        if owner_id:
            if shared_entity_ids:
                query = query.where(
                    or_(Proposal.owner_id == owner_id, Proposal.id.in_(shared_entity_ids))
                )
            else:
                query = query.where(Proposal.owner_id == owner_id)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Proposal.created_at.desc())

        result = await self.db.execute(query)
        proposals = list(result.scalars().all())

        return proposals, total

    async def update(
        self,
        instance: Proposal,
        data: ProposalUpdate,
        user_id: int,
    ) -> Proposal:
        """Update a proposal, refusing edits once the customer has signed.

        After signature, the proposal carries the same legal weight as a
        handwritten contract — letting a CRM user mutate scope/pricing
        out from under the signed PDF would silently break the binding
        copy the customer holds. Reject the write and force the user to
        clone or void instead.
        """
        if instance.signed_at is not None:
            raise ValueError(
                "Proposal has been signed and is locked — clone it to make changes",
            )
        return await super().update(instance, data, user_id)

    async def create(self, data: ProposalCreate, user_id: int) -> Proposal:
        """Create a new proposal with auto-generated number + public token."""
        proposal_number = await self._generate_proposal_number()

        proposal_data = data.model_dump()
        proposal_data["proposal_number"] = proposal_number
        proposal_data["public_token"] = secrets.token_urlsafe(32)
        proposal_data["created_by_id"] = user_id
        # Default ownership to the creating user when the form didn't
        # specify one. owner_id is load-bearing downstream: it drives
        # tenant-branding lookups (public proposal page colors/logo),
        # signed-PDF email routing through the owner's Gmail OAuth,
        # and "my proposals" data scoping. A NULL owner silently falls
        # back to the generic "CRM" defaults and Resend, which is why
        # early Link Creative proposals rendered unbranded.
        if proposal_data.get("owner_id") is None:
            proposal_data["owner_id"] = user_id

        proposal = Proposal(**proposal_data)
        self.db.add(proposal)
        await self.db.flush()
        await self.db.refresh(proposal)

        return proposal

    async def accept_proposal_public(
        self,
        proposal: Proposal,
        signer_name: str,
        signer_email: str,
        signer_ip: str | None = None,
        signer_user_agent: str | None = None,
    ) -> Proposal:
        """Accept a proposal via the public link with e-signature data.

        Signer-email check uses ``designated_signer_email`` when set, otherwise
        falls back to the linked contact's email. Prevents a third party who
        got hold of the public URL from signing as the customer with an
        attacker-controlled email.

        After the e-signature is recorded, this tries to spawn the Stripe
        artifact that the proposal's payment_type implies (Invoice for
        one_time, Checkout Session for subscription). A Stripe failure
        does NOT unwind the acceptance — the proposal stays accepted and
        the CRM user can resend billing manually.

        Raises ValueError if the proposal is not in sent/viewed state or
        the signer_email doesn't match.
        """
        if proposal.status not in ("sent", "viewed"):
            raise ValueError(f"Cannot accept proposal in '{proposal.status}' status")

        # Hard-block expired proposals server-side. The public page
        # already shows "Expired" in the UI, but without this a signer
        # could craft a direct POST and sign past the expiry, which
        # undermines the "Valid until" commitment they saw.
        if proposal.valid_until and proposal.valid_until < datetime.now(UTC).date():
            raise ValueError(
                f"This proposal expired on {proposal.valid_until.isoformat()} "
                "and can no longer be accepted",
            )

        _assert_signer_matches(proposal, signer_email)

        # Atomic status transition: conditional UPDATE guarded by the
        # same (sent|viewed) whitelist. If two accept requests arrive
        # concurrently, only one row update will match — the other
        # returns rowcount=0 and we raise instead of spawning a second
        # Stripe Invoice / Checkout Session.
        now = datetime.now(UTC)
        stmt = (
            update(Proposal)
            .where(Proposal.id == proposal.id)
            .where(Proposal.status.in_(("sent", "viewed")))
            .values(
                status="accepted",
                accepted_at=now,
                signer_name=signer_name,
                signer_email=signer_email,
                signer_ip=signer_ip,
                signer_user_agent=signer_user_agent,
                signed_at=now,
            )
        )
        result = await self.db.execute(stmt)
        if result.rowcount == 0:
            raise ValueError(
                "Proposal was accepted by another signer moments ago",
            )
        await self.db.flush()
        await self.db.refresh(proposal)

        # Mail the signer a signed PDF copy for their records. Runs
        # before billing spawn so the client has the countersigned doc
        # in hand even if Stripe is down.
        await self.send_signed_copy_to_client(proposal)

        await self._maybe_spawn_billing(proposal)

        await self.db.refresh(proposal)
        return proposal

    async def _maybe_spawn_billing(self, proposal: Proposal) -> None:
        """Create the Stripe Invoice or Checkout Session for an accepted
        proposal, if pricing is resolvable and Stripe is configured.

        Mutates the proposal row with the resulting Stripe ids + payment
        url and moves status to 'awaiting_payment'. Stripe errors are
        captured on ``proposal.billing_error`` (so the CRM admin can see
        them and retry) instead of bubbling up and unwinding the
        acceptance — the client signed, that has to stick.
        """
        billing = _resolve_billing(proposal)
        if billing is None:
            return

        payments = PaymentService(self.db)
        try:
            if billing["payment_type"] == "one_time":
                result = await payments.create_invoice_for_proposal(
                    proposal_id=proposal.id,
                    contact_id=proposal.contact_id,
                    company_id=proposal.company_id,
                    amount=billing["amount"],
                    currency=billing["currency"],
                    description=billing["description"],
                    owner_id=proposal.owner_id,
                )
                proposal.stripe_invoice_id = result["stripe_invoice_id"]
                proposal.stripe_payment_url = result["stripe_payment_url"]
            else:
                base = settings.FRONTEND_BASE_URL.rstrip("/")
                if not base:
                    proposal.billing_error = (
                        "FRONTEND_BASE_URL is not configured; cannot build "
                        "subscription checkout return URL"
                    )
                    logger.warning(
                        "FRONTEND_BASE_URL is not set; skipping subscription "
                        "checkout for proposal %s",
                        proposal.id,
                    )
                    await self.db.flush()
                    return
                public_path = f"/proposals/public/{proposal.public_token}"
                result = await payments.create_subscription_checkout_for_proposal(
                    proposal_id=proposal.id,
                    contact_id=proposal.contact_id,
                    company_id=proposal.company_id,
                    amount=billing["amount"],
                    currency=billing["currency"],
                    description=billing["description"],
                    interval=billing["interval"],
                    interval_count=billing["interval_count"],
                    success_url=f"{base}{public_path}?paid=1",
                    cancel_url=f"{base}{public_path}",
                )
                proposal.stripe_checkout_session_id = result["stripe_checkout_session_id"]
                proposal.stripe_payment_url = result["stripe_payment_url"]
        except ValueError as exc:
            # Stripe disabled, customer-resolution failed, or an API
            # error bubbled up. Record the error on the proposal so the
            # CRM admin can see "billing setup failed" and retry; don't
            # unwind the acceptance.
            logger.warning(
                "Billing spawn failed for proposal %s: %s", proposal.id, exc,
            )
            proposal.billing_error = str(exc)
            await self.db.flush()
            return

        proposal.status = "awaiting_payment"
        proposal.invoice_sent_at = datetime.now(UTC)
        proposal.billing_error = None
        await self.db.flush()

    async def retry_billing(self, proposal: Proposal) -> Proposal:
        """Re-run billing spawn for a proposal that previously failed.

        Caller must already have authorization on the proposal
        (enforced at the router). Idempotent: if the proposal already
        has a ``stripe_payment_url`` or is past 'awaiting_payment',
        refuses so we don't create a duplicate charge.
        """
        if proposal.status not in ("accepted", "awaiting_payment"):
            raise ValueError(
                "Only accepted/awaiting_payment proposals can be retried",
            )
        if proposal.stripe_payment_url:
            raise ValueError(
                "Proposal already has a payment link; cannot retry",
            )
        # _maybe_spawn_billing mutates `proposal` in-place and flushes,
        # so we can return the same instance — no refresh required.
        await self._maybe_spawn_billing(proposal)
        return proposal

    async def reject_proposal_public(
        self,
        proposal: Proposal,
        reason: str | None = None,
        signer_ip: str | None = None,
        signer_user_agent: str | None = None,
        signer_email: str | None = None,
    ) -> Proposal:
        """Reject a proposal via the public link.

        Validates the signer_email against the designated or contact
        email, same as accept. Without this check, anyone who received a
        forwarded copy of the proposal link could permanently reject it.
        """
        if proposal.status not in ("sent", "viewed"):
            raise ValueError(f"Cannot reject proposal in '{proposal.status}' status")

        _assert_signer_matches(proposal, signer_email)

        now = datetime.now(UTC)
        proposal.status = "rejected"
        proposal.rejected_at = now
        proposal.rejection_reason = reason
        proposal.signer_ip = signer_ip
        proposal.signer_user_agent = signer_user_agent
        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def record_view(
        self, proposal_id: int, ip_address: str | None = None, user_agent: str | None = None
    ) -> Proposal:
        """Record a view on a proposal and increment view_count."""
        proposal = await self.get_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        view = ProposalView(
            proposal_id=proposal_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(view)

        now = datetime.now(UTC)
        proposal.view_count = (proposal.view_count or 0) + 1
        proposal.last_viewed_at = now

        # Auto-transition from sent to viewed
        if proposal.status == "sent":
            proposal.status = "viewed"
            proposal.viewed_at = now

        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def get_public_proposal(self, token: str) -> Proposal | None:
        """Get a proposal by its unguessable public token.

        Token-based lookup replaces the old sequential proposal_number
        enumeration. Caller should also use hmac.compare_digest on the
        returned row's public_token before trusting it.
        """
        if not token or len(token) < 16:
            return None
        query = (
            select(Proposal)
            .options(
                selectinload(Proposal.contact),
                selectinload(Proposal.company),
            )
            .where(Proposal.public_token == token)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def send_proposal_email(
        self, proposal_id: int, user_id: int, attach_pdf: bool = False
    ) -> None:
        """Send branded proposal email to the contact's email."""
        proposal = await self.get_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")
        if not proposal.contact_id:
            raise ValueError("Proposal has no associated contact")

        from src.contacts.models import Contact
        contact_result = await self.db.execute(
            select(Contact).where(Contact.id == proposal.contact_id)
        )
        contact = contact_result.scalar_one_or_none()
        if not contact or not contact.email:
            raise ValueError("Contact has no email address")

        branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)

        # Build public view URL using the unguessable token (not
        # proposal_number, which is enumerable). Mint one on the fly
        # for pre-migration rows.
        if not proposal.public_token:
            proposal.public_token = secrets.token_urlsafe(32)
            await self.db.flush()
        base_url = os.getenv("FRONTEND_URL", "http://localhost:3000")
        view_url = f"{base_url}/proposals/public/{proposal.public_token}"

        proposal_data = {
            "proposal_title": proposal.title,
            "client_name": contact.first_name if hasattr(contact, "first_name") else str(contact),
            "summary": proposal.executive_summary or proposal.content or "",
            "total": proposal.pricing_section or "",
            "currency": "USD",
            "view_url": view_url,
        }
        subject, html_body = render_proposal_email(branding, proposal_data)

        attachments: list[EmailAttachment] | None = None
        if attach_pdf:
            try:
                pdf_bytes = await self.generate_proposal_pdf(proposal_id, user_id)
            except Exception as exc:
                logger.warning(
                    "PDF render failed for proposal %s — sending email without attachment: %s",
                    proposal_id, exc,
                )
            else:
                attachments = [EmailAttachment(
                    filename=f"proposal-{proposal.proposal_number}.pdf",
                    content=pdf_bytes,
                    content_type="application/pdf",
                )]

        email_service = EmailService(self.db)
        await email_service.queue_email(
            to_email=contact.email,
            subject=subject,
            body=html_body,
            sent_by_id=user_id,
            entity_type="proposals",
            entity_id=proposal.id,
            attachments=attachments,
        )

        # Mark proposal as sent
        if proposal.status == "draft":
            proposal.status = "sent"
            proposal.sent_at = datetime.now(UTC)
            await self.db.flush()
            await self.db.refresh(proposal)

    async def generate_proposal_pdf(
        self,
        proposal_id: int,
        user_id: int,
        include_signature: bool = False,
    ) -> bytes:
        """Generate a branded proposal PDF in the corporate-professional
        aesthetic that mirrors the public web view.

        When ``include_signature`` is True and the proposal has been
        signed, the PDF includes a signature section with the full
        e-signature audit (name, email, IP, user-agent, timestamp).

        PDF-specific notes:
        - Uses <table> layout instead of flexbox (weasyprint's flex
          has page-fragmentation bugs — issues #2076 + #2163).
        - Omits `text-wrap: balance/pretty` (weasyprint ignores them),
          uses `max-width` constraints on prose blocks instead.
        - Plain business-document styling: clean sans throughout,
          section titles with a short accent rule, no § numbering or
          editorial drama.
        """
        proposal = await self.get_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)

        company_name_raw = branding.get("company_name") or "CRM"
        company_name = escape(company_name_raw)
        accent = escape(branding.get("primary_color") or "#6366f1")
        footer_text = branding.get("footer_text") or ""

        # Pre-validate the logo URL: if it fails the SSRF check, omit the
        # <img> entirely rather than handing weasyprint a URL it will
        # later refuse and log as an error per page render.
        logo_html = ""
        logo_is_image = False
        logo_url = branding.get("logo_url") or ""
        if logo_url:
            try:
                validate_public_url(
                    logo_url,
                    allowed_schemes=("https",),
                    allowed_hostnames=pdf_logo_allowed_hosts(),
                )
                logo_html = (
                    f'<img src="{escape(logo_url)}" alt="{company_name}" class="letterhead-logo" />'
                )
                logo_is_image = True
            except UnsafeUrlError as exc:
                logger.warning(
                    "Skipping proposal logo for tenant user %s: %s", user_id, exc
                )
        if not logo_html:
            initial = escape((company_name_raw or "P")[0].upper())
            logo_html = f'<span class="letterhead-initial">{initial}</span>'

        # When the uploaded logo is an image that already contains the
        # wordmark (common case for branded PNG/SVG marks), suppress
        # the text company name to avoid "Link Creative  Link Creative".
        letterhead_company_html = (
            "" if logo_is_image else f'<span class="letterhead-company">{company_name}</span>'
        )

        # ---------- Title / cover metadata ----------
        contact_name = ""
        if proposal.contact:
            contact_name = getattr(proposal.contact, "full_name", "") or ""

        secondary_company = ""
        if proposal.company and getattr(proposal.company, "name", None):
            _cname = proposal.company.name  # type: ignore[assignment]
            if _cname and _cname != company_name_raw:
                secondary_company = _cname

        valid_html = ""
        if proposal.valid_until:
            date_str = proposal.valid_until.strftime("%B %d, %Y")
            label = "Expired" if proposal.valid_until < datetime.now(UTC).date() else "Valid until"
            valid_html = (
                f'<p class="cover-validity">{escape(label)} '
                f'<span class="tabular">{escape(date_str)}</span></p>'
            )

        # ---------- Structured pricing block ----------
        pricing_block_html = ""
        cadence_label_map = {
            ("month", 1): "Monthly",
            ("month", 3): "Quarterly",
            ("month", 6): "Bi-yearly",
            ("year", 1): "Yearly",
        }
        amount = getattr(proposal, "amount", None)
        currency = (getattr(proposal, "currency", None) or "USD").upper()
        is_subscription_pricing = False
        if amount is not None:
            try:
                amount_val = Decimal(str(amount))
            except (ArithmeticError, ValueError, TypeError):
                amount_val = None  # type: ignore[assignment]
            if amount_val is not None and amount_val > 0:
                symbol = {"USD": "$", "EUR": "€", "GBP": "£", "CAD": "$", "AUD": "$"}.get(currency, "")
                num_str = f"{amount_val:,.2f}"
                display_amount = f"{symbol}{num_str}" if symbol else f"{currency} {num_str}"

                payment_type = getattr(proposal, "payment_type", "one_time")
                interval = getattr(proposal, "recurring_interval", None)
                interval_count = getattr(proposal, "recurring_interval_count", None) or 1
                is_subscription_pricing = payment_type == "subscription" and bool(interval)
                cadence_text = ""
                if is_subscription_pricing and interval:
                    cadence_text = cadence_label_map.get(
                        (interval, interval_count),
                        f"Every {interval_count} {interval}{'s' if interval_count > 1 else ''}",
                    )

                label = "Recurring fee" if is_subscription_pricing else "Total"
                cadence_cell = (
                    f'<td class="pricing-cadence">billed {escape(cadence_text.lower())}</td>'
                    if cadence_text else ""
                )
                pricing_block_html = f"""
<table class="pricing-block" cellpadding="0" cellspacing="0"><tr>
  <td>
    <div class="pricing-label">{escape(label)}</div>
    <div class="pricing-amount tabular">{escape(display_amount)}</div>
  </td>
  {cadence_cell}
</tr></table>
"""

        # ---------- Content sections ----------
        section_data = [
            ("Executive Summary", proposal.executive_summary),
            ("Scope of Work", proposal.scope_of_work),
            ("Timeline", proposal.timeline),
            ("Terms & Conditions", proposal.terms),
        ]
        populated_content = [(t, c) for t, c in section_data if c]

        sections_html = ""

        def _section(title_text: str, body_html: str) -> str:
            return (
                '<section class="doc-section">'
                f'  <div class="doc-section-rule"></div>'
                f'  <h2 class="doc-section-title">{title_text}</h2>'
                f'  {body_html}'
                '</section>'
            )

        for title, content in populated_content:
            sections_html += _section(
                escape(title),
                f'<p class="doc-prose">{escape(content)}</p>',
            )

        # Pricing section — standard heading + pricing block + optional notes
        pricing_free_text = proposal.pricing_section
        if pricing_block_html or pricing_free_text:
            title_text = "Engagement & Fees" if is_subscription_pricing else "Fees"
            body = pricing_block_html
            if pricing_free_text:
                body += f'<p class="doc-prose">{escape(pricing_free_text)}</p>'
            sections_html += _section(escape(title_text), body)

        # Fallback `content` block if nothing structured was filled in
        if (
            proposal.content
            and not populated_content
            and not pricing_block_html
            and not pricing_free_text
        ):
            sections_html += _section(
                "Proposal",
                f'<p class="doc-prose">{escape(proposal.content)}</p>',
            )

        # ---------- Cover letter (under the title block) ----------
        cover_letter_html = ""
        if proposal.cover_letter:
            cover_letter_html = (
                '<section class="doc-cover-letter">'
                f'<p>{escape(proposal.cover_letter)}</p>'
                '</section>'
            )

        # ---------- Signatory section ----------
        signatory_html = ""
        if include_signature and proposal.signed_at:
            signed_display = proposal.signed_at.strftime("%B %d, %Y · %H:%M UTC")
            ua = proposal.signer_user_agent or ""
            if len(ua) > 90:
                ua = ua[:87] + "..."

            rows = [
                ("Signatory", proposal.signer_name or ""),
                ("Email", proposal.signer_email or ""),
                ("Signed at", signed_display),
            ]
            if proposal.signer_ip:
                rows.append(("IP address", proposal.signer_ip))
            if ua:
                rows.append(("User-agent", ua))

            rows_html = "".join(
                f'<tr><th>{escape(label)}</th><td class="tabular">{escape(val)}</td></tr>'
                for label, val in rows
            )

            signatory_html = f"""
<section class="doc-signatory page-break-before">
  <div class="doc-section-rule"></div>
  <h2 class="doc-section-title">Signatory</h2>
  <p class="doc-prose">
    This proposal was accepted and electronically signed under the US ESIGN Act
    (15 USC §7001) and applicable state UETA statutes. The signature below
    carries the same legal effect as a handwritten signature.
  </p>
  <table class="doc-signatory-table">
    <tbody>{rows_html}</tbody>
  </table>
  <div class="doc-signature-line"></div>
  <p class="doc-signature-caption">Signed electronically for {escape(proposal.signer_name or "")}</p>
</section>
"""

        # ---------- Assemble ----------
        title_html = escape(proposal.title)
        proposal_number_html = escape(proposal.proposal_number)
        contact_block = (
            f'<p class="cover-prepared-for">Prepared for <strong>{escape(contact_name)}</strong>'
            + (f' &middot; <span class="cover-company">{escape(secondary_company)}</span>' if secondary_company else '')
            + '</p>'
            if contact_name else ""
        )
        footer_block = (
            f'<footer class="doc-footer"><p>{escape(footer_text)}</p></footer>'
            if footer_text else ""
        )

        html = f"""\
<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<style>
  @page {{
    size: Letter;
    margin: 20mm 20mm 20mm 20mm;
  }}
  * {{ box-sizing: border-box; }}
  html {{ font-size: 11pt; }}
  body {{
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    color: #111827;
    line-height: 1.6;
    margin: 0;
    padding: 0;
  }}
  .tabular {{ font-variant-numeric: tabular-nums; }}

  /* ---------- Letterhead ---------- */
  .letterhead {{
    width: 100%;
    border-bottom: 0.75pt solid #e5e7eb;
    margin-bottom: 24pt;
    padding-bottom: 10pt;
  }}
  .letterhead td {{ vertical-align: middle; }}
  .letterhead td.right {{ text-align: right; }}
  .letterhead-logo {{ height: 22pt; width: auto; max-width: 140pt; }}
  .letterhead-initial {{
    display: inline-block;
    width: 20pt; height: 20pt; line-height: 20pt;
    text-align: center;
    background: {accent};
    color: #ffffff;
    font-size: 10pt;
    font-weight: 600;
    margin-right: 8pt;
    vertical-align: middle;
  }}
  .letterhead-company {{
    font-size: 11pt;
    font-weight: 600;
    color: #111827;
    vertical-align: middle;
  }}
  .letterhead-meta {{
    font-size: 9pt;
    color: #6b7280;
  }}

  /* ---------- Cover title block (left-aligned, business-document) ---------- */
  .cover {{
    padding: 0 0 20pt;
    border-bottom: 0.5pt solid #e5e7eb;
    margin-bottom: 24pt;
  }}
  .cover-eyebrow {{
    font-size: 8.5pt;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #6b7280;
    margin: 0 0 8pt;
  }}
  .cover-title {{
    font-weight: 600;
    font-size: 24pt;
    line-height: 1.2;
    letter-spacing: -0.01em;
    color: #0f172a;
    margin: 0 0 10pt;
    max-width: 32em;
  }}
  .cover-prepared-for {{
    font-size: 11pt;
    color: #374151;
    margin: 0 0 4pt;
  }}
  .cover-prepared-for strong {{ font-weight: 600; color: #111827; }}
  .cover-company {{ color: #6b7280; }}
  .cover-validity {{
    font-size: 9pt;
    color: #6b7280;
    margin: 8pt 0 0;
  }}

  /* ---------- Cover letter ---------- */
  .doc-cover-letter {{
    font-size: 11pt;
    line-height: 1.7;
    color: #374151;
    margin: 0 0 24pt;
    max-width: 44em;
  }}
  .doc-cover-letter p {{ margin: 0; white-space: pre-wrap; }}

  /* ---------- Sections ---------- */
  .doc-section {{
    margin: 0 0 24pt;
    page-break-inside: avoid;
  }}
  .doc-section-rule {{
    width: 24pt;
    height: 1.5pt;
    background: {accent};
    margin-bottom: 8pt;
  }}
  .doc-section-title {{
    font-size: 14pt;
    font-weight: 600;
    letter-spacing: -0.01em;
    color: #111827;
    margin: 0 0 10pt;
    line-height: 1.3;
  }}
  .doc-prose {{
    font-size: 10.5pt;
    line-height: 1.7;
    color: #374151;
    margin: 0 0 10pt;
    white-space: pre-wrap;
    max-width: 44em;
  }}

  /* ---------- Pricing block (simple bordered table) ---------- */
  .pricing-block {{
    width: 100%;
    max-width: 40em;
    border: 0.75pt solid {accent}40;
    background: {accent}0a;
    margin: 8pt 0 14pt;
  }}
  .pricing-block td {{
    padding: 12pt 16pt;
    vertical-align: middle;
  }}
  .pricing-label {{
    font-size: 8.5pt;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #6b7280;
    margin-bottom: 4pt;
  }}
  .pricing-amount {{
    font-size: 22pt;
    font-weight: 600;
    color: #0f172a;
    letter-spacing: -0.01em;
    line-height: 1.1;
  }}
  .pricing-cadence {{
    text-align: right;
    font-size: 10pt;
    color: #4b5563;
  }}

  /* ---------- Signatory section ---------- */
  .page-break-before {{ page-break-before: always; }}
  .doc-signatory-table {{
    width: 100%;
    max-width: 44em;
    border-collapse: collapse;
    margin: 14pt 0 18pt;
  }}
  .doc-signatory-table th,
  .doc-signatory-table td {{
    text-align: left;
    padding: 7pt 0;
    border-bottom: 0.5pt solid #e5e7eb;
    vertical-align: top;
  }}
  .doc-signatory-table th {{
    font-size: 9pt;
    color: #6b7280;
    font-weight: 500;
    width: 28%;
  }}
  .doc-signatory-table td {{
    font-size: 10pt;
    color: #111827;
    word-break: break-word;
  }}
  .doc-signature-line {{
    width: 50%;
    height: 0.75pt;
    background: #d1d5db;
    margin: 24pt 0 6pt;
  }}
  .doc-signature-caption {{
    font-size: 9pt;
    color: #6b7280;
    margin: 0;
  }}

  .doc-footer {{
    margin-top: 32pt;
    padding-top: 12pt;
    border-top: 0.5pt solid #e5e7eb;
    font-size: 8.5pt;
    color: #9ca3af;
    line-height: 1.5;
  }}
</style>
</head>
<body>
  <table class="letterhead" cellpadding="0" cellspacing="0"><tr>
    <td>{logo_html}{letterhead_company_html}</td>
    <td class="right letterhead-meta tabular">{proposal_number_html}</td>
  </tr></table>

  <section class="cover">
    <p class="cover-eyebrow">Proposal &middot; <span class="tabular">{proposal_number_html}</span></p>
    <h1 class="cover-title">{title_html}</h1>
    {contact_block}
    {valid_html}
  </section>

  {cover_letter_html}
  {sections_html}
  {signatory_html}

  {footer_block}
</body></html>"""

        # Shared renderer enforces the SSRF allowlist on every resource
        # weasyprint tries to load (logo, font, CSS) so a tenant cannot
        # point the renderer at internal IPs or ``file://`` paths.
        return await render_html_to_pdf(html)

    async def send_signed_copy_to_client(self, proposal: Proposal) -> None:
        """Email the client a PDF of the accepted proposal with their e-signature.

        Sent via ``EmailService.queue_email(sent_by_id=proposal.owner_id)`` so
        it routes through the proposal owner's Gmail OAuth connection when
        they have one — otherwise falls back to the tenant's default email
        sender. Failure is logged but does not unwind acceptance.
        """
        if not proposal.signed_at:
            return
        signer_email = (proposal.signer_email or "").strip()
        if not signer_email:
            logger.warning(
                "Cannot send signed copy for proposal %s: no signer email",
                proposal.id,
            )
            return

        branding = await self.get_branding_for_proposal(proposal)
        company = branding.get("company_name") or "Your provider"
        signer_name = escape(proposal.signer_name or "")
        title = escape(proposal.title)
        body = (
            f"<p>Hi {signer_name or 'there'},</p>"
            f"<p>Thank you for accepting <strong>{title}</strong>. A signed "
            f"PDF copy is attached for your records.</p>"
            f"<p>{escape(company)}</p>"
        )

        # Render + queue are both best-effort: a failure in either leaves
        # the proposal accepted but without a signed-copy email. The CRM
        # user can resend from the admin UI.
        try:
            pdf_bytes = await self.generate_proposal_pdf(
                proposal.id,
                proposal.owner_id or 0,
                include_signature=True,
            )
            email_service = EmailService(self.db)
            await email_service.queue_email(
                to_email=signer_email,
                subject=f"Signed copy — {proposal.title}",
                body=body,
                sent_by_id=proposal.owner_id,
                entity_type="proposals",
                entity_id=proposal.id,
                attachments=[EmailAttachment(
                    filename=f"proposal-{proposal.proposal_number}-signed.pdf",
                    content=pdf_bytes,
                    content_type="application/pdf",
                )],
            )
        except Exception as exc:
            # exc_info=True forces a full traceback into the log
            # stream. Without it we burned a cycle in 2026-04-24 with a
            # silent signed-copy failure that looked identical between
            # "pod rolled mid-accept" and "PDF template tripped
            # weasyprint" — the traceback is what separates them.
            logger.warning(
                "Failed to send signed copy for proposal %s: %s",
                proposal.id, exc,
                exc_info=True,
            )

    async def get_branding_for_proposal(self, proposal: Proposal) -> dict:
        """Get tenant branding from the proposal owner's tenant."""
        if proposal.owner_id:
            return await TenantBrandingHelper.get_branding_for_user(self.db, proposal.owner_id)
        return TenantBrandingHelper.get_default_branding()

    async def substitute_template_variables(
        self, template_content: str, variables: dict
    ) -> str:
        """Replace {{variable}} placeholders in template content.

        Single-pass substitution so a value that itself contains ``{{x}}``
        is not re-expanded. Missing keys are left as-is; present-but-falsy
        values (None, empty string) substitute to an empty string.
        """
        def _replacer(match: "re.Match[str]") -> str:
            key = match.group(1)
            if key not in variables:
                return match.group(0)
            value = variables[key]
            return str(value) if value else ""

        return _TEMPLATE_VAR_PATTERN.sub(_replacer, template_content)


class ProposalTemplateService(BaseService[ProposalTemplate]):
    """Service for ProposalTemplate read operations. Create/update live in the router."""

    model = ProposalTemplate

    async def get_list(
        self,
        category: str | None = None,
    ) -> list[ProposalTemplate]:
        """Get all templates, optionally filtered by category."""
        query = select(ProposalTemplate)
        if category:
            query = query.where(ProposalTemplate.category == category)
        query = query.order_by(ProposalTemplate.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())
