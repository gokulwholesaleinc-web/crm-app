"""Invoice PDF (HTML) rendering for payments."""

from html import escape

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.payments.models import Payment


async def generate_invoice_pdf(db: AsyncSession, payment_id: int) -> bytes:
    """Generate a branded invoice PDF (HTML-bytes) for a payment."""
    from src.email.branded_templates import TenantBrandingHelper

    result = await db.execute(
        select(Payment)
        .options(
            selectinload(Payment.customer),
            selectinload(Payment.quote),
            selectinload(Payment.opportunity),
        )
        .where(Payment.id == payment_id)
    )
    payment = result.scalar_one_or_none()
    if not payment:
        raise ValueError(f"Payment {payment_id} not found")

    branding = TenantBrandingHelper.get_default_branding()
    if payment.owner_id:
        branding = await TenantBrandingHelper.get_branding_for_user(db, payment.owner_id)

    company = escape(branding.get("company_name", "CRM"))
    primary = escape(branding.get("primary_color", "#6366f1"))
    logo_url = branding.get("logo_url", "")
    footer_text = escape(branding.get("footer_text", ""))

    client_name = "Customer"
    client_email = ""
    if payment.customer:
        client_name = escape(payment.customer.name or "Customer")
        client_email = escape(payment.customer.email or "")

    pay_date = ""
    if payment.updated_at:
        pay_date = payment.updated_at.strftime("%Y-%m-%d")

    logo_html = ""
    if logo_url:
        logo_html = (
            f'<img src="{escape(logo_url)}" alt="{company}" '
            f'width="40" height="40" style="margin-right:12px;border-radius:6px;" />'
        )

    html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Invoice #{payment.id}</title>
<style>
body {{ font-family: Arial, Helvetica, sans-serif; margin: 40px; color: #111827; }}
.header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 3px solid {primary}; padding-bottom: 16px; margin-bottom: 24px; }}
.company {{ font-size: 20px; font-weight: 700; color: {primary}; }}
.invoice-title {{ font-size: 28px; font-weight: 700; color: #111827; margin-bottom: 4px; }}
.meta-table {{ width: 100%; margin-bottom: 24px; }}
.meta-table td {{ padding: 4px 8px; font-size: 14px; }}
.meta-label {{ color: #6b7280; font-weight: 600; width: 140px; }}
.items-table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; }}
.items-table th {{ background-color: #f9fafb; padding: 10px 12px; text-align: left; font-size: 13px; font-weight: 600; color: #6b7280; border-bottom: 2px solid #e5e7eb; }}
.items-table td {{ padding: 10px 12px; border-bottom: 1px solid #e5e7eb; font-size: 14px; }}
.total-row td {{ font-weight: 700; font-size: 16px; border-top: 2px solid #111827; }}
.amount-col {{ text-align: right; font-variant-numeric: tabular-nums; }}
.footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #e5e7eb; text-align: center; font-size: 12px; color: #9ca3af; }}
@media print {{ body {{ margin: 20px; }} }}
</style>
</head>
<body>
<div class="header">
  <div>
    <div class="company">{logo_html}{company}</div>
  </div>
  <div style="text-align: right;">
    <div class="invoice-title">INVOICE</div>
    <div style="font-size: 14px; color: #6b7280;">#{payment.id}</div>
  </div>
</div>

<table class="meta-table">
<tr><td class="meta-label">Bill To:</td><td>{client_name}</td></tr>
<tr><td class="meta-label">Email:</td><td>{client_email}</td></tr>
<tr><td class="meta-label">Date:</td><td>{pay_date}</td></tr>
<tr><td class="meta-label">Status:</td><td>{escape(payment.status)}</td></tr>
<tr><td class="meta-label">Payment Method:</td><td>{escape(payment.payment_method or "Card")}</td></tr>
</table>

<table class="items-table">
<thead>
<tr>
  <th>Description</th>
  <th class="amount-col">Amount</th>
</tr>
</thead>
<tbody>
<tr>
  <td>Payment #{payment.id}</td>
  <td class="amount-col">{escape(payment.currency)} {payment.amount}</td>
</tr>
</tbody>
<tfoot>
<tr class="total-row">
  <td>Total</td>
  <td class="amount-col">{escape(payment.currency)} {payment.amount}</td>
</tr>
</tfoot>
</table>

<div class="footer">
  <p>{company}</p>
  <p>{footer_text}</p>
</div>
</body>
</html>"""

    return html.encode("utf-8")
