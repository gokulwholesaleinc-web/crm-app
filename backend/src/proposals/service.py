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
        """Generate branded proposal PDF with all sections.

        When ``include_signature`` is True and the proposal has been
        signed, appends an e-signature audit block (signer name,
        email, IP, timestamp). Used for the post-acceptance "signed
        copy" that gets emailed to the client.
        """
        proposal = await self.get_by_id(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        branding = await TenantBrandingHelper.get_branding_for_user(self.db, user_id)

        company_name = escape(branding.get("company_name", "CRM"))
        primary_color = escape(branding.get("primary_color", "#6366f1"))
        secondary_color = escape(branding.get("secondary_color", "#8b5cf6"))
        # Pre-validate the logo URL: if it fails the SSRF check, omit the
        # <img> entirely rather than handing weasyprint a URL that it will
        # later refuse and log as an error per page render.
        logo_html = ""
        logo_url = branding.get("logo_url") or ""
        if logo_url:
            try:
                validate_public_url(
                    logo_url,
                    allowed_schemes=("https",),
                    allowed_hostnames=pdf_logo_allowed_hosts(),
                )
                logo_html = (
                    f'<img src="{escape(logo_url)}" alt="{company_name}" '
                    f'style="max-height:48px;margin-right:16px;" />'
                )
            except UnsafeUrlError as exc:
                logger.warning(
                    "Skipping proposal logo for tenant user %s: %s", user_id, exc
                )

        sections_html = ""
        section_data = [
            ("Cover Letter", proposal.cover_letter),
            ("Executive Summary", proposal.executive_summary),
            ("Scope of Work", proposal.scope_of_work),
            ("Pricing", proposal.pricing_section),
            ("Timeline", proposal.timeline),
            ("Terms and Conditions", proposal.terms),
        ]
        for title, content in section_data:
            if content:
                sections_html += (
                    f'<div style="margin-bottom:24px;">'
                    f'<h2 style="color:{primary_color};font-size:18px;margin-bottom:8px;">'
                    f'{escape(title)}</h2>'
                    f'<p style="white-space:pre-wrap;line-height:1.6;">{escape(content)}</p>'
                    f'</div>'
                )

        if proposal.content and not proposal.executive_summary and not proposal.scope_of_work:
            sections_html += (
                f'<div style="margin-bottom:24px;">'
                f'<p style="white-space:pre-wrap;line-height:1.6;">{escape(proposal.content)}</p>'
                f'</div>'
            )

        signature_html = ""
        if include_signature and proposal.signed_at:
            signed_on = proposal.signed_at.strftime("%B %d, %Y at %H:%M UTC")
            signer_row = (
                f'<p style="margin:4px 0;"><strong>Signed by:</strong> '
                f'{escape(proposal.signer_name or "")}</p>'
                f'<p style="margin:4px 0;"><strong>Email:</strong> '
                f'{escape(proposal.signer_email or "")}</p>'
                f'<p style="margin:4px 0;"><strong>Signed on:</strong> {signed_on}</p>'
            )
            if proposal.signer_ip:
                signer_row += (
                    f'<p style="margin:4px 0;color:#6b7280;font-size:11px;">'
                    f'IP: {escape(proposal.signer_ip)}</p>'
                )
            signature_html = (
                f'<div style="margin-top:32px;padding:16px 20px;'
                f'background-color:#f3f4f6;border-left:4px solid {primary_color};'
                f'border-radius:4px;">'
                f'<h2 style="color:{primary_color};font-size:16px;margin:0 0 8px;">'
                f'Electronic Signature</h2>'
                f'{signer_row}'
                f'</div>'
            )

        contact_name = ""
        if proposal.contact:
            contact_name = getattr(proposal.contact, "full_name", "") or ""

        valid_line = ""
        if proposal.valid_until:
            valid_line = (
                f'<p style="color:#6b7280;font-size:13px;">Valid until: '
                f'{proposal.valid_until.isoformat()}</p>'
            )

        html = f"""\
<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
body {{ font-family: Arial, Helvetica, sans-serif; margin: 0; padding: 0; color: #111827; }}
</style>
</head><body>
<div style="background-color:{primary_color};padding:24px 32px;color:#ffffff;">
  <div style="display:flex;align-items:center;">
    {logo_html}
    <span style="font-size:22px;font-weight:700;">{company_name}</span>
  </div>
</div>
<div style="padding:32px;">
  <h1 style="font-size:26px;margin-bottom:4px;">{escape(proposal.title)}</h1>
  <p style="color:#6b7280;margin-bottom:4px;">{escape(proposal.proposal_number)}</p>
  {"<p style='color:#6b7280;'>Prepared for " + escape(contact_name) + "</p>" if contact_name else ""}
  {valid_line}
  <hr style="border:none;border-top:2px solid {secondary_color};margin:24px 0;" />
  {sections_html}
  {signature_html}
</div>
<div style="background-color:#f9fafb;padding:16px 32px;text-align:center;font-size:12px;color:#6b7280;">
  {company_name}
</div>
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
            logger.warning(
                "Failed to send signed copy for proposal %s: %s",
                proposal.id, exc,
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
