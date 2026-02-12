"""Tests for branded email templates and PDF generation.

Tests run against a real SQLite database via the shared conftest
fixtures -- no mocking.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.whitelabel.models import Tenant, TenantSettings, TenantUser
from src.email.branded_templates import (
    TenantBrandingHelper,
    render_branded_email,
    render_quote_email,
    render_proposal_email,
    render_payment_receipt_email,
    render_campaign_wrapper,
)
from src.email.pdf_service import BrandedPDFGenerator
from src.email.service import EmailService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_BRANDING = {
    "company_name": "Acme Corp",
    "logo_url": "https://example.com/logo.png",
    "primary_color": "#3b82f6",
    "secondary_color": "#6366f1",
    "accent_color": "#10b981",
    "footer_text": "Acme Corp - Building the future",
    "privacy_policy_url": "https://acme.com/privacy",
    "terms_of_service_url": "https://acme.com/terms",
    "email_from_name": "Acme Sales",
    "email_from_address": "sales@acme.com",
}

SAMPLE_QUOTE = {
    "quote_number": "Q-2026-001",
    "client_name": "John Smith",
    "total": "15,000.00",
    "currency": "USD",
    "valid_until": "2026-03-15",
    "items": [
        {"description": "Enterprise License", "quantity": 1, "unit_price": "10,000.00", "total": "10,000.00"},
        {"description": "Premium Support", "quantity": 1, "unit_price": "5,000.00", "total": "5,000.00"},
    ],
    "view_url": "https://app.acme.com/quotes/Q-2026-001",
}

SAMPLE_PROPOSAL = {
    "proposal_title": "CRM Implementation Plan",
    "client_name": "Jane Doe",
    "summary": "Comprehensive CRM rollout for 50 users including training and data migration.",
    "total": "85,000.00",
    "currency": "USD",
    "view_url": "https://app.acme.com/proposals/P-001",
}

SAMPLE_PAYMENT = {
    "receipt_number": "REC-2026-042",
    "client_name": "Bob Wilson",
    "amount": "12,500.00",
    "currency": "USD",
    "payment_date": "2026-02-10",
    "payment_method": "Visa ending 4242",
    "items": [
        {"description": "Annual License", "amount": "10,000.00"},
        {"description": "Setup Fee", "amount": "2,500.00"},
    ],
}


# ===================================================================
# TenantBrandingHelper tests
# ===================================================================

class TestTenantBrandingHelper:

    async def test_get_branding_for_user_returns_tenant_data(
        self, db_session: AsyncSession, test_user: User, test_tenant: Tenant, test_tenant_user: TenantUser,
    ):
        branding = await TenantBrandingHelper.get_branding_for_user(db_session, test_user.id)

        assert branding["company_name"] == "Test Tenant Inc"
        assert branding["primary_color"] == "#6366f1"
        assert branding["secondary_color"] == "#8b5cf6"
        assert branding["accent_color"] == "#22c55e"
        assert branding["logo_url"] == "https://example.com/logo.png"
        assert branding["footer_text"] == "Test Tenant Footer"

    async def test_get_branding_falls_back_to_defaults_when_no_tenant(
        self, db_session: AsyncSession, test_user: User,
    ):
        branding = await TenantBrandingHelper.get_branding_for_user(db_session, test_user.id)

        defaults = TenantBrandingHelper.get_default_branding()
        assert branding == defaults
        assert branding["company_name"] == "CRM"
        assert branding["primary_color"] == "#6366f1"

    async def test_get_default_branding_has_required_keys(self):
        branding = TenantBrandingHelper.get_default_branding()
        required_keys = {
            "company_name", "logo_url", "primary_color", "secondary_color",
            "accent_color", "footer_text", "privacy_policy_url",
            "terms_of_service_url", "email_from_name", "email_from_address",
        }
        assert required_keys == set(branding.keys())


# ===================================================================
# Base email template tests
# ===================================================================

class TestRenderBrandedEmail:

    def test_renders_with_all_branding_fields(self):
        html = render_branded_email(
            branding=SAMPLE_BRANDING,
            subject="Test Subject",
            headline="Welcome",
            body_html="<p>Hello World</p>",
        )

        assert "Acme Corp" in html
        assert "#3b82f6" in html  # primary_color in header
        assert "Welcome" in html
        assert "<p>Hello World</p>" in html
        assert "Acme Corp - Building the future" in html
        assert "https://acme.com/privacy" in html
        assert "Privacy Policy" in html
        assert "https://acme.com/terms" in html
        assert "Terms of Service" in html
        assert "logo.png" in html

    def test_renders_cta_button(self):
        html = render_branded_email(
            branding=SAMPLE_BRANDING,
            subject="Test",
            headline="Action Required",
            body_html="<p>Click below</p>",
            cta_text="View Dashboard",
            cta_url="https://app.acme.com/dashboard",
        )

        assert "View Dashboard" in html
        assert "https://app.acme.com/dashboard" in html

    def test_renders_without_cta(self):
        html = render_branded_email(
            branding=SAMPLE_BRANDING,
            subject="Test",
            headline="Info",
            body_html="<p>No action needed</p>",
        )

        assert "No action needed" in html
        # No CTA button should be present
        assert "View Dashboard" not in html

    def test_renders_without_logo(self):
        branding = {**SAMPLE_BRANDING, "logo_url": ""}
        html = render_branded_email(
            branding=branding,
            subject="Test",
            headline="No Logo",
            body_html="<p>Content</p>",
        )

        assert "Acme Corp" in html
        assert '<img' not in html.split('</td></tr></table>')[0]  # no img in header area

    def test_renders_without_footer_links(self):
        branding = {
            **SAMPLE_BRANDING,
            "footer_text": "",
            "privacy_policy_url": "",
            "terms_of_service_url": "",
        }
        html = render_branded_email(
            branding=branding,
            subject="Test",
            headline="Minimal",
            body_html="<p>Content</p>",
        )

        assert "Privacy Policy" not in html
        assert "Terms of Service" not in html

    def test_html_structure_is_valid(self):
        html = render_branded_email(
            branding=SAMPLE_BRANDING,
            subject="Structure Test",
            headline="Hello",
            body_html="<p>Body</p>",
        )

        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "prefers-color-scheme:dark" in html

    def test_escapes_special_characters(self):
        branding = {**SAMPLE_BRANDING, "company_name": "O'Brien & Sons <LLC>"}
        html = render_branded_email(
            branding=branding,
            subject="Test",
            headline="Special <chars> & \"quotes\"",
            body_html="<p>Safe content</p>",
        )

        assert "O&#x27;Brien &amp; Sons &lt;LLC&gt;" in html
        assert "Special &lt;chars&gt; &amp; &quot;quotes&quot;" in html


# ===================================================================
# Quote email template tests
# ===================================================================

class TestRenderQuoteEmail:

    def test_renders_quote_with_items(self):
        subject, html = render_quote_email(SAMPLE_BRANDING, SAMPLE_QUOTE)

        assert "Q-2026-001" in subject
        assert "Acme Corp" in subject
        assert "Q-2026-001" in html
        assert "John Smith" in html
        assert "Enterprise License" in html
        assert "Premium Support" in html
        assert "15,000.00" in html
        assert "2026-03-15" in html

    def test_quote_has_view_button(self):
        subject, html = render_quote_email(SAMPLE_BRANDING, SAMPLE_QUOTE)

        assert "View Quote" in html
        assert "https://app.acme.com/quotes/Q-2026-001" in html

    def test_quote_without_view_url(self):
        data = {**SAMPLE_QUOTE}
        del data["view_url"]
        subject, html = render_quote_email(SAMPLE_BRANDING, data)

        assert "View Quote" not in html


# ===================================================================
# Proposal email template tests
# ===================================================================

class TestRenderProposalEmail:

    def test_renders_proposal_correctly(self):
        subject, html = render_proposal_email(SAMPLE_BRANDING, SAMPLE_PROPOSAL)

        assert "CRM Implementation Plan" in subject
        assert "Acme Corp" in subject
        assert "Jane Doe" in html
        assert "Comprehensive CRM rollout" in html
        assert "85,000.00" in html

    def test_proposal_has_view_button(self):
        subject, html = render_proposal_email(SAMPLE_BRANDING, SAMPLE_PROPOSAL)

        assert "View Proposal" in html
        assert "https://app.acme.com/proposals/P-001" in html


# ===================================================================
# Payment receipt email template tests
# ===================================================================

class TestRenderPaymentReceiptEmail:

    def test_renders_receipt_correctly(self):
        subject, html = render_payment_receipt_email(SAMPLE_BRANDING, SAMPLE_PAYMENT)

        assert "REC-2026-042" in subject
        assert "Acme Corp" in subject
        assert "Bob Wilson" in html
        assert "12,500.00" in html
        assert "2026-02-10" in html
        assert "Visa ending 4242" in html

    def test_receipt_has_line_items(self):
        subject, html = render_payment_receipt_email(SAMPLE_BRANDING, SAMPLE_PAYMENT)

        assert "Annual License" in html
        assert "Setup Fee" in html
        assert "10,000.00" in html
        assert "2,500.00" in html

    def test_receipt_without_items(self):
        data = {**SAMPLE_PAYMENT, "items": []}
        subject, html = render_payment_receipt_email(SAMPLE_BRANDING, data)

        assert "REC-2026-042" in html
        assert "12,500.00" in html


# ===================================================================
# Campaign wrapper tests
# ===================================================================

class TestRenderCampaignWrapper:

    def test_wraps_campaign_body(self):
        html = render_campaign_wrapper(
            branding=SAMPLE_BRANDING,
            campaign_body="<h2>Spring Sale!</h2><p>50% off everything.</p>",
            unsubscribe_url="https://app.acme.com/unsubscribe/abc123",
        )

        assert "Spring Sale!" in html
        assert "50% off everything" in html
        assert "Acme Corp" in html

    def test_includes_unsubscribe_link(self):
        html = render_campaign_wrapper(
            branding=SAMPLE_BRANDING,
            campaign_body="<p>Campaign content</p>",
            unsubscribe_url="https://app.acme.com/unsubscribe/abc123",
        )

        assert "Unsubscribe" in html
        assert "https://app.acme.com/unsubscribe/abc123" in html


# ===================================================================
# PDF generation tests
# ===================================================================

class TestBrandedPDFGenerator:

    def setup_method(self):
        self.gen = BrandedPDFGenerator()

    def test_generate_quote_pdf_returns_bytes(self):
        quote_data = {
            "quote_number": "Q-001",
            "date": "2026-02-10",
            "valid_until": "2026-03-10",
            "client_name": "Alice Brown",
            "client_email": "alice@example.com",
            "client_address": "123 Main St",
            "items": [
                {"description": "Widget", "quantity": 10, "unit_price": "50.00", "total": "500.00"},
            ],
            "subtotal": "500.00",
            "discount": "50.00",
            "tax": "45.00",
            "total": "495.00",
            "currency": "USD",
            "terms": "Net 30",
        }

        result = self.gen.generate_quote_pdf(quote_data, SAMPLE_BRANDING)

        assert isinstance(result, bytes)
        html = result.decode("utf-8")
        assert "Quote" in html
        assert "Q-001" in html
        assert "Alice Brown" in html
        assert "Widget" in html
        assert "495.00" in html
        assert "Net 30" in html
        assert "Acme Corp" in html

    def test_generate_proposal_pdf_returns_bytes(self):
        proposal_data = {
            "proposal_title": "Digital Transformation",
            "client_name": "Bob Corp",
            "date": "2026-02-10",
            "sections": [
                {"title": "Executive Summary", "content": "Overview of our approach."},
                {"title": "Pricing", "content": "Competitive rates."},
            ],
            "total": "120,000.00",
            "currency": "USD",
            "terms": "Payment on milestones",
        }

        result = self.gen.generate_proposal_pdf(proposal_data, SAMPLE_BRANDING)

        assert isinstance(result, bytes)
        html = result.decode("utf-8")
        assert "Digital Transformation" in html
        assert "Bob Corp" in html
        assert "Executive Summary" in html
        assert "Pricing" in html
        assert "120,000.00" in html
        assert "Table of Contents" in html
        assert "Acme Corp" in html

    def test_generate_invoice_pdf_returns_bytes(self):
        invoice_data = {
            "invoice_number": "INV-2026-100",
            "date": "2026-02-10",
            "due_date": "2026-03-10",
            "client_name": "Charlie Inc",
            "client_email": "charlie@example.com",
            "client_address": "456 Oak Ave",
            "items": [
                {"description": "Consulting", "quantity": 20, "unit_price": "200.00", "total": "4,000.00"},
            ],
            "subtotal": "4,000.00",
            "tax": "400.00",
            "total": "4,400.00",
            "currency": "USD",
            "payment_status": "paid",
            "notes": "Thank you for your business.",
        }

        result = self.gen.generate_invoice_pdf(invoice_data, SAMPLE_BRANDING)

        assert isinstance(result, bytes)
        html = result.decode("utf-8")
        assert "Invoice" in html
        assert "INV-2026-100" in html
        assert "Charlie Inc" in html
        assert "Consulting" in html
        assert "4,400.00" in html
        assert "PAID" in html
        assert "Thank you for your business" in html

    def test_invoice_unpaid_status(self):
        invoice_data = {
            "invoice_number": "INV-002",
            "date": "2026-02-10",
            "due_date": "2026-03-10",
            "client_name": "Test Client",
            "items": [],
            "total": "1,000.00",
            "currency": "USD",
            "payment_status": "unpaid",
        }

        result = self.gen.generate_invoice_pdf(invoice_data, SAMPLE_BRANDING)
        html = result.decode("utf-8")

        assert "UNPAID" in html
        # Unpaid should use warning color, not accent
        assert "#f59e0b" in html


# ===================================================================
# EmailService.send_branded_email integration test
# ===================================================================

class TestSendBrandedEmail:

    async def test_send_branded_email_queues_with_branding(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_tenant: Tenant,
        test_tenant_user: TenantUser,
    ):
        service = EmailService(db_session)
        email = await service.send_branded_email(
            to_email="recipient@example.com",
            subject="Branded Test",
            headline="Welcome to Our Platform",
            body_html="<p>Thank you for joining.</p>",
            sent_by_id=test_user.id,
        )

        assert email.to_email == "recipient@example.com"
        assert email.subject == "Branded Test"
        assert "Test Tenant Inc" in email.body
        assert "Welcome to Our Platform" in email.body
        assert "Thank you for joining" in email.body
        assert email.sent_by_id == test_user.id

    async def test_send_branded_email_uses_defaults_without_tenant(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        service = EmailService(db_session)
        email = await service.send_branded_email(
            to_email="recipient@example.com",
            subject="Default Test",
            headline="Hello",
            body_html="<p>Content</p>",
            sent_by_id=test_user.id,
        )

        assert "CRM" in email.body
        assert "Hello" in email.body

    async def test_send_branded_email_with_cta(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_tenant: Tenant,
        test_tenant_user: TenantUser,
    ):
        service = EmailService(db_session)
        email = await service.send_branded_email(
            to_email="recipient@example.com",
            subject="CTA Test",
            headline="Action Required",
            body_html="<p>Please review.</p>",
            sent_by_id=test_user.id,
            cta_text="Review Now",
            cta_url="https://app.example.com/review/123",
        )

        assert "Review Now" in email.body
        assert "https://app.example.com/review/123" in email.body
