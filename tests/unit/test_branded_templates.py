"""Tests for branded email templates and PDF generation.

Tests run against a real SQLite database via the shared conftest
fixtures -- no mocking.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth.models import User
from src.email.branded_templates import (
    TenantBrandingHelper,
    render_branded_email,
    render_campaign_wrapper,
    render_contract_expiring_email,
    render_contract_signed_email,
    render_email_reply_email,
    render_lead_assigned_email,
    render_mention_email,
    render_payment_receipt_email,
    render_proposal_email,
    render_proposal_signed_email,
    render_quote_email,
    render_task_due_email,
)
from src.email.pdf_service import BrandedPDFGenerator
from src.email.service import EmailService
from src.whitelabel.models import Tenant, TenantUser

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
    """Tests for retrieving tenant-specific branding configuration."""

    async def test_get_branding_for_user_returns_tenant_data(
        self, db_session: AsyncSession, test_user: User, test_tenant: Tenant, test_tenant_user: TenantUser,
    ):
        """Should return tenant-specific branding when user belongs to a tenant."""
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
        """Should fall back to default branding when user has no tenant."""
        branding = await TenantBrandingHelper.get_branding_for_user(db_session, test_user.id)

        defaults = TenantBrandingHelper.get_default_branding()
        assert branding == defaults
        assert branding["company_name"] == "CRM"
        # PR #325: Link Creative palette swap — primary_color is now
        # the brand-spotlight gold (drives accent rule + tagline pipes
        # + wordmark first word) rather than the legacy slate dark text.
        assert branding["primary_color"] == "#CF982C"

    async def test_get_default_branding_has_required_keys(self):
        """Should include all required branding keys in the default branding dict."""
        branding = TenantBrandingHelper.get_default_branding()
        required_keys = {
            "company_name", "logo_url", "primary_color", "secondary_color",
            "accent_color", "bg_color_light", "surface_color_light",
            "footer_text", "privacy_policy_url",
            "terms_of_service_url", "email_from_name", "email_from_address",
            # PR #325 (migration 034): tagline + 6 social URL fields
            # surface through the default branding dict so the email
            # wrapper renders them with empty fallbacks when no
            # tenant is configured.
            "tagline",
            "social_facebook_url",
            "social_instagram_url",
            "social_tiktok_url",
            "social_linkedin_url",
            "social_youtube_url",
            "social_website_url",
        }
        assert required_keys == set(branding.keys())


# ===================================================================
# Base email template tests
# ===================================================================

class TestRenderBrandedEmail:
    """Tests for the base branded email template rendering."""

    def test_renders_with_all_branding_fields(self):
        """Should include all branding elements in the rendered HTML."""
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
        """Should render a call-to-action button when cta_text and cta_url are provided."""
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
        """Should render the email without a CTA button when none is provided."""
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
        """Should render the email without an img tag when logo_url is empty."""
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
        """Should omit privacy and terms links when footer URLs are empty."""
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
        """Should produce valid HTML with DOCTYPE and light-only color scheme."""
        html = render_branded_email(
            branding=SAMPLE_BRANDING,
            subject="Structure Test",
            headline="Hello",
            body_html="<p>Body</p>",
        )

        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        # PR #325: the wrapper is fixed-light by design (no dark-mode
        # variant) — the meta is ``content="only light"`` and the
        # @media (prefers-color-scheme) block was removed.
        assert 'content="only light"' in html
        assert "prefers-color-scheme" not in html

    def test_escapes_special_characters(self):
        """Should HTML-escape special characters in branding and headline text."""
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
    """Tests for quote-specific branded email rendering."""

    def test_renders_quote_with_items(self):
        """Should render quote details including line items, total, and validity date."""
        subject, html = render_quote_email(SAMPLE_BRANDING, SAMPLE_QUOTE)

        assert "Q-2026-001" in subject
        assert "Acme Corp" in subject
        assert "Q-2026-001" in html
        assert "John Smith" in html
        assert "Enterprise License" in html
        assert "Premium Support" in html
        assert "15,000.00" in html
        assert "2026-03-15" in html

    def test_quote_has_review_accept_button_with_view_url(self):
        """Should include a review and accept button when view_url is provided."""
        subject, html = render_quote_email(SAMPLE_BRANDING, SAMPLE_QUOTE)

        assert "Review &amp; Accept Quote" in html
        assert "https://app.acme.com/quotes/Q-2026-001" in html
        # E-sign flow copy directs recipient to click through
        assert "accept or decline" in html

    def test_quote_without_view_url(self):
        """Should render fallback copy without a review button when view_url is absent."""
        data = {**SAMPLE_QUOTE}
        del data["view_url"]
        subject, html = render_quote_email(SAMPLE_BRANDING, data)

        assert "Review &amp; Accept Quote" not in html
        # Fallback copy without link
        assert "Please find your quote" in html


# ===================================================================
# Proposal email template tests
# ===================================================================

class TestRenderProposalEmail:
    """Tests for proposal-specific branded email rendering."""

    def test_renders_proposal_correctly(self):
        """Should render proposal title, client name, and summary in the email."""
        subject, html = render_proposal_email(SAMPLE_BRANDING, SAMPLE_PROPOSAL)

        assert "CRM Implementation Plan" in subject
        assert "Acme Corp" in subject
        assert "Jane Doe" in html
        assert "Comprehensive CRM rollout" in html
        assert "Proposed investment" not in html
        assert "USD" not in html

    def test_proposal_has_view_button(self):
        """Should include a View Proposal button linking to the proposal URL."""
        subject, html = render_proposal_email(SAMPLE_BRANDING, SAMPLE_PROPOSAL)

        assert "View Proposal" in html
        assert "https://app.acme.com/proposals/P-001" in html


# ===================================================================
# Payment receipt email template tests
# ===================================================================

class TestRenderPaymentReceiptEmail:
    """Tests for payment receipt branded email rendering."""

    def test_renders_receipt_correctly(self):
        """Should render receipt number, client, amount, date, and payment method."""
        subject, html = render_payment_receipt_email(SAMPLE_BRANDING, SAMPLE_PAYMENT)

        assert "REC-2026-042" in subject
        assert "Acme Corp" in subject
        assert "Bob Wilson" in html
        assert "12,500.00" in html
        assert "2026-02-10" in html
        assert "Visa ending 4242" in html

    def test_receipt_has_line_items(self):
        """Should include individual line items and their amounts in the receipt."""
        subject, html = render_payment_receipt_email(SAMPLE_BRANDING, SAMPLE_PAYMENT)

        assert "Annual License" in html
        assert "Setup Fee" in html
        assert "10,000.00" in html
        assert "2,500.00" in html

    def test_receipt_without_items(self):
        """Should render the receipt summary even when the items list is empty."""
        data = {**SAMPLE_PAYMENT, "items": []}
        subject, html = render_payment_receipt_email(SAMPLE_BRANDING, data)

        assert "REC-2026-042" in html
        assert "12,500.00" in html


# ===================================================================
# Campaign wrapper tests
# ===================================================================

class TestRenderCampaignWrapper:
    """Tests for wrapping campaign content in branded email layout."""

    def test_wraps_campaign_body(self):
        """Should wrap campaign HTML body with branded header and footer."""
        html = render_campaign_wrapper(
            branding=SAMPLE_BRANDING,
            campaign_body="<h2>Spring Sale!</h2><p>50% off everything.</p>",
            unsubscribe_url="https://app.acme.com/unsubscribe/abc123",
        )

        assert "Spring Sale!" in html
        assert "50% off everything" in html
        assert "Acme Corp" in html

    def test_includes_unsubscribe_link(self):
        """Should include the unsubscribe link in the campaign email footer."""
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
    """Tests for branded PDF generation of quotes, proposals, and invoices."""

    def setup_method(self):
        """Initialize a BrandedPDFGenerator instance for each test."""
        self.gen = BrandedPDFGenerator()

    def test_generate_quote_pdf_returns_bytes(self):
        """Should return bytes containing branded HTML with quote details and line items."""
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
        """Should return bytes containing branded HTML with proposal sections and table of contents."""
        proposal_data = {
            "proposal_title": "Digital Transformation",
            "client_name": "Bob Corp",
            "date": "2026-02-10",
            "sections": [
                {"title": "Executive Summary", "content": "Overview of our approach."},
                {"title": "Pricing", "content": "Competitive rates."},
            ],
            "terms": "Payment on milestones",
        }

        result = self.gen.generate_proposal_pdf(proposal_data, SAMPLE_BRANDING)

        assert isinstance(result, bytes)
        html = result.decode("utf-8")
        assert "Digital Transformation" in html
        assert "Bob Corp" in html
        assert "Executive Summary" in html
        assert "Pricing" in html
        assert "Total Investment" not in html
        assert "120,000.00" not in html
        assert "USD" not in html
        assert "Table of Contents" in html
        assert "Acme Corp" in html

    def test_generate_invoice_pdf_returns_bytes(self):
        """Should return bytes containing branded HTML with invoice details and paid status."""
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
        """Should display UNPAID status with warning color for unpaid invoices."""
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
    """Tests for EmailService.send_branded_email integration with tenant branding."""

    async def test_send_branded_email_queues_with_branding(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_tenant: Tenant,
        test_tenant_user: TenantUser,
    ):
        """Should queue a branded email using the tenant's branding settings."""
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
        """Should use default CRM branding when user has no tenant association."""
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
        """Should include CTA button text and URL in the branded email body."""
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


# ---------------------------------------------------------------------------
# URL scheme allowlist tests (Session 3 3a.3)
# ---------------------------------------------------------------------------


class TestUrlSchemeAllowlist:
    """Branded templates must reject dangerous URL schemes at render time."""

    def test_javascript_privacy_url_is_dropped(self):
        """``javascript:`` privacy URL must not end up in the rendered HTML."""
        branding = dict(SAMPLE_BRANDING)
        branding["privacy_policy_url"] = "javascript:alert('pwn')"
        html_out = render_branded_email(
            branding=branding,
            subject="s",
            headline="h",
            body_html="<p>b</p>",
        )
        assert "javascript:" not in html_out
        # Link should be omitted entirely rather than rendered with a broken href.
        assert "Privacy Policy" not in html_out

    def test_javascript_terms_url_is_dropped(self):
        branding = dict(SAMPLE_BRANDING)
        branding["terms_of_service_url"] = "JavaScript:alert(1)"  # mixed case bypass attempt
        html_out = render_branded_email(
            branding=branding,
            subject="s",
            headline="h",
            body_html="<p>b</p>",
        )
        assert "javascript:" not in html_out.lower()
        assert "Terms of Service" not in html_out

    def test_data_url_logo_is_dropped(self):
        """``data:`` URLs in logos are blocked to stop HTML-in-image bombs."""
        branding = dict(SAMPLE_BRANDING)
        branding["logo_url"] = "data:text/html,<script>alert(1)</script>"
        html_out = render_branded_email(
            branding=branding,
            subject="s",
            headline="h",
            body_html="<p>b</p>",
        )
        assert "data:text/html" not in html_out
        assert "<script>" not in html_out

    def test_javascript_cta_url_is_dropped(self):
        """A ``javascript:`` cta_url must not emit an ``href=javascript:...``."""
        html_out = render_branded_email(
            branding=SAMPLE_BRANDING,
            subject="s",
            headline="h",
            body_html="<p>b</p>",
            cta_text="Click me",
            cta_url="javascript:alert('xss')",
        )
        assert "javascript:" not in html_out
        # The CTA is entirely suppressed when the URL is rejected.
        assert "Click me" not in html_out

    def test_valid_https_urls_pass_through(self):
        """Valid https:// URLs must still render unchanged."""
        html_out = render_branded_email(
            branding=SAMPLE_BRANDING,
            subject="s",
            headline="h",
            body_html="<p>b</p>",
            cta_text="Accept",
            cta_url="https://app.example.com/accept",
        )
        assert "https://app.example.com/accept" in html_out
        assert "https://acme.com/privacy" in html_out
        assert "https://acme.com/terms" in html_out

    def test_campaign_unsubscribe_blocks_javascript(self):
        """``render_campaign_wrapper`` must not emit ``javascript:`` unsubscribe links."""
        html_out = render_campaign_wrapper(
            branding=SAMPLE_BRANDING,
            campaign_body="<p>Hello</p>",
            unsubscribe_url="javascript:alert(1)",
        )
        assert "javascript:" not in html_out
        assert "Unsubscribe" not in html_out

    def test_campaign_unsubscribe_allows_relative_path(self):
        """Site-relative unsubscribe paths (existing behavior) remain supported."""
        html_out = render_campaign_wrapper(
            branding=SAMPLE_BRANDING,
            campaign_body="<p>Hello</p>",
            unsubscribe_url="/api/campaigns/1/unsubscribe?member_id=2",
        )
        assert "Unsubscribe" in html_out
        assert "/api/campaigns/1/unsubscribe" in html_out


class TestTenantSettingsUrlValidation:
    """Schema must reject dangerous URL schemes before they reach the DB."""

    def test_privacy_policy_javascript_rejected(self):
        from pydantic import ValidationError
        from src.whitelabel.schemas import TenantSettingsUpdate

        with pytest.raises(ValidationError):
            TenantSettingsUpdate(privacy_policy_url="javascript:alert(1)")

    def test_terms_of_service_javascript_rejected(self):
        from pydantic import ValidationError
        from src.whitelabel.schemas import TenantSettingsUpdate

        with pytest.raises(ValidationError):
            TenantSettingsUpdate(terms_of_service_url="JAVASCRIPT:alert(1)")

    def test_privacy_policy_https_accepted(self):
        from src.whitelabel.schemas import TenantSettingsUpdate

        payload = TenantSettingsUpdate(privacy_policy_url="https://example.com/privacy")
        assert payload.privacy_policy_url == "https://example.com/privacy"

    def test_mixed_case_javascript_logo_url_rejected(self):
        """Case-insensitive scheme check blocks ``Javascript:`` logo URLs."""
        from pydantic import ValidationError
        from src.whitelabel.schemas import TenantSettingsUpdate

        with pytest.raises(ValidationError):
            TenantSettingsUpdate(logo_url="Javascript:alert(1)")


# ---------------------------------------------------------------------------
# Notification matrix templates (lead_assigned / task_due / mention /
# email_reply_received / contract_expiring / contract_signed /
# proposal_signed)
# ---------------------------------------------------------------------------

NOTIF_BRANDING = {
    "company_name": "Acme Corp",
    "logo_url": "",
    "primary_color": "#ff4400",
    "secondary_color": "#ffaa00",
    "accent_color": "#22c55e",
    "footer_text": "Acme Corp — 123 Main St",
    "privacy_policy_url": "",
    "terms_of_service_url": "",
    "email_from_name": "Acme Corp",
    "email_from_address": "",
}


class TestLeadAssignedEmail:
    """Renderer for the ``lead_assigned`` matrix event."""

    def test_renders_subject_and_lead_card(self):
        """Should put the lead's name in the subject, render the lead card, and include a CTA."""
        subject, html = render_lead_assigned_email(
            NOTIF_BRANDING,
            {
                "lead_full_name": "Jane Cooper",
                "lead_email": "jane@example.com",
                "lead_company_name": "Cooper LLC",
                "lead_url": "https://crm.example.com/leads/42",
                "assigner_name": "Daisy Lead",
            },
        )
        assert subject == "New lead assigned: Jane Cooper"
        assert "Jane Cooper" in html
        assert "Cooper LLC" in html
        assert "jane@example.com" in html
        assert "Daisy Lead" in html
        assert "https://crm.example.com/leads/42" in html
        assert NOTIF_BRANDING["primary_color"] in html

    def test_missing_optional_fields_no_blank_rows(self):
        """Should omit Company / Email rows when those fields are absent rather than rendering empty cells."""
        _, html = render_lead_assigned_email(
            NOTIF_BRANDING,
            {"lead_full_name": "Solo Lead", "lead_url": "https://crm.example.com/leads/1"},
        )
        assert "Cooper LLC" not in html
        assert "jane@example.com" not in html

    def test_assigner_falls_back_to_company(self):
        """Should use the branding company name when ``assigner_name`` is missing."""
        _, html = render_lead_assigned_email(
            NOTIF_BRANDING,
            {"lead_full_name": "Lead McLead", "lead_url": "https://x"},
        )
        assert "Acme Corp" in html


class TestTaskDueEmail:
    """Renderer for the ``task_due`` matrix event."""

    def test_renders_subject_and_due_card(self):
        """Should name the task in the subject and render the due-at + entity rows."""
        subject, html = render_task_due_email(
            NOTIF_BRANDING,
            {
                "activity_subject": "Follow up on demo",
                "activity_due_at": "Friday, May 8",
                "activity_url": "https://crm.example.com/activities/9",
                "entity_label": "Cooper LLC · Jane",
            },
        )
        assert subject == "Task due — Follow up on demo"
        assert "Follow up on demo" in html
        assert "Friday, May 8" in html
        assert "Cooper LLC" in html
        assert "https://crm.example.com/activities/9" in html
        assert NOTIF_BRANDING["primary_color"] in html


class TestMentionEmail:
    """Renderer for the ``mention`` matrix event."""

    def test_truncates_long_snippet(self):
        """Should cap the comment snippet at 280 chars with a typographic ellipsis."""
        long = "x" * 600
        subject, html = render_mention_email(
            NOTIF_BRANDING,
            {
                "author_name": "Daisy Mentions",
                "entity_label": "Acme - Q3 Renewal",
                "entity_url": "https://crm.example.com/contacts/7",
                "content_snippet": long,
            },
        )
        assert "Daisy Mentions mentioned you" in subject
        assert "Acme - Q3 Renewal" in subject
        assert "Daisy Mentions" in html
        assert "…" in html
        assert "x" * 600 not in html
        assert NOTIF_BRANDING["primary_color"] in html

    def test_html_in_snippet_is_escaped(self):
        """Should escape (not interpret) any HTML in the comment body — defensive against stored XSS."""
        _, html = render_mention_email(
            NOTIF_BRANDING,
            {
                "author_name": "Eve",
                "entity_label": "x",
                "entity_url": "https://x",
                "content_snippet": "<script>alert(1)</script>",
            },
        )
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html


class TestEmailReplyEmail:
    """Renderer for the ``email_reply_received`` matrix event."""

    def test_renders_subject_and_thread_card(self):
        """Should prefix the inbound subject in the email subject and link to the thread view."""
        subject, html = render_email_reply_email(
            NOTIF_BRANDING,
            {
                "sender_email": "client@external.com",
                "sender_name": "Big Client",
                "subject_line": "Re: Proposal questions",
                "snippet": "Looks great — when can we sign?",
                "thread_url": "https://crm.example.com/contacts/7?tab=email",
            },
        )
        assert subject == "Reply received — Re: Proposal questions"
        assert "Big Client" in html
        assert "client@external.com" in html
        assert "Looks great" in html
        assert "https://crm.example.com/contacts/7?tab=email" in html
        assert NOTIF_BRANDING["primary_color"] in html

    def test_missing_subject_line_uses_placeholder(self):
        """Should still render a sensible subject + body when the inbound has no Subject header."""
        subject, html = render_email_reply_email(
            NOTIF_BRANDING,
            {
                "sender_email": "x@y.com",
                "sender_name": "",
                "subject_line": "",
                "snippet": "",
                "thread_url": "https://x",
            },
        )
        assert "(no subject)" in subject
        assert "(no subject)" in html


class TestContractExpiringEmail:
    """Renderer for the ``contract_expiring`` matrix event."""

    def test_renders_days_left_and_company(self):
        """Should put days_left + contract title in the subject and render the contract card."""
        subject, html = render_contract_expiring_email(
            NOTIF_BRANDING,
            {
                "contract_title": "MSA 2026",
                "company_name": "Cooper LLC",
                "end_date": "2026-06-01",
                "days_left": 14,
                "contract_url": "https://crm.example.com/contracts/42",
            },
        )
        assert subject == "Contract expiring in 14 days — MSA 2026"
        assert "MSA 2026" in html
        assert "Cooper LLC" in html
        assert "2026-06-01" in html
        assert "14 day" in html
        assert "https://crm.example.com/contracts/42" in html
        assert NOTIF_BRANDING["primary_color"] in html

    def test_singular_day_pluralization(self):
        """Should say "1 day" not "1 days" when only one day remains."""
        subject, html = render_contract_expiring_email(
            NOTIF_BRANDING,
            {
                "contract_title": "Tight Deal",
                "end_date": "2026-05-08",
                "days_left": 1,
                "contract_url": "https://x",
            },
        )
        assert "1 day —" in subject
        assert "1 day</strong>" in html


class TestContractSignedEmail:
    """Renderer for the ``contract_signed`` matrix event (owner audience) and the always-on signer copy."""

    def test_owner_audience_renders_signed_card(self):
        """Owner-side notification should include signer + signed-at metadata + a CTA back to the contract."""
        subject, html = render_contract_signed_email(
            NOTIF_BRANDING,
            {
                "audience": "owner",
                "contract_title": "MSA 2026",
                "signer_name": "Jane Cooper",
                "signed_at": "May 7, 2026 14:23 UTC",
                "contract_url": "https://crm.example.com/contracts/42",
            },
        )
        assert subject == "Contract signed — MSA 2026"
        assert "Jane Cooper" in html
        assert "May 7, 2026" in html
        assert "https://crm.example.com/contracts/42" in html
        assert NOTIF_BRANDING["primary_color"] in html

    def test_signer_audience_thanks_signer(self):
        """Signer-side copy should be a thank-you with no internal CTA leaked to the external party."""
        subject, html = render_contract_signed_email(
            NOTIF_BRANDING,
            {
                "audience": "signer",
                "contract_title": "MSA 2026",
                "signer_name": "Jane Cooper",
            },
        )
        assert subject == "Signed copy — MSA 2026"
        assert "Thank you for signing" in html
        assert "Jane Cooper" in html
        assert "Open contract" not in html


class TestProposalSignedEmail:
    """Renderer for the ``proposal_signed`` matrix event (owner-side)."""

    def test_renders_owner_notification(self):
        """Should put proposal title + signer + CTA in place and use the tenant primary color."""
        subject, html = render_proposal_signed_email(
            NOTIF_BRANDING,
            {
                "proposal_title": "Q3 Engagement",
                "signer_name": "Jane Cooper",
                "signed_at": "May 7, 2026 14:23 UTC",
                "proposal_url": "https://crm.example.com/proposals/9",
            },
        )
        assert subject == "Proposal signed — Q3 Engagement"
        assert "Q3 Engagement" in html
        assert "Jane Cooper" in html
        assert "https://crm.example.com/proposals/9" in html
        assert "billing" not in html.lower()
        assert "USD" not in html
        assert NOTIF_BRANDING["primary_color"] in html


class TestNotifTemplatesUrlSafety:
    """Defensive scheme allowlist on the new notification templates."""

    def test_javascript_url_in_lead_cta_is_dropped(self):
        """A javascript: lead_url must not survive — XSS defense in depth."""
        _, html = render_lead_assigned_email(
            NOTIF_BRANDING,
            {
                "lead_full_name": "Phisher",
                "lead_url": "javascript:alert(1)",
            },
        )
        assert "javascript:alert" not in html
        assert "Open lead" not in html


class TestSafeHexAtRender:
    """``_safe_hex`` is the render-side guard mirroring the schema validator.

    ``TenantBrandingHelper.get_branding_for_user`` reads straight from the
    ORM, bypassing ``_validate_color_field``. Without this guard a
    pre-validator row, raw-SQL insert, or buggy migration could ship a
    malformed hex into a ``<style>`` block; the email client silently
    drops the rule and the customer sees an unbranded email with no
    diagnostic trace.
    """

    def test_safe_hex_accepts_valid_hex(self):
        from src.email.branded_templates import _safe_hex
        assert _safe_hex("#abc", "#000000") == "#abc"
        assert _safe_hex("#abcdef", "#000000") == "#abcdef"
        assert _safe_hex("  #abcdef  ", "#000000") == "#abcdef"

    def test_safe_hex_rejects_garbage(self):
        from src.email.branded_templates import _safe_hex
        fallback = "#000000"
        # Strings that "look like colors" but aren't valid hex.
        assert _safe_hex("red", fallback) == fallback
        assert _safe_hex("#zzz", fallback) == fallback
        assert _safe_hex("#12345", fallback) == fallback
        # 8-digit form is rejected to mirror the schema validator (DB
        # column is VARCHAR(7) — see PR #263 second-pass review).
        assert _safe_hex("#aabbccdd", fallback) == fallback
        # Empty / whitespace / None / non-string.
        assert _safe_hex("", fallback) == fallback
        assert _safe_hex("   ", fallback) == fallback
        assert _safe_hex(None, fallback) == fallback

    def test_safe_hex_logs_on_fallback(self, caplog):
        """A corrupt-row fallback must surface in logs so Sentry catches it."""
        import logging

        from src.email.branded_templates import _safe_hex

        with caplog.at_level(logging.WARNING, logger="src.email.branded_templates"):
            result = _safe_hex("not-a-hex", "#fallback", field="primary_color")

        assert result == "#fallback"
        assert any(
            "primary_color" in r.message and "not-a-hex" in r.message
            for r in caplog.records
        ), f"Expected warning naming the field + bad value, got: {[r.message for r in caplog.records]}"

    def test_safe_hex_silent_on_empty_or_none(self, caplog):
        """Empty / None aren't logged — those just mean 'use the default'."""
        import logging

        from src.email.branded_templates import _safe_hex

        with caplog.at_level(logging.WARNING, logger="src.email.branded_templates"):
            _safe_hex("", "#fallback")
            _safe_hex(None, "#fallback")

        assert len(caplog.records) == 0, (
            f"Expected no warnings for empty/None, got: {[r.message for r in caplog.records]}"
        )

    def test_email_template_drops_garbage_colors(self):
        """Render path must not echo malformed hex into the inline CSS.

        ``_base_email_html`` directly emits primary, secondary, bg_light,
        and surface_light into inline CSS; accent is consumed by the
        wrapping templates (campaign / receipt / etc.) and isn't always
        present in the base render — covered by the per-template tests
        above. We only assert here on the four colors the base shell
        always emits.
        """
        bad_branding = {
            "company_name": "Test",
            "primary_color": "javascript:alert(1)",
            "secondary_color": "#zzz",
            "accent_color": "red",
            "bg_color_light": "not-a-color",
            "surface_color_light": "#12345",
        }
        html = render_branded_email(
            bad_branding,
            "Subject",
            "Headline",
            "<p>Body</p>",
        )
        # None of the garbage values reach the rendered HTML.
        assert "javascript:alert" not in html
        assert "#zzz" not in html
        assert "not-a-color" not in html
        assert "#12345" not in html
        # Documented defaults take over for each rejected field that
        # the base shell renders. PR #325 palette swap: primary is the
        # gold spotlight (#CF982C); accent is black. secondary_color
        # is unused by the email wrapper post-swap so don't assert it.
        assert "#CF982C" in html  # primary fallback
        assert "#000000" in html  # accent fallback (used by CTA + wordmark rest)
        assert "#f9fafb" in html  # bg_color_light fallback
        assert "#ffffff" in html  # surface_color_light fallback


# ---------------------------------------------------------------------------
# Visual contract (PR #325 — Link Creative wrapper redesign)
# ---------------------------------------------------------------------------


_HEADER_WITH_LOGO_BRANDING = {
    **NOTIF_BRANDING,
    "logo_url": "https://example.com/logo.png",
}

_NO_LOGO_BRANDING = {**NOTIF_BRANDING, "logo_url": ""}


class TestHeaderLogoBlock:
    """PR #325 redesign: header is white surface; logo renders bare and centered.

    The legacy "white pill table at width=224 around a 200x40 logo" pattern
    was the right answer for the dark-block header it lived inside — that
    header is gone. The new header surface is already white so a white pill
    around a white logo wouldn't help; the redesign drops the pill and
    centers the bare image instead.
    """

    def test_logo_renders_as_centered_img_when_url_set(self):
        html = render_branded_email(
            _HEADER_WITH_LOGO_BRANDING, "s", "h", "<p>b</p>"
        )
        assert 'src="https://example.com/logo.png"' in html
        # Centered text-align on the surrounding header cell is the
        # visual contract for the redesigned wrapper.
        assert "text-align:center" in html

    def test_no_logo_falls_back_to_wordmark(self):
        """When no logo URL, the wrapper renders the company name as a
        styled wordmark fallback so the header doesn't collapse."""
        html = render_branded_email(_NO_LOGO_BRANDING, "s", "h", "<p>b</p>")
        # No <img> with the legacy logo URL.
        assert 'src="https://example.com/logo.png"' not in html
        # Wordmark fallback emits the company_name uppercase in a
        # styled <span>. NOTIF_BRANDING.company_name is "Acme Corp".
        assert "Acme" in html
        assert "Corp" in html

    def test_legacy_white_pill_chrome_is_gone(self):
        """Round 1 + 2 fixups deleted the white pill wrapper table; ensure
        it stays gone so regressions surface immediately."""
        html = render_branded_email(_HEADER_WITH_LOGO_BRANDING, "s", "h", "<p>b</p>")
        assert "background-color:#ffffff;border-radius:6px;" not in html
        assert 'width="224"' not in html


class TestHeaderBodyPadding:
    """Header and body padding for the redesigned wrapper.

    The new white-surface header uses asymmetric vertical padding
    (32px top, 20px bottom) to seat the wordmark + tagline + accent
    rule comfortably. The body card keeps the 32px symmetric padding
    that was already documented.
    """

    def test_header_uses_redesigned_padding(self):
        html = render_branded_email(_NO_LOGO_BRANDING, "s", "h", "<p>b</p>")
        # Bottom padding shrunk vs. the legacy 24/32 to fit the
        # tagline + 3px gold rule below the wordmark.
        assert "padding:32px 32px 20px;" in html
        assert "border-radius:8px 8px 0 0;" in html

    def test_body_padding_32_32(self):
        """Body card td uses padding:32px 32px."""
        html = render_branded_email(_NO_LOGO_BRANDING, "s", "h", "<p>b</p>")
        assert "padding:32px 32px;" in html


class TestSubjectInlineLabel:
    """Subject line must render as a single inline paragraph, not two separate <p> tags."""

    def test_subject_rendered_inline(self):
        """The old two-<p> Subject pattern must not appear; new inline <strong>Subject:</strong> must."""
        _, html = render_email_reply_email(
            _NO_LOGO_BRANDING,
            {
                "sender_email": "client@example.com",
                "subject_line": "Re: Proposal",
                "snippet": "Looks good.",
            },
        )
        assert '<p style="margin:0 0 8px;font-size:14px;color:#6b7280;">Subject</p>' not in html
        assert '<strong style="color:#6b7280;">Subject:</strong>' in html
        assert "Re: Proposal" in html

    def test_subject_label_and_value_in_same_paragraph(self):
        """Label and value must share a single <p> with no </p><p> between them."""
        _, html = render_email_reply_email(
            _NO_LOGO_BRANDING,
            {
                "sender_email": "a@b.com",
                "subject_line": "Hello from client",
                "snippet": "",
            },
        )
        idx_label = html.index("Subject:")
        idx_value = html.index("Hello from client")
        assert "</p>" not in html[idx_label:idx_value]
