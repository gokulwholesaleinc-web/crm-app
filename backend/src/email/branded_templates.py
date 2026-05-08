"""Branded email template engine with tenant-aware branding.

Provides reusable HTML email templates that pull colors, logos, and
company info from TenantSettings so every outbound email matches the
tenant's brand.
"""

import logging
import re
from html import escape

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.whitelabel.models import Tenant, TenantSettings, TenantUser

logger = logging.getLogger(__name__)

# Schemes allowed in outbound email links. ``html.escape`` does not block
# ``javascript:``/``data:`` URLs inside ``href``/``src`` attributes, so every
# externally-sourced URL that lands in an email must also pass this filter.
_SAFE_URL_SCHEMES = ("https://", "http://", "mailto:")

# Mirrors the ``_HEX_COLOR_RE`` in ``whitelabel/schemas.py`` and the
# frontend ``HEX_COLOR_RE`` in ``utils/colorValidation.ts``. Three- and
# six-digit hex only — eight-digit is rejected because the underlying
# ``tenant_settings`` columns are ``VARCHAR(7)``.
_HEX_COLOR_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def _safe_hex(value: str | None, fallback: str, *, field: str = "color") -> str:
    """Return ``value`` if it's a valid hex color, else ``fallback``.

    Defensive second layer for the email/PDF render path. ``TenantSettings``
    has a Pydantic ``_validate_color_field`` that rejects bad hex on PATCH
    (PR #263 trio fix), but ``TenantBrandingHelper.get_branding_for_user``
    reads straight from the ORM — it can't catch a row that pre-dates the
    validator, was inserted via raw SQL, or made it through a buggy
    migration. Without this guard, a malformed value flows verbatim into
    a ``style="background-color:zzz;"`` declaration that email clients
    silently drop, and the customer sees an unbranded rendering with no
    log entry to diagnose from.

    Logs at WARNING when fallback fires so Sentry can surface corrupt
    rows; otherwise this would replace one silent failure with another.
    """
    if isinstance(value, str) and _HEX_COLOR_RE.match(value.strip()):
        return value.strip()
    if value not in (None, ""):
        logger.warning(
            "branding %s fell back to %s (invalid hex: %r)", field, fallback, value
        )
    return fallback


def _safe_url(url: str | None) -> str:
    """Return ``url`` if it uses an allowlisted scheme, else an empty string.

    Defensive second layer: values in :class:`TenantSettings` should already
    be validated at write time (see ``whitelabel/schemas.py``), but rendering
    should never emit an ``href``/``src`` with a ``javascript:``/``data:``
    scheme even if historical rows or a schema bypass slipped such a value
    into the database. Site-relative paths (``/foo``) are also allowed so
    in-app links like campaign unsubscribe URLs keep working.
    """
    stripped = (url or "").strip()
    if not stripped:
        return ""
    # Site-relative paths are safe — there is no scheme to abuse.
    if stripped.startswith("/") and not stripped.startswith("//"):
        return stripped
    if stripped.lower().startswith(_SAFE_URL_SCHEMES):
        return stripped
    return ""


# ---------------------------------------------------------------------------
# Default branding (used when no tenant is configured)
# ---------------------------------------------------------------------------

_DEFAULT_BRANDING = {
    "company_name": "CRM",
    "logo_url": "",
    "primary_color": "#6366f1",
    "secondary_color": "#8b5cf6",
    "accent_color": "#22c55e",
    # Page + surface backgrounds (light mode only on customer-facing
    # surfaces — public quote/contract/proposal pages and emails
    # render light by default; the app's dark mode is for authenticated
    # sellers and lives on its own CSS-var path). Defaults match the
    # `tenant_settings` column defaults.
    "bg_color_light": "#f9fafb",
    "surface_color_light": "#ffffff",
    "footer_text": "",
    "privacy_policy_url": "",
    "terms_of_service_url": "",
    "email_from_name": "CRM",
    "email_from_address": "",
}


# ---------------------------------------------------------------------------
# Branding helper
# ---------------------------------------------------------------------------

class TenantBrandingHelper:
    """Fetches and provides tenant branding for templates."""

    @staticmethod
    async def get_branding_for_user(db: AsyncSession, user_id: int) -> dict:
        """Get branding dict from user's primary tenant.

        Queries TenantUser -> Tenant -> TenantSettings and returns a flat
        dictionary of branding values.  Falls back to defaults when no
        tenant or settings are found.
        """
        # Prefer the primary TenantUser row, but fall back to any tenant
        # the user belongs to. `is_primary` defaults to False at the DB
        # level, so users created through paths that don't flag primary
        # explicitly (e.g. older seeds, some invite flows) would otherwise
        # hit the default "CRM" branding even when their tenant settings
        # are fully configured.
        result = await db.execute(
            select(TenantUser)
            .where(TenantUser.user_id == user_id)
            .order_by(TenantUser.is_primary.desc(), TenantUser.id.asc())
            .limit(1)
        )
        tenant_user = result.scalar_one_or_none()
        if not tenant_user:
            return TenantBrandingHelper.get_default_branding()

        result = await db.execute(
            select(Tenant)
            .where(Tenant.id == tenant_user.tenant_id)
            .options(selectinload(Tenant.settings))
        )
        tenant = result.scalar_one_or_none()
        if not tenant or not tenant.settings:
            return TenantBrandingHelper.get_default_branding()

        s: TenantSettings = tenant.settings
        return {
            "company_name": s.company_name or tenant.name,
            "logo_url": s.logo_url or "",
            "primary_color": s.primary_color or _DEFAULT_BRANDING["primary_color"],
            "secondary_color": s.secondary_color or _DEFAULT_BRANDING["secondary_color"],
            "accent_color": s.accent_color or _DEFAULT_BRANDING["accent_color"],
            "bg_color_light": s.bg_color_light or _DEFAULT_BRANDING["bg_color_light"],
            "surface_color_light": s.surface_color_light or _DEFAULT_BRANDING["surface_color_light"],
            "footer_text": s.footer_text or "",
            "privacy_policy_url": s.privacy_policy_url or "",
            "terms_of_service_url": s.terms_of_service_url or "",
            "email_from_name": s.email_from_name or s.company_name or tenant.name,
            "email_from_address": s.email_from_address or "",
        }

    @staticmethod
    def get_default_branding() -> dict:
        """Default branding when no tenant is configured."""
        return dict(_DEFAULT_BRANDING)


# ---------------------------------------------------------------------------
# Base HTML email template
# ---------------------------------------------------------------------------

def _base_email_html(
    branding: dict,
    headline: str,
    body_html: str,
    cta_text: str | None = None,
    cta_url: str | None = None,
) -> str:
    """Render content into a branded, responsive HTML email wrapper.

    Uses inline CSS for maximum email-client compatibility (Gmail,
    Outlook, Apple Mail).  Includes dark-mode media query support.
    """
    # _safe_hex sanitizes each color before it reaches the inline-CSS
    # sinks below. ``escape`` is HTML-escaping, not hex validation; a
    # corrupt-row payload of "red" or "#zzz" would otherwise produce
    # ``background-color:red;`` (which clients quietly drop) and the
    # customer would see a white email with no diagnostic trace. See
    # _safe_hex docstring for why ORM-level reads bypass the schema
    # validator.
    primary = escape(_safe_hex(branding.get("primary_color"), "#6366f1", field="primary_color"))
    secondary = escape(_safe_hex(branding.get("secondary_color"), "#8b5cf6", field="secondary_color"))
    accent = escape(_safe_hex(branding.get("accent_color"), "#22c55e", field="accent_color"))
    # Light-mode page + card surface colors. The email's dark-mode media
    # query keeps its hardcoded #1f2937 / #111827 — those approximate
    # the tenant_settings dark defaults and refactoring them through
    # tenant settings risks regressions in finicky email clients
    # (Outlook desktop especially) for marginal gain.
    bg_light = escape(_safe_hex(branding.get("bg_color_light"), "#f9fafb", field="bg_color_light"))
    surface_light = escape(_safe_hex(branding.get("surface_color_light"), "#ffffff", field="surface_color_light"))
    company = escape(branding.get("company_name", "CRM"))
    logo_url = _safe_url(branding.get("logo_url", ""))
    footer_text = escape(branding.get("footer_text", ""))
    privacy_url = _safe_url(branding.get("privacy_policy_url", ""))
    terms_url = _safe_url(branding.get("terms_of_service_url", ""))
    safe_cta_url = _safe_url(cta_url)

    # Logo block — height-locked, width auto to preserve aspect ratio for
    # wordmark logos. max-width caps ultra-wide logos so the header row
    # doesn't wrap. Outlook reads the height attribute; the style block
    # covers Gmail/Apple Mail/web clients.
    #
    # When a logo image is present we assume it already contains the
    # company wordmark and suppress the text company name next to it —
    # otherwise you get "LINKCREATIVE  Link Creative" side-by-side.
    if logo_url:
        # White pill wraps the logo so it stays visible regardless of header
        # primary color (e.g. a white logo on a white header would disappear).
        logo_html = (
            f'<table role="presentation" cellpadding="0" cellspacing="0" '
            f'style="display:inline-table;vertical-align:middle;margin-right:12px;">'
            f'<tr><td style="background-color:#ffffff;border-radius:6px;padding:8px 12px;">'
            f'<img src="{escape(logo_url)}" alt="{company}" '
            f'height="40" '
            f'style="display:block;height:40px;width:auto;max-width:200px;" />'
            f'</td></tr></table>'
        )
        company_label = ""
    else:
        logo_html = ""
        company_label = company

    # CTA button — only render if the URL passed the scheme allowlist.
    if cta_text and safe_cta_url:
        cta_html = (
            f'<table role="presentation" cellpadding="0" cellspacing="0" '
            f'style="margin:24px auto 0;">'
            f'<tr><td style="background-color:{accent};border-radius:6px;'
            f'text-align:center;">'
            f'<a href="{escape(safe_cta_url)}" target="_blank" '
            f'style="display:inline-block;padding:12px 28px;color:#ffffff;'
            f'font-family:Arial,Helvetica,sans-serif;font-size:15px;'
            f'font-weight:600;text-decoration:none;">{escape(cta_text)}</a>'
            f'</td></tr></table>'
        )
    else:
        cta_html = ""

    # Footer links
    footer_links_parts = []
    if privacy_url:
        footer_links_parts.append(
            f'<a href="{escape(privacy_url)}" style="color:#9ca3af;text-decoration:underline;">'
            f'Privacy Policy</a>'
        )
    if terms_url:
        footer_links_parts.append(
            f'<a href="{escape(terms_url)}" style="color:#9ca3af;text-decoration:underline;">'
            f'Terms of Service</a>'
        )
    footer_links = " &middot; ".join(footer_links_parts)

    footer_text_block = (
        f'<p style="margin:0 0 8px;color:#9ca3af;font-size:12px;">{footer_text}</p>'
        if footer_text
        else ""
    )

    return f"""\
<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="color-scheme" content="light dark"/>
<meta name="supported-color-schemes" content="light dark"/>
<title>{escape(headline)}</title>
<!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
<style>
@media (prefers-color-scheme:dark){{
  .email-bg{{background-color:#1f2937!important;}}
  .email-card{{background-color:#111827!important;}}
  .email-text{{color:#e5e7eb!important;}}
  .email-headline{{color:#f9fafb!important;}}
  .email-footer{{background-color:#111827!important;}}
}}
</style>
</head>
<body style="margin:0;padding:0;background-color:{bg_light};font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" class="email-bg" cellpadding="0" cellspacing="0" width="100%" style="background-color:{bg_light};">
<tr><td align="center" style="padding:24px 16px;">

<!-- Header -->
<table role="presentation" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;">
<tr><td style="background-color:{primary};padding:24px 32px;border-radius:8px 8px 0 0;">
  <table role="presentation" cellpadding="0" cellspacing="0" width="100%"><tr>
    <td style="color:#ffffff;font-family:Arial,Helvetica,sans-serif;font-size:18px;font-weight:700;">
      {logo_html}{company_label}
    </td>
  </tr></table>
</td></tr>
<tr><td style="height:3px;line-height:3px;font-size:0;background-color:{secondary};">&nbsp;</td></tr>
</table>

<!-- Body -->
<table role="presentation" class="email-card" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;background-color:{surface_light};">
<tr><td style="padding:32px 32px;">
  <h1 class="email-headline" style="margin:0 0 16px;font-family:Arial,Helvetica,sans-serif;font-size:22px;font-weight:700;color:#111827;">{escape(headline)}</h1>
  <div class="email-text" style="font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.6;color:#374151;">
    {body_html}
  </div>
  {cta_html}
</td></tr>
</table>

<!-- Footer -->
<table role="presentation" class="email-footer" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;background-color:#f9fafb;">
<tr><td style="padding:20px 24px;border-radius:0 0 8px 8px;text-align:center;font-family:Arial,Helvetica,sans-serif;">
  <p style="margin:0 0 4px;color:#6b7280;font-size:13px;font-weight:600;">{company}</p>
  {footer_text_block}
  <p style="margin:0;font-size:12px;">{footer_links}</p>
</td></tr>
</table>

</td></tr>
</table>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Public render function
# ---------------------------------------------------------------------------

def render_branded_email(
    branding: dict,
    subject: str,
    headline: str,
    body_html: str,
    cta_text: str | None = None,
    cta_url: str | None = None,
) -> str:
    """Render any content into the branded email wrapper."""
    return _base_email_html(
        branding=branding,
        headline=headline,
        body_html=body_html,
        cta_text=cta_text,
        cta_url=cta_url,
    )


# ---------------------------------------------------------------------------
# Quote email
# ---------------------------------------------------------------------------

def render_quote_email(branding: dict, quote_data: dict) -> tuple[str, str]:
    """Returns (subject, html_body) for quote emails.

    When ``view_url`` is provided the email directs the recipient to
    review and accept/reject the quote via a branded public link
    (e-sign flow).  The line-items summary is included as a preview.

    Expected quote_data keys:
        quote_number, client_name, total, currency, valid_until,
        items (list of {description, quantity, unit_price, total}),
        view_url (optional - public quote link for e-sign)
    """
    company = escape(branding.get("company_name", "CRM"))
    number = escape(str(quote_data.get("quote_number", "")))
    client = escape(str(quote_data.get("client_name", "")))
    total = escape(str(quote_data.get("total", "0.00")))
    currency = escape(str(quote_data.get("currency", "USD")))
    valid_until = escape(str(quote_data.get("valid_until", "")))
    view_url = quote_data.get("view_url")

    # Build items table rows
    items = quote_data.get("items", [])
    rows_html = ""
    for item in items:
        rows_html += (
            f'<tr>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:14px;">'
            f'{escape(str(item.get("description", "")))}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:14px;text-align:center;">'
            f'{escape(str(item.get("quantity", "")))}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:14px;text-align:right;">'
            f'{currency} {escape(str(item.get("unit_price", "")))}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:14px;text-align:right;">'
            f'{currency} {escape(str(item.get("total", "")))}</td>'
            f'</tr>'
        )

    # Intro copy changes depending on whether this is an e-sign flow
    if view_url:
        intro = (
            f'<p>Dear {client},</p>'
            f'<p>{company} has sent you quote <strong>#{number}</strong> for your review. '
            f'Please click the button below to view the full details, and accept or decline the quote.</p>'
        )
    else:
        intro = (
            f'<p>Dear {client},</p>'
            f'<p>Please find your quote <strong>#{number}</strong> below.</p>'
        )

    body_html = f"""\
{intro}
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="border:1px solid #e5e7eb;border-radius:6px;margin:16px 0;">
<thead>
<tr style="background-color:#f9fafb;">
  <th style="padding:10px 12px;text-align:left;font-size:13px;font-weight:600;color:#6b7280;">Description</th>
  <th style="padding:10px 12px;text-align:center;font-size:13px;font-weight:600;color:#6b7280;">Qty</th>
  <th style="padding:10px 12px;text-align:right;font-size:13px;font-weight:600;color:#6b7280;">Unit Price</th>
  <th style="padding:10px 12px;text-align:right;font-size:13px;font-weight:600;color:#6b7280;">Total</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
<tfoot>
<tr>
  <td colspan="3" style="padding:10px 12px;text-align:right;font-weight:700;font-size:15px;">Total:</td>
  <td style="padding:10px 12px;text-align:right;font-weight:700;font-size:15px;">{currency} {total}</td>
</tr>
</tfoot>
</table>
<p style="color:#6b7280;font-size:13px;">Valid until: {valid_until}</p>"""

    subject = f"Quote #{number} from {company}"
    html = render_branded_email(
        branding=branding,
        subject=subject,
        headline=f"Quote #{number}",
        body_html=body_html,
        cta_text="Review & Accept Quote" if view_url else None,
        cta_url=view_url,
    )
    return subject, html


# ---------------------------------------------------------------------------
# Proposal email
# ---------------------------------------------------------------------------

def render_proposal_email(branding: dict, proposal_data: dict) -> tuple[str, str]:
    """Returns (subject, html_body) for proposal emails.

    Expected proposal_data keys:
        proposal_title, client_name, summary, total, currency, view_url (optional)
    """
    company = escape(branding.get("company_name", "CRM"))
    title = escape(str(proposal_data.get("proposal_title", "Proposal")))
    client = escape(str(proposal_data.get("client_name", "")))
    summary = escape(str(proposal_data.get("summary", "")))
    total = escape(str(proposal_data.get("total", "")))
    currency = escape(str(proposal_data.get("currency", "USD")))

    body_html = f"""\
<p>Dear {client},</p>
<p>We are pleased to present our proposal: <strong>{title}</strong>.</p>
<div style="background-color:#f9fafb;border-radius:6px;padding:16px;margin:16px 0;">
  <p style="margin:0 0 8px;font-size:14px;color:#6b7280;">Summary</p>
  <p style="margin:0;font-size:15px;">{summary}</p>
</div>
<p style="font-size:16px;font-weight:700;">Proposed investment: {currency} {total}</p>
<p>We look forward to discussing this with you.</p>"""

    subject = f"Proposal: {title} from {company}"
    view_url = proposal_data.get("view_url")
    html = render_branded_email(
        branding=branding,
        subject=subject,
        headline=title,
        body_html=body_html,
        cta_text="View Proposal" if view_url else None,
        cta_url=view_url,
    )
    return subject, html


# ---------------------------------------------------------------------------
# Payment receipt email
# ---------------------------------------------------------------------------

def render_payment_receipt_email(branding: dict, payment_data: dict) -> tuple[str, str]:
    """Returns (subject, html_body) for payment receipts.

    Expected payment_data keys:
        receipt_number, client_name, amount, currency, payment_date,
        payment_method, items (list of {description, amount})
    """
    company = escape(branding.get("company_name", "CRM"))
    receipt_no = escape(str(payment_data.get("receipt_number", "")))
    client = escape(str(payment_data.get("client_name", "")))
    amount = escape(str(payment_data.get("amount", "0.00")))
    currency = escape(str(payment_data.get("currency", "USD")))
    pay_date = escape(str(payment_data.get("payment_date", "")))
    pay_method = escape(str(payment_data.get("payment_method", "")))
    accent = escape(_safe_hex(branding.get("accent_color"), "#22c55e", field="accent_color"))

    items = payment_data.get("items", [])
    items_html = ""
    for item in items:
        items_html += (
            f'<tr>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:14px;">'
            f'{escape(str(item.get("description", "")))}</td>'
            f'<td style="padding:8px 12px;border-bottom:1px solid #e5e7eb;font-size:14px;text-align:right;">'
            f'{currency} {escape(str(item.get("amount", "")))}</td>'
            f'</tr>'
        )

    body_html = f"""\
<p>Dear {client},</p>
<p>Thank you for your payment. Here is your receipt.</p>
<div style="background-color:#f0fdf4;border-left:4px solid {accent};border-radius:4px;padding:16px;margin:16px 0;">
  <p style="margin:0;font-size:13px;color:#6b7280;">Amount paid</p>
  <p style="margin:4px 0 0;font-size:24px;font-weight:700;color:#111827;">{currency} {amount}</p>
</div>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin:16px 0;font-size:14px;">
<tr><td style="padding:4px 0;color:#6b7280;">Receipt #</td><td style="padding:4px 0;text-align:right;">{receipt_no}</td></tr>
<tr><td style="padding:4px 0;color:#6b7280;">Date</td><td style="padding:4px 0;text-align:right;">{pay_date}</td></tr>
<tr><td style="padding:4px 0;color:#6b7280;">Payment method</td><td style="padding:4px 0;text-align:right;">{pay_method}</td></tr>
</table>"""

    if items_html:
        body_html += f"""\
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="border:1px solid #e5e7eb;border-radius:6px;margin:16px 0;">
<thead>
<tr style="background-color:#f9fafb;">
  <th style="padding:10px 12px;text-align:left;font-size:13px;font-weight:600;color:#6b7280;">Description</th>
  <th style="padding:10px 12px;text-align:right;font-size:13px;font-weight:600;color:#6b7280;">Amount</th>
</tr>
</thead>
<tbody>
{items_html}
</tbody>
</table>"""

    subject = f"Payment Receipt #{receipt_no} from {company}"
    html = render_branded_email(
        branding=branding,
        subject=subject,
        headline=f"Payment Receipt #{receipt_no}",
        body_html=body_html,
    )
    return subject, html


# ---------------------------------------------------------------------------
# Payment invoice email (re-send)
# ---------------------------------------------------------------------------

def render_payment_invoice_email(branding: dict, payment_data: dict) -> tuple[str, str]:
    """Returns (subject, html_body) for an invoice resend.

    Used when staff click "Resend Invoice" because the customer reports
    not receiving the original. Body references the attached PDF and
    repeats the headline numbers so the email is useful even before the
    attachment is opened.

    Expected payment_data keys: invoice_number, client_name, amount,
    currency, due_date (optional), payment_url (optional).
    """
    company = escape(branding.get("company_name", "CRM"))
    invoice_no = escape(str(payment_data.get("invoice_number", "")))
    client = escape(str(payment_data.get("client_name", "")))
    amount = escape(str(payment_data.get("amount", "0.00")))
    currency = escape(str(payment_data.get("currency", "USD")))
    due_date = escape(str(payment_data.get("due_date", "")))
    accent = escape(_safe_hex(branding.get("accent_color"), "#22c55e", field="accent_color"))
    pay_url = _safe_url(payment_data.get("payment_url", ""))

    pay_button = ""
    if pay_url:
        pay_button = (
            f'<p style="margin:24px 0;text-align:center;">'
            f'<a href="{escape(pay_url)}" '
            f'style="background-color:{accent};color:#ffffff;text-decoration:none;'
            f'padding:12px 24px;border-radius:6px;font-weight:600;display:inline-block;">'
            f'Pay invoice</a></p>'
        )

    body_html = f"""\
<p>Dear {client},</p>
<p>Please find your invoice attached. The headline details are repeated below for your records.</p>
<div style="background-color:#f9fafb;border-left:4px solid {accent};border-radius:4px;padding:16px;margin:16px 0;">
  <p style="margin:0;font-size:13px;color:#6b7280;">Amount due</p>
  <p style="margin:4px 0 0;font-size:24px;font-weight:700;color:#111827;">{currency} {amount}</p>
</div>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin:16px 0;font-size:14px;">
<tr><td style="padding:4px 0;color:#6b7280;">Invoice #</td><td style="padding:4px 0;text-align:right;">{invoice_no}</td></tr>"""

    if due_date:
        body_html += (
            f'<tr><td style="padding:4px 0;color:#6b7280;">Due date</td>'
            f'<td style="padding:4px 0;text-align:right;">{due_date}</td></tr>'
        )

    body_html += "</table>" + pay_button
    body_html += (
        '<p style="font-size:13px;color:#6b7280;">If you have any questions, '
        'just reply to this email.</p>'
    )

    subject = f"Invoice #{invoice_no} from {company}"
    html = render_branded_email(
        branding=branding,
        subject=subject,
        headline=f"Invoice #{invoice_no}",
        body_html=body_html,
    )
    return subject, html


# ---------------------------------------------------------------------------
# Notification matrix templates
# ---------------------------------------------------------------------------
#
# These mirror the user-facing event keys exposed in the Settings →
# Notifications matrix (see ``frontend/src/api/account.ts``
# ``NOTIFICATION_EVENT_TYPES``). Each renderer returns ``(subject,
# html_body)`` so the dispatcher can pass both straight through to
# ``EmailService.queue_email``.

_TRUNCATE_SNIPPET_CHARS = 280


def _truncate(text: str, limit: int) -> str:
    """Trim ``text`` to ``limit`` chars with a trailing ellipsis when cut."""
    s = (text or "").strip()
    if len(s) <= limit:
        return s
    # Use the typographic ellipsis per CLAUDE.md.
    return s[: limit - 1].rstrip() + "…"


def render_lead_assigned_email(
    branding: dict, data: dict
) -> tuple[str, str]:
    """Returns (subject, html_body) for a "lead assigned to you" email.

    Expected ``data`` keys: ``lead_full_name``, ``lead_email`` (optional),
    ``lead_company_name`` (optional), ``lead_url`` (deep link), and
    ``assigner_name`` (optional). The assigner falls back to the
    branding company name when not provided.
    """
    lead_name = escape(str(data.get("lead_full_name") or "a new lead"))
    lead_email = escape(str(data.get("lead_email") or ""))
    lead_company = escape(str(data.get("lead_company_name") or ""))
    assigner = escape(str(
        data.get("assigner_name") or branding.get("company_name") or "CRM"
    ))
    lead_url = data.get("lead_url")

    rows = [f'<tr><td style="padding:4px 0;color:#6b7280;width:120px;">Lead</td>'
            f'<td style="padding:4px 0;font-weight:600;color:#111827;">{lead_name}</td></tr>']
    if lead_company:
        rows.append(
            f'<tr><td style="padding:4px 0;color:#6b7280;">Company</td>'
            f'<td style="padding:4px 0;color:#111827;">{lead_company}</td></tr>'
        )
    if lead_email:
        rows.append(
            f'<tr><td style="padding:4px 0;color:#6b7280;">Email</td>'
            f'<td style="padding:4px 0;color:#111827;">{lead_email}</td></tr>'
        )

    body_html = f"""\
<p>{assigner} has assigned a new lead to you.</p>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f9fafb;border-radius:6px;padding:16px;margin:16px 0;font-size:14px;">
<tbody>
{''.join(rows)}
</tbody>
</table>
<p style="color:#6b7280;font-size:13px;">Open the lead to add an activity, qualify it, or hand it off.</p>"""

    subject = f"New lead assigned: {data.get('lead_full_name') or 'unnamed lead'}"
    html = render_branded_email(
        branding=branding,
        subject=subject,
        headline="New lead assigned to you",
        body_html=body_html,
        cta_text="Open lead" if lead_url else None,
        cta_url=lead_url,
    )
    return subject, html


def render_task_due_email(branding: dict, data: dict) -> tuple[str, str]:
    """Returns (subject, html_body) for a "task due soon" email.

    Expected ``data`` keys: ``activity_subject``, ``activity_due_at``
    (preformatted string), ``activity_url`` (deep link), ``entity_label``
    (optional — e.g. "Acme Inc · John Doe").
    """
    activity_subject = escape(str(data.get("activity_subject") or "Untitled task"))
    due_at = escape(str(data.get("activity_due_at") or ""))
    entity_label = escape(str(data.get("entity_label") or ""))
    activity_url = data.get("activity_url")

    rows = [f'<tr><td style="padding:4px 0;color:#6b7280;width:120px;">Task</td>'
            f'<td style="padding:4px 0;font-weight:600;color:#111827;">{activity_subject}</td></tr>']
    if due_at:
        rows.append(
            f'<tr><td style="padding:4px 0;color:#6b7280;">Due</td>'
            f'<td style="padding:4px 0;color:#111827;">{due_at}</td></tr>'
        )
    if entity_label:
        rows.append(
            f'<tr><td style="padding:4px 0;color:#6b7280;">Linked to</td>'
            f'<td style="padding:4px 0;color:#111827;">{entity_label}</td></tr>'
        )

    body_html = f"""\
<p>You have a task coming due in your CRM.</p>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f9fafb;border-radius:6px;padding:16px;margin:16px 0;font-size:14px;">
<tbody>
{''.join(rows)}
</tbody>
</table>"""

    subject = f"Task due — {data.get('activity_subject') or 'Untitled task'}"
    html = render_branded_email(
        branding=branding,
        subject=subject,
        headline="Task due soon",
        body_html=body_html,
        cta_text="Open task" if activity_url else None,
        cta_url=activity_url,
    )
    return subject, html


def render_mention_email(branding: dict, data: dict) -> tuple[str, str]:
    """Returns (subject, html_body) for an "@mention" email.

    Expected ``data`` keys: ``author_name``, ``entity_label`` (e.g. the
    contact / lead / opportunity title), ``entity_url`` (deep link), and
    ``content_snippet`` (the comment body — truncated to 280 chars before
    rendering so a long thread doesn't blow out the email layout).
    """
    author = escape(str(data.get("author_name") or "Someone"))
    entity_label = escape(str(data.get("entity_label") or "an item"))
    entity_url = data.get("entity_url")
    snippet_raw = _truncate(str(data.get("content_snippet") or ""), _TRUNCATE_SNIPPET_CHARS)
    snippet = escape(snippet_raw) if snippet_raw else ""

    snippet_block = (
        f'<blockquote style="margin:16px 0;padding:12px 16px;border-left:3px solid '
        f'{escape(_safe_hex(branding.get("primary_color"), "#6366f1", field="primary_color"))};background-color:#f9fafb;'
        f'font-size:14px;color:#374151;white-space:pre-wrap;">{snippet}</blockquote>'
        if snippet else ""
    )

    body_html = f"""\
<p><strong>{author}</strong> mentioned you on <strong>{entity_label}</strong>.</p>
{snippet_block}"""

    subject = f"{data.get('author_name') or 'Someone'} mentioned you on {data.get('entity_label') or 'an item'}"
    html = render_branded_email(
        branding=branding,
        subject=subject,
        headline=f"{data.get('author_name') or 'Someone'} mentioned you",
        body_html=body_html,
        cta_text="View thread" if entity_url else None,
        cta_url=entity_url,
    )
    return subject, html


def render_email_reply_email(branding: dict, data: dict) -> tuple[str, str]:
    """Returns (subject, html_body) for an "inbound email reply" notification.

    Expected ``data`` keys: ``sender_email``, ``sender_name`` (optional),
    ``subject_line`` (the inbound message's subject), ``snippet`` (body
    preview — truncated to 280 chars), and ``thread_url`` (deep link to
    the CRM thread view).
    """
    sender_email = escape(str(data.get("sender_email") or ""))
    sender_name = escape(str(data.get("sender_name") or "")) or sender_email or "A contact"
    raw_subject = str(data.get("subject_line") or "(no subject)")
    subject_line = escape(raw_subject)
    snippet_raw = _truncate(str(data.get("snippet") or ""), _TRUNCATE_SNIPPET_CHARS)
    snippet = escape(snippet_raw) if snippet_raw else ""
    thread_url = data.get("thread_url")

    sender_block = (
        f'<p style="margin:0 0 12px;color:#374151;">'
        f'<strong>{sender_name}</strong>'
        + (f' &lt;{sender_email}&gt;' if sender_email and sender_name != sender_email else '')
        + '</p>'
    )
    snippet_block = (
        f'<blockquote style="margin:0;padding:12px 16px;border-left:3px solid '
        f'{escape(_safe_hex(branding.get("primary_color"), "#6366f1", field="primary_color"))};background-color:#f9fafb;'
        f'font-size:14px;color:#374151;white-space:pre-wrap;">{snippet}</blockquote>'
        if snippet else ""
    )

    body_html = f"""\
<p>You have a new email reply on a thread you own.</p>
{sender_block}
<p style="margin:0 0 16px;font-size:15px;color:#374151;"><strong style="color:#6b7280;">Subject:</strong> <span style="font-weight:600;color:#111827;">{subject_line}</span></p>
{snippet_block}"""

    subject = f"Reply received — {raw_subject}"
    html = render_branded_email(
        branding=branding,
        subject=subject,
        headline="Email reply received",
        body_html=body_html,
        cta_text="Open thread" if thread_url else None,
        cta_url=thread_url,
    )
    return subject, html


def render_contract_expiring_email(
    branding: dict, data: dict
) -> tuple[str, str]:
    """Returns (subject, html_body) for the daily "contract expiring" alert.

    Expected ``data`` keys: ``contract_title``, ``company_name``
    (optional), ``end_date`` (preformatted string), ``days_left`` (int),
    ``contract_url`` (deep link).
    """
    title = escape(str(data.get("contract_title") or "Contract"))
    company = escape(str(data.get("company_name") or ""))
    end_date = escape(str(data.get("end_date") or ""))
    days_left = int(data.get("days_left") or 0)
    contract_url = data.get("contract_url")

    plural = "" if days_left == 1 else "s"
    rows = [f'<tr><td style="padding:4px 0;color:#6b7280;width:120px;">Contract</td>'
            f'<td style="padding:4px 0;font-weight:600;color:#111827;">{title}</td></tr>']
    if company:
        rows.append(
            f'<tr><td style="padding:4px 0;color:#6b7280;">Company</td>'
            f'<td style="padding:4px 0;color:#111827;">{company}</td></tr>'
        )
    if end_date:
        rows.append(
            f'<tr><td style="padding:4px 0;color:#6b7280;">Expires</td>'
            f'<td style="padding:4px 0;color:#111827;">{end_date}</td></tr>'
        )

    body_html = f"""\
<p>The contract below expires in <strong>{days_left} day{plural}</strong>. Renewal usually takes a few business days — start the conversation now to avoid a service gap.</p>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f9fafb;border-radius:6px;padding:16px;margin:16px 0;font-size:14px;">
<tbody>
{''.join(rows)}
</tbody>
</table>"""

    subject = f"Contract expiring in {days_left} day{plural} — {data.get('contract_title') or 'Contract'}"
    html = render_branded_email(
        branding=branding,
        subject=subject,
        headline=f"Contract expiring in {days_left} day{plural}",
        body_html=body_html,
        cta_text="Open contract" if contract_url else None,
        cta_url=contract_url,
    )
    return subject, html


def render_contract_signed_email(
    branding: dict, data: dict
) -> tuple[str, str]:
    """Returns (subject, html_body) for the "contract signed" notification.

    Used for **two distinct flows**:
      1. signer-side transactional copy — caller supplies ``audience='signer'``,
         ``signer_name``. Always-on, never matrix-gated.
      2. owner-side notification — caller supplies ``audience='owner'``,
         ``signer_name``, ``signed_at``, ``contract_url``. Matrix-gated on
         ``contract_signed``.

    Expected ``data`` keys: ``audience`` ('signer' | 'owner'),
    ``contract_title``, ``signer_name``, ``signed_at`` (preformatted str,
    optional), ``contract_url`` (optional — owner only).
    """
    title = escape(str(data.get("contract_title") or "Contract"))
    signer_name = escape(str(data.get("signer_name") or ""))
    signed_at = escape(str(data.get("signed_at") or ""))
    contract_url = data.get("contract_url")
    audience = (data.get("audience") or "owner").lower()
    company = escape(branding.get("company_name", "CRM"))

    if audience == "signer":
        # Distinct copy when the PDF couldn't be rendered — saying
        # "attached for your records" while attaching nothing is
        # actively misleading.
        if data.get("pdf_pending"):
            body_html = f"""\
<p>Hi {signer_name or 'there'},</p>
<p>Thank you for signing <strong>{title}</strong>. Your signed PDF copy will be sent once it's ready — usually within a few minutes. Reply to this email if you don't see it shortly.</p>
<p>{company}</p>"""
        else:
            body_html = f"""\
<p>Hi {signer_name or 'there'},</p>
<p>Thank you for signing <strong>{title}</strong>. A signed PDF copy is attached for your records.</p>
<p>{company}</p>"""
        subject = f"Signed copy — {data.get('contract_title') or 'Contract'}"
        headline = "Thank you for signing"
        cta_text = None
        cta_url = None
    else:
        rows = [f'<tr><td style="padding:4px 0;color:#6b7280;width:120px;">Contract</td>'
                f'<td style="padding:4px 0;font-weight:600;color:#111827;">{title}</td></tr>']
        if signer_name:
            rows.append(
                f'<tr><td style="padding:4px 0;color:#6b7280;">Signed by</td>'
                f'<td style="padding:4px 0;color:#111827;">{signer_name}</td></tr>'
            )
        if signed_at:
            rows.append(
                f'<tr><td style="padding:4px 0;color:#6b7280;">Signed at</td>'
                f'<td style="padding:4px 0;color:#111827;">{signed_at}</td></tr>'
            )
        body_html = f"""\
<p>Your contract has been electronically signed.</p>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f9fafb;border-radius:6px;padding:16px;margin:16px 0;font-size:14px;">
<tbody>
{''.join(rows)}
</tbody>
</table>"""
        subject = f"Contract signed — {data.get('contract_title') or 'Contract'}"
        headline = "Contract signed"
        cta_text = "Open contract" if contract_url else None
        cta_url = contract_url

    html = render_branded_email(
        branding=branding,
        subject=subject,
        headline=headline,
        body_html=body_html,
        cta_text=cta_text,
        cta_url=cta_url,
    )
    return subject, html


def render_proposal_signed_email(
    branding: dict, data: dict
) -> tuple[str, str]:
    """Returns (subject, html_body) for the OWNER-side "proposal signed" notification.

    Distinct from :func:`render_proposal_email` — that one is the
    send-for-signature email to the signer; this is the post-acceptance
    notification to the internal owner. Signer-side post-acceptance copy
    (with the signed PDF attached) stays in proposals/service.py and is
    not template-ified to keep the attachment-heavy logic local.

    Expected ``data`` keys: ``proposal_title``, ``signer_name`` (signer
    of the e-sign), ``signed_at`` (preformatted str, optional),
    ``proposal_url`` (deep link).
    """
    title = escape(str(data.get("proposal_title") or "Proposal"))
    signer_name = escape(str(data.get("signer_name") or ""))
    signed_at = escape(str(data.get("signed_at") or ""))
    proposal_url = data.get("proposal_url")

    rows = [f'<tr><td style="padding:4px 0;color:#6b7280;width:120px;">Proposal</td>'
            f'<td style="padding:4px 0;font-weight:600;color:#111827;">{title}</td></tr>']
    if signer_name:
        rows.append(
            f'<tr><td style="padding:4px 0;color:#6b7280;">Signed by</td>'
            f'<td style="padding:4px 0;color:#111827;">{signer_name}</td></tr>'
        )
    if signed_at:
        rows.append(
            f'<tr><td style="padding:4px 0;color:#6b7280;">Signed at</td>'
            f'<td style="padding:4px 0;color:#111827;">{signed_at}</td></tr>'
        )

    body_html = f"""\
<p>Your proposal has been accepted and electronically signed.</p>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f9fafb;border-radius:6px;padding:16px;margin:16px 0;font-size:14px;">
<tbody>
{''.join(rows)}
</tbody>
</table>
<p style="color:#6b7280;font-size:13px;">If billing is configured the next step (Stripe invoice or checkout) is automatically queued.</p>"""

    subject = f"Proposal signed — {data.get('proposal_title') or 'Proposal'}"
    html = render_branded_email(
        branding=branding,
        subject=subject,
        headline="Proposal signed",
        body_html=body_html,
        cta_text="Open proposal" if proposal_url else None,
        cta_url=proposal_url,
    )
    return subject, html


# ---------------------------------------------------------------------------
# Campaign wrapper
# ---------------------------------------------------------------------------

def render_campaign_wrapper(
    branding: dict,
    campaign_body: str,
    unsubscribe_url: str,
) -> str:
    """Wraps campaign content in branded template with unsubscribe link."""
    safe_unsub = _safe_url(unsubscribe_url)
    if safe_unsub:
        unsub_html = (
            f'<p style="margin:16px 0 0;font-size:12px;color:#9ca3af;text-align:center;">'
            f'<a href="{escape(safe_unsub)}" style="color:#9ca3af;text-decoration:underline;">'
            f'Unsubscribe</a></p>'
        )
    else:
        unsub_html = ""
    body_with_unsub = campaign_body + unsub_html

    return _base_email_html(
        branding=branding,
        headline="",
        body_html=body_with_unsub,
    )
