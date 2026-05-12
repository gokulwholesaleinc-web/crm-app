"""Unit tests for email template tone + visual rewrites.

Tests render each template function and assert on key substrings so that
tone changes, color defaults, and the contract send helper are all verified
without standing up a database.
"""
from __future__ import annotations

from src.email.branded_templates import (
    _DEFAULT_BRANDING,
    _base_email_html,
    render_contract_send_email,
    render_lead_assigned_email,
    render_payment_receipt_email,
    render_proposal_email,
    render_task_due_email,
)


def _default_branding(**overrides: str) -> dict:
    b = dict(_DEFAULT_BRANDING)
    b.update(overrides)
    return b


# ---------------------------------------------------------------------------
# Visual defaults
# ---------------------------------------------------------------------------

class TestVisualDefaults:
    def test_agency_palette_primary(self):
        assert _DEFAULT_BRANDING["primary_color"] == "#1e293b"

    def test_agency_palette_accent(self):
        assert _DEFAULT_BRANDING["accent_color"] == "#0ea5e9"

    def test_agency_palette_secondary(self):
        assert _DEFAULT_BRANDING["secondary_color"] == "#0ea5e9"

    def test_system_font_stack_in_body(self):
        html = _base_email_html(_default_branding(), "Test", "<p>hello</p>")
        assert "-apple-system" in html
        assert "BlinkMacSystemFont" in html

    def test_cta_pill_border_radius(self):
        html = _base_email_html(
            _default_branding(), "Test", "<p>body</p>",
            cta_text="Click me", cta_url="https://example.com/sign",
        )
        assert "border-radius:24px" in html

    def test_cta_uppercase_letter_spacing(self):
        html = _base_email_html(
            _default_branding(), "Test", "<p>body</p>",
            cta_text="Sign Now", cta_url="https://example.com/sign",
        )
        assert "text-transform:uppercase" in html
        assert "letter-spacing:0.5px" in html

    def test_sender_title_renders_when_set(self):
        html = _base_email_html(
            _default_branding(), "Test", "<p>body</p>",
            sender_title="Senior Account Manager",
        )
        assert "Senior Account Manager" in html

    def test_sender_title_absent_when_not_set(self):
        html = _base_email_html(_default_branding(), "Test", "<p>body</p>")
        assert "sender_title" not in html

    def test_tenant_primary_color_overrides_default(self):
        branding = _default_branding(primary_color="#ff0000")
        html = _base_email_html(branding, "Test", "<p>body</p>")
        assert "#ff0000" in html
        assert "#1e293b" not in html


# ---------------------------------------------------------------------------
# Tone: proposal email
# ---------------------------------------------------------------------------

class TestProposalEmailTone:
    def test_hi_greeting(self):
        _, html = render_proposal_email(
            _default_branding(),
            {"proposal_title": "Q3 Campaign", "client_name": "Alex", "summary": "s", "total": "5000", "currency": "USD"},
        )
        assert "Hi Alex" in html

    def test_no_dear_greeting(self):
        _, html = render_proposal_email(
            _default_branding(),
            {"proposal_title": "Q3 Campaign", "client_name": "Alex", "summary": "s", "total": "5000", "currency": "USD"},
        )
        assert "Dear Alex" not in html

    def test_ready_to_move_forward_copy(self):
        _, html = render_proposal_email(
            _default_branding(),
            {"proposal_title": "Q3 Campaign", "client_name": "Alex", "summary": "s", "total": "5000", "currency": "USD"},
        )
        assert "Ready to move forward" in html

    def test_no_we_look_forward(self):
        _, html = render_proposal_email(
            _default_branding(),
            {"proposal_title": "Q3 Campaign", "client_name": "Alex", "summary": "s", "total": "5000", "currency": "USD"},
        )
        assert "We look forward to discussing" not in html


# ---------------------------------------------------------------------------
# Tone: payment receipt
# ---------------------------------------------------------------------------

class TestPaymentReceiptTone:
    def test_hi_greeting(self):
        _, html = render_payment_receipt_email(
            _default_branding(),
            {"receipt_number": "INV-001", "client_name": "Jo", "amount": "500", "currency": "USD",
             "payment_date": "2026-05-11", "payment_method": "Card"},
        )
        assert "Hi Jo" in html

    def test_invoice_processed_copy(self):
        _, html = render_payment_receipt_email(
            _default_branding(),
            {"receipt_number": "INV-001", "client_name": "Jo", "amount": "500", "currency": "USD",
             "payment_date": "2026-05-11", "payment_method": "Card"},
        )
        assert "INV-001 has been processed" in html

    def test_questions_about_invoice_copy(self):
        _, html = render_payment_receipt_email(
            _default_branding(),
            {"receipt_number": "INV-001", "client_name": "Jo", "amount": "500", "currency": "USD",
             "payment_date": "2026-05-11", "payment_method": "Card"},
        )
        assert "Questions about this invoice" in html

    def test_no_thank_you_for_payment(self):
        _, html = render_payment_receipt_email(
            _default_branding(),
            {"receipt_number": "INV-001", "client_name": "Jo", "amount": "500", "currency": "USD",
             "payment_date": "2026-05-11", "payment_method": "Card"},
        )
        assert "Thank you for your payment. Here is your receipt" not in html


# ---------------------------------------------------------------------------
# Tone: task due
# ---------------------------------------------------------------------------

class TestTaskDueTone:
    def test_activity_subject_in_intro(self):
        _, html = render_task_due_email(
            _default_branding(),
            {"activity_subject": "Follow-up call", "activity_due_at": "May 12 at 2pm",
             "activity_url": "https://example.com/tasks/1"},
        )
        assert "Follow-up call" in html
        assert "May 12 at 2pm" in html

    def test_jump_in_copy(self):
        _, html = render_task_due_email(
            _default_branding(),
            {"activity_subject": "Follow-up call", "activity_due_at": "May 12 at 2pm"},
        )
        assert "Jump in to complete or reschedule" in html

    def test_no_generic_task_coming_due_copy(self):
        _, html = render_task_due_email(
            _default_branding(),
            {"activity_subject": "Follow-up call", "activity_due_at": "May 12 at 2pm"},
        )
        assert "You have a task coming due in your CRM" not in html


# ---------------------------------------------------------------------------
# Tone: lead assigned
# ---------------------------------------------------------------------------

class TestLeadAssignedTone:
    def test_assigned_you_copy(self):
        _, html = render_lead_assigned_email(
            _default_branding(),
            {"lead_full_name": "Sara Lee", "lead_url": "https://example.com/leads/5",
             "assigner_name": "Mike"},
        )
        assert "Mike assigned you a new lead" in html
        assert "Sara Lee" in html

    def test_first_step_outreach_copy(self):
        _, html = render_lead_assigned_email(
            _default_branding(),
            {"lead_full_name": "Sara Lee", "lead_url": "https://example.com/leads/5",
             "assigner_name": "Mike"},
        )
        assert "First step" in html

    def test_no_old_copy(self):
        _, html = render_lead_assigned_email(
            _default_branding(),
            {"lead_full_name": "Sara Lee", "lead_url": "https://example.com/leads/5",
             "assigner_name": "Mike"},
        )
        assert "Open the lead to add an activity, qualify it, or hand it off" not in html


# ---------------------------------------------------------------------------
# Contract send email (new helper)
# ---------------------------------------------------------------------------

class TestRenderContractSendEmail:
    def test_subject_format(self):
        subject, _ = render_contract_send_email(
            _default_branding(),
            contract_title="Agency Services Agreement",
            client_first_name="Dana",
            sign_url="https://example.com/contracts/sign/abc123",
        )
        assert subject == "Contract for signature — Agency Services Agreement"

    def test_hi_greeting(self):
        _, html = render_contract_send_email(
            _default_branding(),
            contract_title="Agency Services Agreement",
            client_first_name="Dana",
            sign_url="https://example.com/contracts/sign/abc123",
        )
        assert "Hi Dana" in html

    def test_contract_title_in_body(self):
        _, html = render_contract_send_email(
            _default_branding(),
            contract_title="Agency Services Agreement",
            client_first_name="Dana",
            sign_url="https://example.com/contracts/sign/abc123",
        )
        assert "Agency Services Agreement" in html

    def test_seven_day_validity_copy(self):
        _, html = render_contract_send_email(
            _default_branding(),
            contract_title="Agency Services Agreement",
            client_first_name="Dana",
            sign_url="https://example.com/contracts/sign/abc123",
        )
        assert "valid for 7 days" in html

    def test_reply_questions_copy(self):
        _, html = render_contract_send_email(
            _default_branding(),
            contract_title="Agency Services Agreement",
            client_first_name="Dana",
            sign_url="https://example.com/contracts/sign/abc123",
        )
        assert "Questions? Reply to this email" in html

    def test_cta_button_present(self):
        _, html = render_contract_send_email(
            _default_branding(),
            contract_title="Agency Services Agreement",
            client_first_name="Dana",
            sign_url="https://example.com/contracts/sign/abc123",
        )
        assert "Review &amp; Sign" in html or "Review & Sign" in html
        assert "contracts/sign/abc123" in html

    def test_optional_message_included(self):
        _, html = render_contract_send_email(
            _default_branding(),
            contract_title="Agency Services Agreement",
            client_first_name="Dana",
            sign_url="https://example.com/contracts/sign/abc123",
            message="Please review at your earliest convenience.",
        )
        assert "Please review at your earliest convenience" in html

    def test_fallback_greeting_without_name(self):
        _, html = render_contract_send_email(
            _default_branding(),
            contract_title="Agency Services Agreement",
            client_first_name="",
            sign_url="https://example.com/contracts/sign/abc123",
        )
        assert "Hi there" in html

    def test_renders_as_branded_html(self):
        _, html = render_contract_send_email(
            _default_branding(company_name="Link Creative"),
            contract_title="Agency Services Agreement",
            client_first_name="Dana",
            sign_url="https://example.com/contracts/sign/abc123",
        )
        assert "Link Creative" in html
        assert "<!DOCTYPE html>" in html

    def test_unsafe_sign_url_rejected(self):
        """javascript: URLs must not appear in the rendered CTA."""
        _, html = render_contract_send_email(
            _default_branding(),
            contract_title="Test",
            client_first_name="A",
            sign_url="javascript:alert(1)",
        )
        assert "javascript:" not in html
