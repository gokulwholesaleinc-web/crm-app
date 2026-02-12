"""Branded email template engine with tenant-aware branding.

Provides reusable HTML email templates that pull colors, logos, and
company info from TenantSettings so every outbound email matches the
tenant's brand.
"""

from html import escape
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.whitelabel.models import Tenant, TenantSettings, TenantUser


# ---------------------------------------------------------------------------
# Default branding (used when no tenant is configured)
# ---------------------------------------------------------------------------

_DEFAULT_BRANDING = {
    "company_name": "CRM",
    "logo_url": "",
    "primary_color": "#6366f1",
    "secondary_color": "#8b5cf6",
    "accent_color": "#22c55e",
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
        result = await db.execute(
            select(TenantUser)
            .where(TenantUser.user_id == user_id, TenantUser.is_primary == True)
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
    cta_text: Optional[str] = None,
    cta_url: Optional[str] = None,
) -> str:
    """Render content into a branded, responsive HTML email wrapper.

    Uses inline CSS for maximum email-client compatibility (Gmail,
    Outlook, Apple Mail).  Includes dark-mode media query support.
    """
    primary = escape(branding.get("primary_color", "#6366f1"))
    secondary = escape(branding.get("secondary_color", "#8b5cf6"))
    accent = escape(branding.get("accent_color", "#22c55e"))
    company = escape(branding.get("company_name", "CRM"))
    logo_url = branding.get("logo_url", "")
    footer_text = escape(branding.get("footer_text", ""))
    privacy_url = escape(branding.get("privacy_policy_url", ""))
    terms_url = escape(branding.get("terms_of_service_url", ""))

    # Logo block
    if logo_url:
        logo_html = (
            f'<img src="{escape(logo_url)}" alt="{company}" '
            f'width="40" height="40" '
            f'style="display:inline-block;vertical-align:middle;margin-right:12px;'
            f'border-radius:6px;" />'
        )
    else:
        logo_html = ""

    # CTA button
    if cta_text and cta_url:
        cta_html = (
            f'<table role="presentation" cellpadding="0" cellspacing="0" '
            f'style="margin:24px auto 0;">'
            f'<tr><td style="background-color:{accent};border-radius:6px;'
            f'text-align:center;">'
            f'<a href="{escape(cta_url)}" target="_blank" '
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
            f'<a href="{privacy_url}" style="color:#9ca3af;text-decoration:underline;">'
            f'Privacy Policy</a>'
        )
    if terms_url:
        footer_links_parts.append(
            f'<a href="{terms_url}" style="color:#9ca3af;text-decoration:underline;">'
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
<body style="margin:0;padding:0;background-color:#f3f4f6;font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" class="email-bg" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f3f4f6;">
<tr><td align="center" style="padding:24px 16px;">

<!-- Header -->
<table role="presentation" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;">
<tr><td style="background-color:{primary};padding:20px 24px;border-radius:8px 8px 0 0;">
  <table role="presentation" cellpadding="0" cellspacing="0" width="100%"><tr>
    <td style="color:#ffffff;font-family:Arial,Helvetica,sans-serif;font-size:18px;font-weight:700;">
      {logo_html}{company}
    </td>
  </tr></table>
</td></tr>
</table>

<!-- Body -->
<table role="presentation" class="email-card" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;background-color:#ffffff;">
<tr><td style="padding:32px 24px;">
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
    cta_text: Optional[str] = None,
    cta_url: Optional[str] = None,
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

    Expected quote_data keys:
        quote_number, client_name, total, currency, valid_until,
        items (list of {description, quantity, unit_price, total}),
        view_url (optional)
    """
    company = escape(branding.get("company_name", "CRM"))
    number = escape(str(quote_data.get("quote_number", "")))
    client = escape(str(quote_data.get("client_name", "")))
    total = escape(str(quote_data.get("total", "0.00")))
    currency = escape(str(quote_data.get("currency", "USD")))
    valid_until = escape(str(quote_data.get("valid_until", "")))

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

    body_html = f"""\
<p>Dear {client},</p>
<p>Please find your quote <strong>#{number}</strong> below.</p>
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
    view_url = quote_data.get("view_url")
    html = render_branded_email(
        branding=branding,
        subject=subject,
        headline=f"Quote #{number}",
        body_html=body_html,
        cta_text="View Quote" if view_url else None,
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
    accent = escape(branding.get("accent_color", "#22c55e"))

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
# Campaign wrapper
# ---------------------------------------------------------------------------

def render_campaign_wrapper(
    branding: dict,
    campaign_body: str,
    unsubscribe_url: str,
) -> str:
    """Wraps campaign content in branded template with unsubscribe link."""
    unsub_html = (
        f'<p style="margin:16px 0 0;font-size:12px;color:#9ca3af;text-align:center;">'
        f'<a href="{escape(unsubscribe_url)}" style="color:#9ca3af;text-decoration:underline;">'
        f'Unsubscribe</a></p>'
    )
    body_with_unsub = campaign_body + unsub_html

    return _base_email_html(
        branding=branding,
        headline="",
        body_html=body_with_unsub,
    )
