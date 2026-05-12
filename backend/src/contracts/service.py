"""Contract service layer."""

import logging
import secrets
from datetime import UTC, datetime, timedelta
from html import escape

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import selectinload

from src.attachments.object_storage import upload_file_bytes
from src.config import settings
from src.contracts.models import Contract
from src.contracts.schemas import ContractCreate, ContractUpdate
from src.core.base_service import CRUDService
from src.core.constants import DEFAULT_PAGE_SIZE
from src.core.filtering import build_token_search
from src.core.sorting import build_order_clauses
from src.core.url_safety import UnsafeUrlError, validate_public_url
from src.email.branded_templates import TenantBrandingHelper, render_contract_send_email
from src.email.pdf_render import pdf_logo_allowed_hosts, render_html_to_pdf
from src.email.service import EmailService
from src.email.types import EmailAttachment

logger = logging.getLogger(__name__)

ENTITY_TYPE_CONTRACTS = "contracts"

# Mirrors proposals: signing links are valid for 7 days from send.
SIGN_TOKEN_TTL = timedelta(days=7)

CONTRACT_SORTABLE_FIELDS = {
    "title": Contract.title,
    "status": Contract.status,
    "value": Contract.value,
    "end_date": Contract.end_date,
    "created_at": Contract.created_at,
}


class ContractService(CRUDService[Contract, ContractCreate, ContractUpdate]):
    """Service for Contract CRUD operations."""

    model = Contract
    entity_type = ENTITY_TYPE_CONTRACTS
    create_exclude_fields: set = set()
    update_exclude_fields: set = set()

    def _get_eager_load_options(self):
        return [
            selectinload(Contract.contact),
            selectinload(Contract.company),
        ]

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        contact_id: int | None = None,
        company_id: int | None = None,
        status: str | None = None,
        owner_id: int | None = None,
        shared_entity_ids: list[int] | None = None,
        search: str | None = None,
        order_by: str | None = None,
        order_dir: str | None = None,
    ) -> tuple[list[Contract], int]:
        """Get paginated list of contracts with filters."""
        query = select(Contract).options(
            selectinload(Contract.contact),
            selectinload(Contract.company),
        )

        if contact_id:
            query = query.where(Contract.contact_id == contact_id)

        if company_id:
            query = query.where(Contract.company_id == company_id)

        if status:
            query = query.where(Contract.status == status)

        if owner_id or shared_entity_ids:
            clauses = []
            if owner_id:
                clauses.append(Contract.owner_id == owner_id)
            if shared_entity_ids:
                clauses.append(Contract.id.in_(shared_entity_ids))
            query = query.where(or_(*clauses))

        if search:
            condition = build_token_search(search, Contract.title)
            if condition is not None:
                query = query.where(condition)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        order_clauses = build_order_clauses(
            CONTRACT_SORTABLE_FIELDS,
            order_by,
            order_dir,
            default=[Contract.created_at.desc(), Contract.id.desc()],
        )
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(*order_clauses)

        result = await self.db.execute(query)
        contracts = list(result.scalars().all())

        return contracts, total

    async def get_by_token(self, token: str) -> Contract | None:
        """Resolve a contract by its public sign token.

        Used by the public view + sign endpoints. Returns None when the
        token is missing, malformed, or no contract carries it.
        """
        if not token or len(token) < 16:
            return None
        result = await self.db.execute(
            select(Contract)
            .options(selectinload(Contract.contact), selectinload(Contract.company))
            .where(Contract.sign_token == token),
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _mint_token() -> str:
        """Mint an unguessable URL-safe token for the public sign link."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def _token_expiry() -> datetime:
        return datetime.now(UTC) + SIGN_TOKEN_TTL

    # ---------- E-sign workflow ----------

    async def send_for_signature(
        self,
        contract: Contract,
        user_id: int,
        to_email: str | None = None,
        message: str | None = None,
    ) -> Contract:
        """Mint a sign token, mark sent_at, and email the signer.

        Acquires a row-level lock before any state mutation. Two concurrent
        send requests on the same contract row serialize on the lock, so
        the second request's email is queued *after* the first commits its
        token — only the latest token is live, but at least no email goes
        out mid-flush with a token the row no longer holds. (Mirrors the
        ``SELECT … FOR UPDATE`` pattern in
        ``proposals/service.resend_payment_link``.)
        """
        recipient = to_email or (contract.contact.email if contract.contact else None)
        if not recipient:
            raise ValueError("No recipient email — provide to_email or link a contact with an email address")

        # Lock the contract row for the rest of the transaction. Postgres
        # serializes; SQLite (test) treats it as a no-op which is fine
        # because tests are single-threaded.
        locked = await self.db.execute(
            select(Contract).where(Contract.id == contract.id).with_for_update(),
        )
        contract = locked.scalar_one()

        if contract.status not in ("draft", "sent"):
            raise ValueError(
                f"Cannot send contract in '{contract.status}' status for signature"
            )

        # Re-mint each send so an old forwarded link from a previous
        # send-cycle stops working.
        contract.sign_token = self._mint_token()
        contract.sign_token_expires_at = self._token_expiry()
        contract.sent_at = datetime.now(UTC)
        contract.status = "sent"
        await self.db.flush()
        await self.db.refresh(contract)

        owner_id = contract.owner_id or user_id
        base_url = settings.FRONTEND_BASE_URL or "http://localhost:3000"
        sign_url = f"{base_url}/contracts/sign/{contract.sign_token}"

        branding = await TenantBrandingHelper.get_branding_for_user(self.db, owner_id)
        client_first_name = (
            contract.contact.first_name if contract.contact else ""
        )
        subject, body = render_contract_send_email(
            branding=branding,
            contract_title=contract.title,
            client_first_name=client_first_name,
            sign_url=sign_url,
            message=message,
        )

        # `queue_email` catches transport failures internally and returns
        # the queue row reflecting what happened. Inspect status — if it's
        # not `sent` (delivered now) or `throttled` (will go out later),
        # revert the contract so the operator can fix Gmail / mistyped
        # recipient and resend without a stale `sent_at`.
        email_service = EmailService(self.db)
        try:
            email = await email_service.queue_email(
                to_email=recipient,
                subject=subject,
                body=body,
                sent_by_id=owner_id,
                entity_type=ENTITY_TYPE_CONTRACTS,
                entity_id=contract.id,
            )
        except Exception as exc:
            logger.exception(
                "Failed to construct send email for contract %s",
                contract.id,
            )
            raise ValueError(f"Could not queue contract email: {exc}") from exc

        # Only revert on a terminal "failed" status. "retry" means the
        # send is in the queue and the retry worker will pick it up;
        # "throttled" means it'll go out at the next throttle window.
        # The EmailQueue UI surfaces both for operator visibility, and
        # we log retry status loud here so a stuck-in-retry contract is
        # greppable without trawling the queue table.
        if email.status == "retry":
            logger.warning(
                "Contract %s email %s in retry (attempts=%d, error=%r) — "
                "monitor email queue, may need manual resend",
                contract.id, email.id, email.retry_count, email.error,
            )

        if email.status == "failed":
            contract.sign_token = None
            contract.sign_token_expires_at = None
            contract.sent_at = None
            contract.status = "draft"
            await self.db.flush()
            await self.db.refresh(contract)
            detail = email.error or "email send failed"
            raise ValueError(
                f"Could not send signature email — {detail}. "
                "Connect Gmail in Settings or retry."
            )

        return contract

    async def get_public_view(self, contract: Contract) -> dict:
        """Return the signer-facing projection of a contract."""
        company_name = contract.company.name if contract.company else None
        contact_name = contract.contact.full_name if contract.contact else None
        signer_email = contract.contact.email.lower() if contract.contact and contract.contact.email else None

        # `get_branding_for_user` already returns default branding when
        # the tenant row is missing; bare-except here would hide bugs.
        owner_id = contract.owner_id or 0
        branding = await TenantBrandingHelper.get_branding_for_user(self.db, owner_id)

        return {
            "id": contract.id,
            "title": contract.title,
            "scope": contract.scope,
            "value": contract.value,
            "currency": contract.currency,
            "start_date": contract.start_date,
            "end_date": contract.end_date,
            "status": contract.status,
            "company_name": company_name,
            "contact_name": contact_name,
            "signer_email": signer_email,
            "expires_at": contract.sign_token_expires_at,
            "signed_at": contract.signed_at,
            "signed_by_name": contract.signed_by_name,
            "branding": branding,
        }

    async def sign_contract(
        self,
        contract: Contract,
        signer_name: str,
        signer_email: str,
        signature_data_url: str,
        signer_ip: str | None = None,
        signer_user_agent: str | None = None,
    ) -> Contract:
        """Persist signature, generate signed PDF, email signer a copy."""
        if contract.status != "sent":
            raise ValueError(
                f"Cannot sign contract in '{contract.status}' status"
            )

        now = datetime.now(UTC)
        expires = contract.sign_token_expires_at
        if not expires:
            raise ValueError("Sign link has expired")
        # SQLite returns naive datetimes; coerce to UTC for comparison.
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires < now:
            raise ValueError("Sign link has expired")

        # Email check: if a contact with email is linked, the signer must match.
        if contract.contact and contract.contact.email:
            if signer_email.lower() != contract.contact.email.lower():
                raise ValueError(
                    "Signer email does not match the expected contact email"
                )

        # Atomic transition: guarded by status == "sent" so concurrent
        # sign requests can't both succeed.
        stmt = (
            update(Contract)
            .where(Contract.id == contract.id)
            .where(Contract.status == "sent")
            .values(
                status="signed",
                signed_at=now,
                signed_by_name=signer_name,
                signed_signature_b64=signature_data_url,
                signer_email=signer_email,
                signer_ip=signer_ip,
                signer_user_agent=signer_user_agent,
                sign_token=None,
                sign_token_expires_at=None,
            )
        )
        result = await self.db.execute(stmt)
        if result.rowcount == 0:
            raise ValueError("Contract was signed by another signer moments ago")

        await self.db.flush()
        await self.db.refresh(contract)

        # Render signed PDF and upload to R2. The customer's signature is
        # already persisted and the status flipped — a render failure here
        # does NOT unwind signing, but logger.exception ensures the
        # traceback is loud so the operator can re-render later.
        try:
            pdf_bytes = await self._generate_contract_pdf(contract, include_signature=True)
            timestamp = int(now.timestamp())
            r2_key = f"contracts/{contract.id}/signed-{timestamp}.pdf"
            await upload_file_bytes(pdf_bytes, r2_key, content_type="application/pdf")
            contract.signed_pdf_r2_key = r2_key
            await self.db.flush()
            await self.db.refresh(contract)
        except Exception:
            logger.exception(
                "Failed to render/upload signed PDF for contract %s",
                contract.id,
            )

        # Email signed copy to signer — failure doesn't unwind signing.
        try:
            await self._send_signed_copy(contract, signer_email)
        except Exception:
            logger.exception(
                "Failed to send signed copy for contract %s",
                contract.id,
            )

        # Owner-side notification (matrix-gated) — skip when no owner.
        if contract.owner_id:
            from src.notifications.service import notify_on_contract_signed

            try:
                await notify_on_contract_signed(
                    db=self.db,
                    owner_id=contract.owner_id,
                    contract_id=contract.id,
                    contract_title=contract.title,
                    signer_name=contract.signed_by_name,
                    signed_at=contract.signed_at.strftime("%B %d, %Y · %H:%M UTC") if contract.signed_at else None,
                )
            except Exception:
                logger.exception("contract_signed notify failed for contract %s", contract.id)

        return contract

    async def _generate_contract_pdf(
        self,
        contract: Contract,
        include_signature: bool = False,
    ) -> bytes:
        """Generate a branded contract PDF mirroring the proposal PDF aesthetic."""
        owner_id = contract.owner_id or 0
        branding = await TenantBrandingHelper.get_branding_for_user(self.db, owner_id)

        company_name_raw = branding.get("company_name") or "CRM"
        company_name = escape(company_name_raw)
        accent = escape(branding.get("primary_color") or "#6366f1")
        footer_text = branding.get("footer_text") or ""

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
                logger.warning("Skipping contract logo for tenant user %s: %s", owner_id, exc)

        if not logo_html:
            initial = escape((company_name_raw or "C")[0].upper())
            logo_html = f'<span class="letterhead-initial">{initial}</span>'

        letterhead_company_html = (
            "" if logo_is_image else f'<span class="letterhead-company">{company_name}</span>'
        )

        contact_name = ""
        if contract.contact:
            contact_name = getattr(contract.contact, "full_name", "") or ""

        secondary_company = ""
        if contract.company and getattr(contract.company, "name", None):
            _cname = contract.company.name
            if _cname and _cname != company_name_raw:
                secondary_company = _cname

        contact_block = (
            f'<p class="cover-prepared-for">Prepared for <strong>{escape(contact_name)}</strong>'
            + (f' &middot; <span class="cover-company">{escape(secondary_company)}</span>' if secondary_company else "")
            + "</p>"
            if contact_name else ""
        )

        # Value / dates block
        meta_rows = []
        if contract.value is not None:
            symbol = {"USD": "$", "EUR": "€", "GBP": "£", "CAD": "$", "AUD": "$"}.get(
                (contract.currency or "USD").upper(), ""
            )
            formatted = f"{symbol}{contract.value:,.2f}" if symbol else f"{contract.currency} {contract.value:,.2f}"
            meta_rows.append(("Contract value", formatted))
        if contract.start_date:
            meta_rows.append(("Start date", contract.start_date.strftime("%B %d, %Y")))
        if contract.end_date:
            meta_rows.append(("End date", contract.end_date.strftime("%B %d, %Y")))

        meta_html = ""
        if meta_rows:
            rows_html = "".join(
                f'<tr><th>{escape(label)}</th><td class="tabular">{escape(val)}</td></tr>'
                for label, val in meta_rows
            )
            meta_html = f'<table class="doc-meta-table"><tbody>{rows_html}</tbody></table>'

        scope_html = ""
        if contract.scope:
            scope_html = (
                '<section class="doc-section">'
                '<div class="doc-section-rule"></div>'
                '<h2 class="doc-section-title">Scope</h2>'
                f'<p class="doc-prose">{escape(contract.scope)}</p>'
                '</section>'
            )

        signatory_html = ""
        if include_signature and contract.signed_at:
            signed_display = contract.signed_at.strftime("%B %d, %Y · %H:%M UTC")
            ua = contract.signer_user_agent or ""
            if len(ua) > 90:
                ua = ua[:87] + "..."

            rows = [
                ("Signatory", contract.signed_by_name or ""),
                ("Signed at", signed_display),
            ]
            if contract.signer_email:
                rows.append(("Email", contract.signer_email))
            if contract.signer_ip:
                rows.append(("IP address", contract.signer_ip))
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
    This contract was electronically signed under the US ESIGN Act
    (15 USC §7001) and applicable state UETA statutes. The signature below
    carries the same legal effect as a handwritten signature.
  </p>
  <table class="doc-signatory-table">
    <tbody>{rows_html}</tbody>
  </table>
  <div class="doc-signature-line"></div>
  <p class="doc-signature-caption">Signed electronically for {escape(contract.signed_by_name or "")}</p>
</section>
"""

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
  .letterhead-meta {{ font-size: 9pt; color: #6b7280; }}
  .cover {{
    padding: 0 0 20pt;
    border-bottom: 0.5pt solid #e5e7eb;
    margin-bottom: 24pt;
  }}
  .cover-eyebrow {{ font-size: 9pt; color: #6b7280; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 10pt; }}
  .cover-title {{ font-size: 20pt; font-weight: 700; color: #111827; margin: 0 0 10pt; line-height: 1.25; }}
  .cover-prepared-for {{ font-size: 10pt; color: #374151; margin: 0 0 4pt; }}
  .cover-company {{ color: #6b7280; }}
  .doc-meta-table {{ width: 100%; margin: 12pt 0 0; border-collapse: collapse; font-size: 10pt; }}
  .doc-meta-table th {{ text-align: left; color: #6b7280; font-weight: 500; padding: 3pt 12pt 3pt 0; width: 30%; }}
  .doc-meta-table td {{ color: #111827; padding: 3pt 0; }}
  .doc-section {{ margin-top: 24pt; }}
  .doc-section-rule {{ height: 1.5pt; width: 20pt; background: {accent}; margin-bottom: 8pt; }}
  .doc-section-title {{ font-size: 13pt; font-weight: 600; color: #111827; margin: 0 0 10pt; }}
  .doc-prose {{ font-size: 10.5pt; line-height: 1.65; color: #374151; white-space: pre-wrap; margin: 0; max-width: 72ch; }}
  .doc-signatory {{ margin-top: 32pt; }}
  .doc-signatory-table {{ width: 100%; border-collapse: collapse; font-size: 9.5pt; margin: 12pt 0; }}
  .doc-signatory-table th {{ text-align: left; color: #6b7280; font-weight: 500; padding: 4pt 12pt 4pt 0; width: 28%; }}
  .doc-signatory-table td {{ color: #111827; padding: 4pt 0; }}
  .doc-signature-line {{ border-top: 0.75pt solid #6b7280; width: 160pt; margin-top: 24pt; }}
  .doc-signature-caption {{ font-size: 8.5pt; color: #6b7280; margin-top: 4pt; }}
  .doc-footer {{ margin-top: 32pt; padding-top: 10pt; border-top: 0.5pt solid #e5e7eb; font-size: 8.5pt; color: #9ca3af; }}
  .page-break-before {{ page-break-before: always; }}
</style>
</head>
<body>

<table class="letterhead" cellpadding="0" cellspacing="0"><tr>
  <td>{logo_html}{letterhead_company_html}</td>
  <td class="right letterhead-meta">Contract</td>
</tr></table>

<div class="cover">
  <p class="cover-eyebrow">Contract</p>
  <h1 class="cover-title">{escape(contract.title)}</h1>
  {contact_block}
  {meta_html}
</div>

{scope_html}
{signatory_html}

{footer_block}
</body></html>"""

        return await render_html_to_pdf(html)

    async def _send_signed_copy(self, contract: Contract, signer_email: str) -> None:
        """Email the signer a PDF copy of the signed contract."""
        if not contract.signed_at or not signer_email:
            return

        owner_id = contract.owner_id or 0
        branding = await TenantBrandingHelper.get_branding_for_user(self.db, owner_id)

        # Render first so the body text can honestly reflect whether a
        # PDF will be attached. Otherwise the signer reads "PDF
        # attached" and finds nothing.
        attachments: list[EmailAttachment] = []
        try:
            pdf_bytes = await self._generate_contract_pdf(contract, include_signature=True)
            attachments = [EmailAttachment(
                filename=f"contract-{contract.id}-signed.pdf",
                content=pdf_bytes,
                content_type="application/pdf",
            )]
        except Exception:
            logger.exception(
                "PDF render failed for signed contract %s",
                contract.id,
            )

        from src.email.branded_templates import render_contract_signed_email

        subject, body = render_contract_signed_email(branding, {
            "audience": "signer",
            "contract_title": contract.title,
            "signer_name": contract.signed_by_name,
            # Render the "PDF will follow" copy when the PDF render
            # failed; the unattached "PDF copy is attached" line
            # otherwise lies to the signer.
            "pdf_pending": not attachments,
        })

        email_service = EmailService(self.db)
        await email_service.queue_email(
            to_email=signer_email,
            subject=subject,
            body=body,
            sent_by_id=owner_id,
            entity_type=ENTITY_TYPE_CONTRACTS,
            entity_id=contract.id,
            attachments=attachments or None,
        )
