"""Branded PDF generation service.

Generates professional HTML-based PDFs for quotes, proposals, and
invoices using tenant branding.  The HTML output can be rendered to PDF
via the browser's print function or a server-side tool like weasyprint.

Since neither reportlab nor weasyprint are in requirements.txt, we
produce self-contained HTML documents styled for print.  Callers can
convert to bytes via ``html.encode("utf-8")`` for direct download or
attachment.
"""

from html import escape
from typing import Optional


class BrandedPDFGenerator:
    """Generates branded, print-ready HTML documents using tenant settings."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _header_html(branding: dict, document_type: str) -> str:
        primary = escape(branding.get("primary_color", "#6366f1"))
        company = escape(branding.get("company_name", "CRM"))
        logo_url = branding.get("logo_url", "")

        logo = ""
        if logo_url:
            logo = (
                f'<img src="{escape(logo_url)}" alt="{company}" '
                f'style="height:40px;margin-right:12px;border-radius:4px;" />'
            )

        return f"""\
<div style="display:flex;justify-content:space-between;align-items:center;
            border-bottom:3px solid {primary};padding-bottom:16px;margin-bottom:24px;">
  <div style="display:flex;align-items:center;">
    {logo}
    <span style="font-size:20px;font-weight:700;color:{primary};">{company}</span>
  </div>
  <div style="font-size:24px;font-weight:700;color:#374151;text-transform:uppercase;letter-spacing:2px;">
    {escape(document_type)}
  </div>
</div>"""

    @staticmethod
    def _footer_html(branding: dict, page_numbers: bool = False) -> str:
        company = escape(branding.get("company_name", "CRM"))
        footer_text = escape(branding.get("footer_text", ""))

        parts = [f'<span>{company}</span>']
        if footer_text:
            parts.append(f'<span style="margin-left:16px;">{footer_text}</span>')

        return f"""\
<div style="border-top:1px solid #e5e7eb;padding-top:12px;margin-top:32px;
            font-size:11px;color:#9ca3af;display:flex;justify-content:space-between;">
  <div>{"  ".join(parts)}</div>
  {'<div>Page <span class="page-num"></span></div>' if page_numbers else ''}
</div>"""

    @staticmethod
    def _wrap_document(content: str, title: str) -> str:
        return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>{escape(title)}</title>
<style>
  @page {{ size: A4; margin: 20mm; }}
  body {{ font-family: Arial, Helvetica, sans-serif; color: #111827; margin: 0; padding: 24px; font-size: 14px; line-height: 1.5; }}
  table {{ border-collapse: collapse; width: 100%; }}
  @media print {{
    body {{ padding: 0; }}
    .no-print {{ display: none; }}
  }}
</style>
</head>
<body>
{content}
</body>
</html>"""

    # ------------------------------------------------------------------
    # Quote PDF
    # ------------------------------------------------------------------

    def generate_quote_pdf(self, quote_data: dict, branding: dict) -> bytes:
        """Generate a professional quote as printable HTML, returned as UTF-8 bytes.

        Expected quote_data keys:
            quote_number, date, valid_until, client_name, client_email,
            client_address, items (list of {description, quantity, unit_price, total}),
            subtotal, discount, tax, total, currency, terms
        """
        currency = escape(str(quote_data.get("currency", "USD")))
        quote_num = escape(str(quote_data.get("quote_number", "")))

        # Items table
        rows = ""
        for item in quote_data.get("items", []):
            rows += (
                f'<tr>'
                f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;">'
                f'{escape(str(item.get("description", "")))}</td>'
                f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:center;">'
                f'{escape(str(item.get("quantity", "")))}</td>'
                f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:right;">'
                f'{currency} {escape(str(item.get("unit_price", "")))}</td>'
                f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:right;">'
                f'{currency} {escape(str(item.get("total", "")))}</td>'
                f'</tr>'
            )

        # Summary rows
        def _summary_row(label: str, value: str, bold: bool = False) -> str:
            weight = "font-weight:700;" if bold else ""
            size = "font-size:16px;" if bold else ""
            return (
                f'<tr><td colspan="3" style="padding:6px 10px;text-align:right;{weight}{size}">'
                f'{escape(label)}</td>'
                f'<td style="padding:6px 10px;text-align:right;{weight}{size}">'
                f'{currency} {escape(str(value))}</td></tr>'
            )

        summary = ""
        if quote_data.get("subtotal") is not None:
            summary += _summary_row("Subtotal", quote_data["subtotal"])
        if quote_data.get("discount"):
            summary += _summary_row("Discount", quote_data["discount"])
        if quote_data.get("tax"):
            summary += _summary_row("Tax", quote_data["tax"])
        summary += _summary_row("Total", quote_data.get("total", "0.00"), bold=True)

        terms = escape(str(quote_data.get("terms", "")))
        terms_block = (
            f'<div style="margin-top:24px;padding:12px;background:#f9fafb;border-radius:4px;font-size:12px;color:#6b7280;">'
            f'<strong>Terms &amp; Conditions</strong><br/>{terms}</div>'
            if terms else ""
        )

        html = (
            self._header_html(branding, "Quote")
            + f"""\
<table style="margin-bottom:24px;font-size:13px;">
<tr>
  <td style="vertical-align:top;width:50%;padding-right:16px;">
    <p style="margin:0 0 4px;color:#6b7280;font-size:12px;">Quote For</p>
    <p style="margin:0;font-weight:600;">{escape(str(quote_data.get("client_name", "")))}</p>
    <p style="margin:0;color:#6b7280;">{escape(str(quote_data.get("client_email", "")))}</p>
    <p style="margin:0;color:#6b7280;">{escape(str(quote_data.get("client_address", "")))}</p>
  </td>
  <td style="vertical-align:top;width:50%;text-align:right;">
    <p style="margin:0 0 4px;"><strong>Quote #:</strong> {quote_num}</p>
    <p style="margin:0;"><strong>Date:</strong> {escape(str(quote_data.get("date", "")))}</p>
    <p style="margin:0;"><strong>Valid Until:</strong> {escape(str(quote_data.get("valid_until", "")))}</p>
  </td>
</tr>
</table>

<table>
<thead>
<tr style="background-color:#f3f4f6;">
  <th style="padding:10px;text-align:left;font-size:12px;color:#6b7280;">Description</th>
  <th style="padding:10px;text-align:center;font-size:12px;color:#6b7280;">Qty</th>
  <th style="padding:10px;text-align:right;font-size:12px;color:#6b7280;">Unit Price</th>
  <th style="padding:10px;text-align:right;font-size:12px;color:#6b7280;">Total</th>
</tr>
</thead>
<tbody>
{rows}
</tbody>
<tfoot>
{summary}
</tfoot>
</table>
{terms_block}
"""
            + self._footer_html(branding)
        )

        return self._wrap_document(html, f"Quote {quote_num}").encode("utf-8")

    # ------------------------------------------------------------------
    # Proposal PDF
    # ------------------------------------------------------------------

    def generate_proposal_pdf(self, proposal_data: dict, branding: dict) -> bytes:
        """Generate a professional proposal as printable HTML, returned as UTF-8 bytes.

        Expected proposal_data keys:
            proposal_title, client_name, date, sections
            (list of {title, content}), total, currency, terms
        """
        primary = escape(branding.get("primary_color", "#6366f1"))
        company = escape(branding.get("company_name", "CRM"))
        title = escape(str(proposal_data.get("proposal_title", "Proposal")))
        client = escape(str(proposal_data.get("client_name", "")))
        date_str = escape(str(proposal_data.get("date", "")))
        currency = escape(str(proposal_data.get("currency", "USD")))
        total = escape(str(proposal_data.get("total", "")))
        logo_url = branding.get("logo_url", "")

        logo = ""
        if logo_url:
            logo = (
                f'<img src="{escape(logo_url)}" alt="{company}" '
                f'style="height:60px;margin-bottom:16px;border-radius:6px;" />'
            )

        # Cover page
        cover = f"""\
<div style="text-align:center;padding:80px 24px 40px;page-break-after:always;">
  {logo}
  <h1 style="font-size:32px;color:{primary};margin:0 0 8px;">{title}</h1>
  <p style="font-size:16px;color:#6b7280;margin:0 0 24px;">Prepared for {client}</p>
  <p style="font-size:14px;color:#9ca3af;">{company} &middot; {date_str}</p>
</div>"""

        # Table of contents
        sections = proposal_data.get("sections", [])
        toc_items = ""
        for i, sec in enumerate(sections, 1):
            toc_items += (
                f'<p style="margin:4px 0;font-size:14px;">'
                f'{i}. {escape(str(sec.get("title", "")))}</p>'
            )

        toc = f"""\
<div style="margin-bottom:32px;page-break-after:always;">
  <h2 style="font-size:18px;color:{primary};border-bottom:2px solid {primary};padding-bottom:8px;">
    Table of Contents</h2>
  {toc_items}
</div>"""

        # Sections
        sections_html = ""
        for i, sec in enumerate(sections, 1):
            sections_html += (
                f'<div style="margin-bottom:24px;">'
                f'<h2 style="font-size:18px;color:{primary};margin:0 0 8px;">'
                f'{i}. {escape(str(sec.get("title", "")))}</h2>'
                f'<div style="font-size:14px;line-height:1.6;">'
                f'{escape(str(sec.get("content", "")))}</div>'
                f'</div>'
            )

        # Investment
        investment = ""
        if total:
            investment = (
                f'<div style="margin:24px 0;padding:16px;background:#f0fdf4;border-radius:6px;text-align:center;">'
                f'<p style="margin:0;font-size:13px;color:#6b7280;">Total Investment</p>'
                f'<p style="margin:4px 0 0;font-size:28px;font-weight:700;color:#111827;">{currency} {total}</p>'
                f'</div>'
            )

        terms = escape(str(proposal_data.get("terms", "")))
        terms_block = (
            f'<div style="margin-top:24px;padding:12px;background:#f9fafb;border-radius:4px;font-size:12px;color:#6b7280;">'
            f'<strong>Terms &amp; Conditions</strong><br/>{terms}</div>'
            if terms else ""
        )

        html = cover + toc + sections_html + investment + terms_block + self._footer_html(branding, page_numbers=True)
        return self._wrap_document(html, title).encode("utf-8")

    # ------------------------------------------------------------------
    # Invoice PDF
    # ------------------------------------------------------------------

    def generate_invoice_pdf(self, payment_data: dict, branding: dict) -> bytes:
        """Generate a professional invoice as printable HTML, returned as UTF-8 bytes.

        Expected payment_data keys:
            invoice_number, date, due_date, client_name, client_email,
            client_address, items (list of {description, quantity, unit_price, total}),
            subtotal, tax, total, currency, payment_status, notes
        """
        currency = escape(str(payment_data.get("currency", "USD")))
        inv_num = escape(str(payment_data.get("invoice_number", "")))
        status = escape(str(payment_data.get("payment_status", "unpaid")))
        accent = escape(branding.get("accent_color", "#22c55e"))

        status_color = accent if status.lower() == "paid" else "#f59e0b"

        rows = ""
        for item in payment_data.get("items", []):
            rows += (
                f'<tr>'
                f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;">'
                f'{escape(str(item.get("description", "")))}</td>'
                f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:center;">'
                f'{escape(str(item.get("quantity", "")))}</td>'
                f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:right;">'
                f'{currency} {escape(str(item.get("unit_price", "")))}</td>'
                f'<td style="padding:8px 10px;border-bottom:1px solid #e5e7eb;text-align:right;">'
                f'{currency} {escape(str(item.get("total", "")))}</td>'
                f'</tr>'
            )

        def _row(label: str, value: str, bold: bool = False) -> str:
            w = "font-weight:700;" if bold else ""
            s = "font-size:16px;" if bold else ""
            return (
                f'<tr><td colspan="3" style="padding:6px 10px;text-align:right;{w}{s}">'
                f'{escape(label)}</td>'
                f'<td style="padding:6px 10px;text-align:right;{w}{s}">'
                f'{currency} {escape(str(value))}</td></tr>'
            )

        summary = ""
        if payment_data.get("subtotal") is not None:
            summary += _row("Subtotal", payment_data["subtotal"])
        if payment_data.get("tax"):
            summary += _row("Tax", payment_data["tax"])
        summary += _row("Total", payment_data.get("total", "0.00"), bold=True)

        notes = escape(str(payment_data.get("notes", "")))
        notes_block = (
            f'<div style="margin-top:16px;font-size:12px;color:#6b7280;">'
            f'<strong>Notes:</strong> {notes}</div>'
            if notes else ""
        )

        html = (
            self._header_html(branding, "Invoice")
            + f"""\
<div style="display:flex;justify-content:space-between;margin-bottom:24px;">
  <div>
    <p style="margin:0 0 4px;color:#6b7280;font-size:12px;">Bill To</p>
    <p style="margin:0;font-weight:600;">{escape(str(payment_data.get("client_name", "")))}</p>
    <p style="margin:0;color:#6b7280;font-size:13px;">{escape(str(payment_data.get("client_email", "")))}</p>
    <p style="margin:0;color:#6b7280;font-size:13px;">{escape(str(payment_data.get("client_address", "")))}</p>
  </div>
  <div style="text-align:right;font-size:13px;">
    <p style="margin:0 0 4px;"><strong>Invoice #:</strong> {inv_num}</p>
    <p style="margin:0;"><strong>Date:</strong> {escape(str(payment_data.get("date", "")))}</p>
    <p style="margin:0;"><strong>Due Date:</strong> {escape(str(payment_data.get("due_date", "")))}</p>
    <p style="margin:8px 0 0;">
      <span style="background:{status_color};color:#fff;padding:2px 10px;border-radius:10px;font-size:12px;font-weight:600;">
        {status.upper()}
      </span>
    </p>
  </div>
</div>

<table>
<thead>
<tr style="background-color:#f3f4f6;">
  <th style="padding:10px;text-align:left;font-size:12px;color:#6b7280;">Description</th>
  <th style="padding:10px;text-align:center;font-size:12px;color:#6b7280;">Qty</th>
  <th style="padding:10px;text-align:right;font-size:12px;color:#6b7280;">Unit Price</th>
  <th style="padding:10px;text-align:right;font-size:12px;color:#6b7280;">Total</th>
</tr>
</thead>
<tbody>
{rows}
</tbody>
<tfoot>
{summary}
</tfoot>
</table>
{notes_block}
"""
            + self._footer_html(branding)
        )

        return self._wrap_document(html, f"Invoice {inv_num}").encode("utf-8")
