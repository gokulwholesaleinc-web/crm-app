"""Proposal service layer."""

import logging
import os
import re
import secrets
from datetime import datetime, timezone
from html import escape
from typing import Optional, List, Tuple
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from src.proposals.models import Proposal, ProposalTemplate, ProposalView
from src.proposals.schemas import ProposalCreate, ProposalUpdate
from src.core.base_service import CRUDService, StatusTransitionMixin
from src.core.constants import DEFAULT_PAGE_SIZE
from src.core.filtering import build_token_search
from src.core.url_safety import UnsafeUrlError, validate_public_url
from src.email.branded_templates import TenantBrandingHelper, render_proposal_email
from src.email.service import EmailService

logger = logging.getLogger(__name__)

_TEMPLATE_VAR_PATTERN = re.compile(r"\{\{(\w+)\}\}")


def _proposal_logo_allowed_hosts() -> Optional[List[str]]:
    """Return the optional allowlist of hostnames permitted for logo fetches.

    Read from ``PROPOSAL_LOGO_ALLOWED_HOSTS`` (comma-separated). When unset,
    :func:`validate_public_url` falls back to ``https`` + non-private-IP
    enforcement, which is the minimum safe baseline. Operators that know
    their tenant assets live on a single CDN can tighten this further via
    env var without a code change.
    """
    raw = os.getenv("PROPOSAL_LOGO_ALLOWED_HOSTS", "").strip()
    if not raw:
        return None
    return [h.strip().lower() for h in raw.split(",") if h.strip()]


def _safe_pdf_url_fetcher(url: str):
    """weasyprint url_fetcher that blocks SSRF attempts.

    weasyprint will fetch any URL you hand it — including ``file://`` for
    local disk reads and private-IP HTTP for internal metadata endpoints.
    This wrapper gates every outbound fetch through the shared SSRF
    validator before delegating to weasyprint's default fetcher.
    """
    try:
        validate_public_url(
            url,
            allowed_schemes=("https",),
            allowed_hostnames=_proposal_logo_allowed_hosts(),
        )
    except UnsafeUrlError as exc:
        logger.warning("Rejected unsafe PDF resource URL: %s", exc)
        raise
    from weasyprint import default_url_fetcher
    return default_url_fetcher(url)


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
        year = datetime.now(timezone.utc).year
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
        search: Optional[str] = None,
        status: Optional[str] = None,
        contact_id: Optional[int] = None,
        company_id: Optional[int] = None,
        opportunity_id: Optional[int] = None,
        owner_id: Optional[int] = None,
        shared_entity_ids: Optional[List[int]] = None,
    ) -> Tuple[List[Proposal], int]:
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
        total = total_result.scalar()

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

        proposal = Proposal(**proposal_data)
        self.db.add(proposal)
        await self.db.flush()
        await self.db.refresh(proposal)

        return proposal

    async def record_view(
        self, proposal_id: int, ip_address: Optional[str] = None, user_agent: Optional[str] = None
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

        now = datetime.now(timezone.utc)
        proposal.view_count = (proposal.view_count or 0) + 1
        proposal.last_viewed_at = now

        # Auto-transition from sent to viewed
        if proposal.status == "sent":
            proposal.status = "viewed"
            proposal.viewed_at = now

        await self.db.flush()
        await self.db.refresh(proposal)
        return proposal

    async def get_public_proposal(self, token: str) -> Optional[Proposal]:
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

        email_service = EmailService(self.db)
        await email_service.queue_email(
            to_email=contact.email,
            subject=subject,
            body=html_body,
            sent_by_id=user_id,
            entity_type="proposals",
            entity_id=proposal.id,
        )

        # Mark proposal as sent
        if proposal.status == "draft":
            proposal.status = "sent"
            proposal.sent_at = datetime.now(timezone.utc)
            await self.db.flush()
            await self.db.refresh(proposal)

    async def generate_proposal_pdf(self, proposal_id: int, user_id: int) -> bytes:
        """Generate branded proposal PDF with all sections."""
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
                    allowed_hostnames=_proposal_logo_allowed_hosts(),
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
</div>
<div style="background-color:#f9fafb;padding:16px 32px;text-align:center;font-size:12px;color:#6b7280;">
  {company_name}
</div>
</body></html>"""

        # Convert HTML to PDF bytes. The custom url_fetcher enforces the
        # SSRF allowlist on every resource weasyprint tries to load (logo,
        # font, CSS) so a tenant cannot point the renderer at internal IPs
        # or ``file://`` paths.
        try:
            import weasyprint
            pdf_bytes = weasyprint.HTML(
                string=html,
                url_fetcher=_safe_pdf_url_fetcher,
            ).write_pdf()
        except ImportError:
            # Fallback: return HTML as bytes if weasyprint is not available
            pdf_bytes = html.encode("utf-8")

        return pdf_bytes

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


class ProposalTemplateService(CRUDService[ProposalTemplate, None, None]):
    """Service for ProposalTemplate CRUD operations."""

    model = ProposalTemplate
    create_exclude_fields = set()
    update_exclude_fields = set()

    async def get_list(
        self,
        category: Optional[str] = None,
    ) -> List[ProposalTemplate]:
        """Get all templates, optionally filtered by category."""
        query = select(ProposalTemplate)
        if category:
            query = query.where(ProposalTemplate.category == category)
        query = query.order_by(ProposalTemplate.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())
