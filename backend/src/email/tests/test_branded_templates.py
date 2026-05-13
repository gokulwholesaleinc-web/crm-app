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
    # The CRM is single-tenant by design and ships with the Link
    # Creative gold/black palette baked in as defaults so emails render
    # correctly even before an admin opens the branding form. Tenants
    # that customize colors still override these via TenantSettings.
    def test_link_creative_palette_primary_is_black(self):
        assert _DEFAULT_BRANDING["primary_color"] == "#000000"

    def test_link_creative_palette_accent_is_gold(self):
        assert _DEFAULT_BRANDING["accent_color"] == "#c5a467"

    def test_link_creative_palette_secondary_is_gold(self):
        assert _DEFAULT_BRANDING["secondary_color"] == "#c5a467"

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
        # No production caller passes sender info today, but the API
        # surface kept the kwargs so back-compat is intact. When nothing
        # is set the entire attribution block must collapse — including
        # the wrapper class — so the body doesn't grow a stray empty div.
        html = _base_email_html(_default_branding(), "Test", "<p>body</p>")
        assert "sender_title" not in html
        assert "email-sender-attribution" not in html
        assert "email-sender-title" not in html

    # -- Header layout: centered logo + tagline + gold rule ---------------

    def test_centered_header_uses_company_name_when_no_logo(self):
        # No logo configured: the company name renders as a wordmark
        # fallback in the centered header so the email still has brand
        # presence.
        html = _base_email_html(
            _default_branding(company_name="Link Creative"),
            "Test",
            "<p>body</p>",
        )
        assert "Link Creative" in html
        # Centered text-align is the visual contract.
        assert "text-align:center" in html

    def test_logo_renders_as_image_when_configured(self):
        html = _base_email_html(
            _default_branding(
                company_name="Link Creative",
                logo_url="https://example.com/logo.png",
            ),
            "Test",
            "<p>body</p>",
        )
        assert 'src="https://example.com/logo.png"' in html
        assert 'alt="Link Creative"' in html

    def test_tagline_renders_with_gold_pipe_separators(self):
        html = _base_email_html(
            _default_branding(
                tagline="ACCESSIBLE MEDIA | AUTHENTIC STORYTELLING | REAL RESULTS",
            ),
            "Test",
            "<p>body</p>",
        )
        assert "ACCESSIBLE MEDIA" in html
        assert "AUTHENTIC STORYTELLING" in html
        assert "REAL RESULTS" in html
        # Pipes recolored to the secondary (gold) accent, not left as
        # plain text "|".
        assert "color:#c5a467;font-weight:700" in html

    def test_tagline_block_absent_when_unset(self):
        # The mobile media query references `.email-tagline` whether
        # or not a tagline is present, so check for the rendered div
        # itself rather than the bare class string.
        html = _base_email_html(_default_branding(), "Test", "<p>body</p>")
        assert 'class="email-tagline"' not in html

    def test_tagline_collapses_empty_pipe_segments(self):
        # Doubled or trailing pipes must not emit phantom dividers; the
        # rendered tagline should only carry separators between non-empty
        # segments.
        html = _base_email_html(
            _default_branding(tagline="ONE ||  | TWO |"),
            "Test",
            "<p>body</p>",
        )
        assert "ONE" in html
        assert "TWO" in html
        # Exactly one separator span between the two real segments.
        assert html.count('color:#c5a467;font-weight:700;padding:0 6px') == 1

    def test_gold_accent_rule_below_header(self):
        # The 3px gold strip under the header is part of the visual
        # contract — its presence is what differentiates this wrapper
        # from the legacy dark-block header.
        html = _base_email_html(
            _default_branding(secondary_color="#c5a467"),
            "Test",
            "<p>body</p>",
        )
        assert "background-color:#c5a467" in html
        assert "height:3px" in html

    # -- Footer: dark surface + social row + legal links ------------------

    def test_footer_uses_near_black_surface(self):
        html = _base_email_html(_default_branding(), "Test", "<p>body</p>")
        assert "background-color:#0a0a0a" in html

    def test_social_row_renders_only_configured_platforms(self):
        html = _base_email_html(
            _default_branding(
                social_facebook_url="https://facebook.com/foo",
                social_linkedin_url="https://linkedin.com/company/foo",
            ),
            "Test",
            "<p>body</p>",
        )
        # KEEP UP heading appears because at least one platform is set.
        assert "KEEP UP WITH US ON SOCIAL" in html
        # Configured platforms emit anchored circles.
        assert 'href="https://facebook.com/foo"' in html
        assert 'href="https://linkedin.com/company/foo"' in html
        assert 'aria-label="Facebook"' in html
        assert 'aria-label="LinkedIn"' in html
        # Unconfigured platforms render nothing.
        assert "instagram.com" not in html
        assert "tiktok.com" not in html
        assert "youtube.com" not in html
        assert 'aria-label="Instagram"' not in html

    def test_social_row_omitted_when_no_platforms_configured(self):
        # The "KEEP UP WITH US ON SOCIAL" heading is gated behind at
        # least one configured platform so tenants that haven't filled
        # any social URLs in don't get a stranded heading above an
        # empty row.
        html = _base_email_html(_default_branding(), "Test", "<p>body</p>")
        assert "KEEP UP WITH US ON SOCIAL" not in html

    def test_social_url_with_unsafe_scheme_is_dropped(self):
        # javascript:/data:/vbscript: schemes must never reach an
        # ``href`` attribute even when stored in the database.
        html = _base_email_html(
            _default_branding(
                social_facebook_url="javascript:alert(1)",
                social_instagram_url="https://instagram.com/ok",
            ),
            "Test",
            "<p>body</p>",
        )
        assert "javascript:" not in html
        assert 'aria-label="Facebook"' not in html
        # Tighten: the safe URL still renders so we know the row
        # wasn't collapsed for an unrelated reason.
        assert 'aria-label="Instagram"' in html
        assert "instagram.com/ok" in html

    def test_social_url_strict_rejects_mailto_and_relative(self):
        # _safe_url permits ``mailto:`` and site-relative paths for the
        # campaign unsubscribe surface; social footer cells must be
        # external http(s) only or a recipient clicking a "Facebook"
        # circle could land on /admin/internal or pop a compose window.
        html = _base_email_html(
            _default_branding(
                social_facebook_url="mailto:owner@example.com",
                social_instagram_url="/admin/internal",
                social_tiktok_url="https://tiktok.com/@ok",
            ),
            "Test",
            "<p>body</p>",
        )
        assert "mailto:" not in html
        assert "/admin/internal" not in html
        assert 'aria-label="Facebook"' not in html
        assert 'aria-label="Instagram"' not in html
        assert 'aria-label="TikTok"' in html

    def test_social_row_omitted_when_all_urls_unsafe(self):
        # If every configured URL fails the allowlist, the entire
        # "KEEP UP WITH US ON SOCIAL" block must collapse rather than
        # render an empty row beneath a stranded heading.
        html = _base_email_html(
            _default_branding(
                social_facebook_url="javascript:alert(1)",
                social_instagram_url="mailto:x@y",
                social_tiktok_url="/relative",
            ),
            "Test",
            "<p>body</p>",
        )
        assert "KEEP UP WITH US ON SOCIAL" not in html

    def test_footer_legal_links_render_white_on_dark(self):
        html = _base_email_html(
            _default_branding(
                privacy_policy_url="https://example.com/privacy",
                terms_of_service_url="https://example.com/terms",
            ),
            "Test",
            "<p>body</p>",
        )
        assert "Privacy Policy" in html
        assert "Terms of Service" in html
        # Light gray legible against the dark footer.
        assert "color:#e5e7eb;text-decoration:underline" in html

    # -- Responsive: mobile media query -----------------------------------

    def test_mobile_media_query_present(self):
        html = _base_email_html(_default_branding(), "Test", "<p>body</p>")
        assert "@media only screen and (max-width:480px)" in html

    def test_mobile_media_query_scales_tagline(self):
        html = _base_email_html(_default_branding(), "Test", "<p>body</p>")
        assert ".email-tagline{font-size:11px!important" in html

    def test_mobile_media_query_full_width_cta(self):
        html = _base_email_html(
            _default_branding(), "Test", "<p>body</p>",
            cta_text="Sign", cta_url="https://example.com/sign",
        )
        assert ".email-cta-wrap{width:100%!important" in html
        assert ".email-cta-link{display:block!important" in html
        assert 'class="email-cta-wrap"' in html
        assert 'class="email-cta-link"' in html

    def test_mobile_media_query_scales_headline_and_body(self):
        html = _base_email_html(_default_branding(), "Test", "<p>body</p>")
        assert ".email-headline{font-size:19px!important" in html
        assert ".email-text{font-size:14px!important" in html

    def test_dark_mode_media_query_still_present(self):
        # Existing dark-mode support is preserved.
        html = _base_email_html(_default_branding(), "Test", "<p>body</p>")
        assert "@media (prefers-color-scheme:dark)" in html

    def test_responsive_class_hooks_on_outer_cells(self):
        # Layout cells get class hooks so the mobile media query can
        # override paddings without fighting per-element inline styles.
        html = _base_email_html(_default_branding(), "Test", "<p>body</p>")
        assert 'class="email-outer-cell"' in html
        assert 'class="email-header-cell"' in html
        assert 'class="email-body-cell"' in html
        assert 'class="email-footer-cell"' in html

    # -- Sender attribution (back-compat API) -----------------------------

    def test_sender_block_renders_above_body(self):
        # Old two-column header is gone; sender_name/sender_title now
        # surface as a small caption above the body headline so the
        # back-compat API still has a visible effect.
        html = _base_email_html(
            _default_branding(), "Headline", "<p>body</p>",
            sender_name="Jane Smith",
            sender_title="Senior Account Manager",
        )
        attribution_start = html.find('class="email-sender-attribution"')
        assert attribution_start != -1
        body_h1 = html.find("<h1", attribution_start)
        assert body_h1 != -1
        attribution = html[attribution_start:body_h1]
        assert "Jane Smith" in attribution
        assert "Senior Account Manager" in attribution

    def test_sender_block_whitespace_treated_as_absent(self):
        html = _base_email_html(
            _default_branding(), "Test", "<p>body</p>",
            sender_name="   ", sender_title="\t",
        )
        assert "email-sender-attribution" not in html

    def test_render_branded_email_plumbs_sender_name(self):
        from src.email.branded_templates import render_branded_email
        html = render_branded_email(
            _default_branding(), "Subject", "Headline", "<p>body</p>",
            sender_name="Jane Smith", sender_title="AE",
        )
        attribution_start = html.find('class="email-sender-attribution"')
        assert attribution_start != -1
        # Both fields appear inside the attribution block.
        body_h1 = html.find("<h1", attribution_start)
        attribution = html[attribution_start:body_h1]
        assert "Jane Smith" in attribution
        assert "AE" in attribution

    def test_tenant_primary_color_overrides_default(self):
        branding = _default_branding(primary_color="#ff0000")
        html = _base_email_html(branding, "Test", "<p>body</p>")
        assert "#ff0000" in html
        # The new wrapper uses ``primary_color`` for tagline copy and
        # the no-logo wordmark fallback; the old hardcoded #1e293b
        # default must not leak through.
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
