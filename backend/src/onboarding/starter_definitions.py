"""Built-in onboarding "starter" template definitions — the single source of
truth for Lorenzo's 6 Google Forms rebuilt as onboarding templates (P4).

These are reusable, in-code definitions: the seed UPSERTs them into the DB
(``seed.py`` imports ``onboarding_template_specs`` from here), the
``GET /templates/starters`` endpoint lists them, and the wizard's
``POST /templates/from-starter`` clones one into a fresh template. Keeping the
definitions HERE (one source) means the seed and the wizard never diverge.

Each starter carries a stable ``key`` (a hyphen slug used by from-starter), a
deterministic human-readable ``name`` (the seed UPSERTs by name — a rename
orphans the old row; ``test_seed_is_idempotent`` guards it), a ``kind``
∈ {``questionnaire``, ``upload_request``}, an optional ``service_tag``, a
``description``, and the kind's ``field_definitions`` (wire-valid by
construction — every kind's ``validate_definitions`` accepts them; the matrix
test in ``tests/unit/test_onboarding_seed.py`` proves it).

The two ``upload-gated`` forms (1, 3) split into a ``questionnaire`` doc + an
``upload_request`` doc because the questionnaire kind does not accept
``file_upload`` (§B.3). Eight starters total.

service_tag decisions (§C.1 — null = universal/always-offered):
  * Forms 1/2/3 (admin info, identity, strategy, branding, brand assets) →
    ``None`` (universal onboarding every client gets).
  * Form 4 "Website Onboarding Form"          → ``service_tag="website"``.
  * Form 5 "Link Label Studios — Podcast"      → ``service_tag="podcast"``.
  * Form 6 "Link Live — Guest Intake"          → ``service_tag="link-live"``.
These slugs match ``schemas._SERVICE_TAG_RE`` (lowercase alphanumeric + hyphen);
underscores are NOT allowed there, so ``link_live`` would be rejected by the API
slug validator — it is written as ``link-live`` below.
"""

from __future__ import annotations


# --------------------------------------------------------------------------
# Field-builder helpers — keep each form definition declarative + readable.
# --------------------------------------------------------------------------
def _q(
    fid: str,
    kind: str,
    label: str,
    order: int,
    *,
    required: bool = True,
    section_id: str | None = None,
    section_label: str | None = None,
    help: str | None = None,
    options: list[dict] | None = None,
    allow_other: bool = False,
    display: str | None = None,
    max_length: int | None = None,
    prefill: str | None = None,
    sensitive: bool = False,
) -> dict:
    """One questionnaire field dict (only non-default keys are emitted).

    Mirrors the LOCKED flat field shape the questionnaire handler validates:
    ``{id, kind, label, required, order, section_id?, section_label?, help?,
    options?, allow_other?, display?, maxLength?, prefill?, sensitive?}``.
    """
    field: dict = {"id": fid, "kind": kind, "label": label, "required": required,
                   "order": order}
    if section_id is not None:
        field["section_id"] = section_id
    if section_label is not None:
        field["section_label"] = section_label
    if help is not None:
        field["help"] = help
    if options is not None:
        field["options"] = options
    if allow_other:
        field["allow_other"] = True
    if display is not None:
        field["display"] = display
    if max_length is not None:
        field["maxLength"] = max_length
    if prefill is not None:
        field["prefill"] = prefill
    if sensitive:
        field["sensitive"] = True
    return field


def _upload(
    fid: str,
    label: str,
    order: int,
    *,
    required: bool,
    max_files: int,
    max_mb: int,
    section_id: str | None = None,
    section_label: str | None = None,
    sensitive: bool = False,
    help: str | None = None,
) -> dict:
    """One ``file_upload`` field dict for an ``upload_request`` template."""
    field: dict = {
        "id": fid,
        "kind": "file_upload",
        "label": label,
        "required": required,
        "order": order,
        "maxFiles": max_files,
        "maxMB": max_mb,
    }
    if section_id is not None:
        field["section_id"] = section_id
    if section_label is not None:
        field["section_label"] = section_label
    if sensitive:
        field["sensitive"] = True
    if help is not None:
        field["help"] = help
    return field


def _opts(*labels: str) -> list[dict]:
    """``("2-10", "11-50")`` → ``[{value,label}]`` with slugified values.

    The stored answer is always the option ``value`` (a stable slug); the
    ``label`` is presentation-only and freely re-editable without orphaning a
    stored answer (§7.4).
    """
    out: list[dict] = []
    for label in labels:
        value = _slugify_option(label)
        out.append({"value": value, "label": label})
    return out


def _slugify_option(label: str) -> str:
    """A stable, slug-safe option value derived from a human label.

    Lowercased, non-alphanumerics collapsed to a single underscore, trimmed.
    Matches ``^[a-z0-9_]+$`` (no leading/trailing underscore) so it never
    collides with the reserved ``__other__`` token nor trips the option-value
    validation.
    """
    chars: list[str] = []
    prev_us = False
    for ch in label.lower():
        if ch.isalnum():
            chars.append(ch)
            prev_us = False
        elif not prev_us:
            chars.append("_")
            prev_us = True
    return "".join(chars).strip("_") or "option"


# --------------------------------------------------------------------------
# Reusable option sets.
# --------------------------------------------------------------------------
_WEEKDAYS = _opts("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
_ALL_DAYS = _opts(
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
)
_TIMES_MORN_AFT = _opts("Morning", "Afternoon")
_BUSINESS_SIZE = _opts("2-10", "11-50", "51-100", "100+")


# --------------------------------------------------------------------------
# The 8 starter definitions (the 2 mixed forms split into Q + upload docs).
# --------------------------------------------------------------------------
def _form1_admin_questionnaire() -> dict:
    """Form 1 (non-upload questions) — "Administrative Information"."""
    company = "Company Details"
    contacts = "Contacts"
    comms = "Comms"
    fields = [
        _q("legal_business_name", "short_text", "Legal Business Name", 1,
           section_id="company", section_label=company, prefill="company.name"),
        _q("mailing_address", "short_text", "Mailing / Billing Address", 2,
           section_id="company", section_label=company),
        _q("industry_sector", "short_text", "Industry Sector", 3,
           section_id="company", section_label=company),
        _q("business_size", "single_choice", "Business Size", 4,
           section_id="company", section_label=company, options=_BUSINESS_SIZE),
        _q("year_founded", "short_text", "Year business was founded", 5,
           section_id="company", section_label=company),
        # Form 1 Q7 — composite Primary Contact split into 4 ordered fields
        # under one section (§A.6); the *_email field is kind=email.
        _q("primary_contact_name", "short_text", "Primary Contact — Name", 6,
           section_id="contacts", section_label=contacts, prefill="contact.name"),
        _q("primary_contact_title", "short_text", "Primary Contact — Title", 7,
           section_id="contacts", section_label=contacts),
        _q("primary_contact_email", "email", "Primary Contact — Email", 8,
           section_id="contacts", section_label=contacts),
        _q("primary_contact_phone", "short_text", "Primary Contact — Phone", 9,
           section_id="contacts", section_label=contacts),
        # Form 1 Q8 — Additional Contact (optional) split the same way.
        _q("additional_contact_name", "short_text",
           "Additional Contact — Name", 10, required=False,
           section_id="contacts", section_label=contacts),
        _q("additional_contact_title", "short_text",
           "Additional Contact — Title", 11, required=False,
           section_id="contacts", section_label=contacts),
        _q("additional_contact_email", "email",
           "Additional Contact — Email", 12, required=False,
           section_id="contacts", section_label=contacts),
        _q("additional_contact_phone", "short_text",
           "Additional Contact — Phone", 13, required=False,
           section_id="contacts", section_label=contacts),
        _q("availability_days", "multi_choice",
           "Preferred Availability Days", 14,
           section_id="comms", section_label=comms, options=_WEEKDAYS),
        _q("availability_times", "multi_choice",
           "Preferred Availability Times", 15,
           section_id="comms", section_label=comms, options=_TIMES_MORN_AFT),
        _q("awards", "short_text", "Any awards or nominations held", 16,
           section_id="comms", section_label=comms),
        _q("upcoming_dates", "short_text",
           "Special / important upcoming dates", 17, required=False,
           section_id="comms", section_label=comms),
    ]
    return {
        "key": "admin-information",
        "name": "Client Onboarding: Administrative Information",
        "description": "Company details, contacts, and communication "
                       "preferences (Form 1 — questionnaire portion).",
        "service_tag": None,
        "kind": "questionnaire",
        "field_definitions": fields,
    }


def _form1_identity_upload() -> dict:
    """Form 1 (upload question) — gov-ID identity verification."""
    fields = [
        _upload(
            "government_id", "Government-issued ID (driver's license / state ID, "
            "front only)", 1, required=True, max_files=1, max_mb=10,
            sensitive=True,
            help="A clear photo of the front of your driver's license or "
                 "state ID. Stored securely.",
        ),
    ]
    return {
        "key": "identity-verification",
        "name": "Client Onboarding: Identity Verification",
        "description": "Government-issued ID upload (Form 1 — identity "
                       "verification). Sensitive PII.",
        "service_tag": None,
        "kind": "upload_request",
        "field_definitions": fields,
    }


def _form2_strategy() -> dict:
    """Form 2 — "Client Strategy Insights" (18 questions, no uploads)."""
    fields = [
        _q("client_name", "short_text", "Client Name", 1, prefill="contact.name"),
        _q("past_strategies", "multi_choice",
           "Past marketing strategies / channels used", 2, allow_other=True,
           options=_opts(
               "Organic Social", "Email", "SEO", "Paid Ads", "OOH",
               "Direct Mail", "Content", "GEO", "Influencer/UGC")),
        _q("what_worked", "paragraph", "What has worked well previously", 3),
        _q("what_didnt_work", "paragraph",
           "What hasn't produced expected results", 4),
        _q("biggest_challenges", "paragraph",
           "Biggest current challenges", 5),
        _q("internal_limitations", "paragraph",
           "Internal limitations affecting strategy", 6),
        _q("external_factors", "paragraph",
           "External factors impacting visibility / growth", 7),
        _q("current_activities", "paragraph",
           "Marketing activities currently ongoing", 8),
        _q("top_goals", "paragraph",
           "Top marketing goals next 6–12 months", 9),
        _q("planned_campaigns", "paragraph",
           "Specific campaigns / initiatives planned", 10),
        _q("target_audience", "paragraph",
           "Target audience / customer segments", 11),
        _q("primary_focus", "single_choice",
           "Primary focus", 12, allow_other=True,
           options=_opts("Awareness", "Lead-gen", "Conversion")),
        _q("desired_tone", "paragraph",
           "Desired tone / message for future campaigns", 13),
        _q("kpis_tracked", "paragraph", "KPIs currently tracked", 14),
        _q("benchmarks", "paragraph", "Benchmarks / targets aiming for", 15),
        _q("analytics_tools", "multi_choice",
           "Existing analytics / reporting tools", 16, allow_other=True,
           options=_opts("Google Analytics", "HubSpot", "Salesforce")),
        _q("historic_milestones", "paragraph",
           "Historic milestones & achievements", 17),
        _q("booking_goals", "paragraph",
           "Goals around weekday / weekend bookings", 18),
    ]
    return {
        "key": "client-strategy-insights",
        "name": "Client Strategy Insights",
        "description": "Marketing strategy intake (Form 2).",
        "service_tag": None,
        "kind": "questionnaire",
        "field_definitions": fields,
    }


def _form3_branding_questionnaire() -> dict:
    """Form 3 (non-upload questions) — "Branding Details"."""
    fields = [
        _q("brand_style_preferences", "paragraph",
           "Brand colors, fonts, visual style preferences", 1),
        _q("brand_mission", "paragraph", "Brand mission / core message", 2),
        _q("brand_tone", "paragraph", "Brand tone of voice", 3),
        _q("brand_uniqueness", "paragraph",
           "What makes your brand unique", 4),
        _q("editing_dos_donts", "paragraph",
           "Editing do's and don'ts", 5),
        _q("brands_admired", "paragraph",
           "Brands you admire / wish to emulate", 6),
        _q("digital_reference_1", "short_text",
           "Digital reference #1 for brand vision", 7, required=False),
        _q("digital_reference_2", "short_text",
           "Digital reference #2 for brand vision", 8, required=False),
        _q("digital_reference_3", "short_text",
           "Digital reference #3 for brand vision", 9, required=False),
        _q("anything_else", "paragraph",
           "Anything else you'd like us to know", 10, required=False),
    ]
    return {
        "key": "branding-details",
        "name": "Client Onboarding: Branding Details",
        "description": "Brand identity, preferences, and perception "
                       "(Form 3 — questionnaire portion).",
        "service_tag": None,
        "kind": "questionnaire",
        "field_definitions": fields,
    }


def _form3_brand_assets_upload() -> dict:
    """Form 3 (upload questions) — "Brand Assets"."""
    fields = [
        _upload("logos", "Primary & secondary logos (high-res)", 1,
                required=False, max_files=5, max_mb=10),
        _upload("brand_guidelines", "Brand guidelines / style guide", 2,
                required=False, max_files=5, max_mb=10),
        _upload("other_assets",
                "Other visual assets (icons, photography, templates)", 3,
                required=False, max_files=10, max_mb=10),
        _upload("old_photos", "Old photos to be used in content", 4,
                required=True, max_files=10, max_mb=10),
        _upload("templates",
                "Existing templates / slogans / messaging frameworks", 5,
                required=False, max_files=5, max_mb=10),
    ]
    return {
        "key": "brand-assets",
        "name": "Client Onboarding: Brand Assets",
        "description": "Logo, brand-guideline, and visual-asset uploads "
                       "(Form 3 — upload portion).",
        "service_tag": None,
        "kind": "upload_request",
        "field_definitions": fields,
    }


def _form4_website() -> dict:
    """Form 4 — "Website Onboarding Form" (no uploads; 2 sensitive passwords)."""
    basic = "Basic Info"
    tech = "Technical Prep"
    domain = "Domain Services"
    design = "Design"
    inspiration = "Sources of Inspiration"
    acquisition = "Customer Acquisition"
    integrations = "Integrations"
    hosting = "Domain Credentials"
    platform = "Website Platform"
    fields = [
        _q("email", "email", "Email", 1),
        _q("name", "short_text", "Name", 2,
           section_id="basic", section_label=basic, prefill="contact.name"),
        _q("company", "short_text", "Company", 3,
           section_id="basic", section_label=basic, prefill="company.name"),
        _q("current_domain", "short_text", "Current website domain", 4,
           section_id="tech", section_label=tech),
        _q("continue_domain", "single_choice",
           "Continue using this domain?", 5,
           section_id="tech", section_label=tech, options=_opts("Yes", "No")),
        _q("domain_services", "multi_choice", "Services on domain", 6,
           section_id="domain", section_label=domain, allow_other=True,
           options=_opts(
               "Email", "Software Suite", "VPN", "Printer/fax", "N/A",
               "Not sure")),
        _q("domain_details", "paragraph", "Relevant details", 7,
           section_id="domain", section_label=domain),
        _q("design_inspiration", "paragraph",
           "Desired look / colors / fonts / elements", 8,
           section_id="design", section_label=design),
        _q("inspiration_site_1", "short_text", "Site #1 URL", 9,
           section_id="inspiration", section_label=inspiration),
        _q("inspiration_why_1", "paragraph", "Why Site #1", 10,
           section_id="inspiration", section_label=inspiration),
        _q("inspiration_site_2", "short_text", "Site #2 URL", 11,
           section_id="inspiration", section_label=inspiration),
        _q("inspiration_why_2", "paragraph", "Why Site #2", 12,
           section_id="inspiration", section_label=inspiration),
        _q("inspiration_site_3", "short_text", "Site #3 URL", 13,
           section_id="inspiration", section_label=inspiration),
        _q("inspiration_why_3", "paragraph", "Why Site #3", 14,
           section_id="inspiration", section_label=inspiration),
        _q("trends_to_avoid", "paragraph",
           "Design trends to avoid + why", 15,
           section_id="inspiration", section_label=inspiration),
        _q("desired_actions", "multi_choice", "Desired visitor actions", 16,
           section_id="acquisition", section_label=acquisition,
           allow_other=True,
           options=_opts("Contact form", "Call", "Email", "Purchase")),
        _q("planned_integrations", "multi_choice", "Planned integrations", 17,
           required=False, section_id="integrations",
           section_label=integrations, allow_other=True,
           options=_opts("Chatbot", "Calendar/Scheduler", "N/A")),
        _q("integration_explanation", "paragraph",
           "Integration explanation", 18, required=False,
           section_id="integrations", section_label=integrations),
        _q("hosting_site", "short_text", "Hosting Site", 19, required=False,
           section_id="hosting", section_label=hosting),
        _q("hosting_username", "short_text", "Hosting Username", 20,
           required=False, section_id="hosting", section_label=hosting),
        _q("hosting_password", "short_text", "Hosting Password", 21,
           required=False, section_id="hosting", section_label=hosting,
           sensitive=True),
        _q("platform_username", "short_text", "Website Platform Username", 22,
           required=False, section_id="platform", section_label=platform),
        _q("platform_password", "short_text", "Website Platform Password", 23,
           required=False, section_id="platform", section_label=platform,
           sensitive=True),
    ]
    return {
        "key": "website-onboarding",
        "name": "Website Onboarding Form",
        "description": "Website project intake — domain, design, integrations, "
                       "and credentials (Form 4).",
        "service_tag": "website",
        "kind": "questionnaire",
        "field_definitions": fields,
    }


def _form5_podcast() -> dict:
    """Form 5 — "Link Label Studios — Podcast/Studio Intake"."""
    fields = [
        _q("first_name", "short_text", "First Name", 1),
        _q("last_name", "short_text", "Last Name", 2),
        _q("email", "email", "Email", 3),
        _q("phone", "short_text", "Phone", 4),
        _q("podcast_name", "short_text", "Podcast / Brand Name", 5,
           required=False),
        _q("shooting_days", "single_choice", "Preferred Shooting Days", 6,
           options=_ALL_DAYS),
        _q("shooting_times", "single_choice", "Shooting Times", 7,
           options=_opts("Morning", "Afternoon", "Evening", "Flexible")),
        _q("filming_frequency", "single_choice", "Filming Frequency", 8,
           allow_other=True,
           options=_opts("Weekly", "Bi-Weekly", "Monthly")),
        _q("category_niche", "short_text", "Category / Niche", 9),
        _q("podcast_references", "paragraph",
           "Podcast references you love", 10, required=False),
        _q("social_handles", "short_text", "Personal Social Handles", 11),
        _q("branding_assistance", "single_choice",
           "Social management & branding assistance", 12, allow_other=True,
           options=_opts("Yes", "No")),
        _q("service_level", "single_choice", "Service Level", 13,
           allow_other=True,
           options=_opts("Film only", "Film + edit + distribute")),
        _q("distribution_platforms", "multi_choice",
           "Distribution Platforms", 14, allow_other=True,
           options=_opts("Spotify", "Apple", "YouTube")),
        _q("social_channels", "multi_choice", "Desired Social Channels", 15,
           allow_other=True,
           options=_opts(
               "Instagram", "Facebook", "TikTok", "YouTube Shorts", "X",
               "LinkedIn")),
        _q("budget_preference", "single_choice", "Budget Preference", 16,
           required=False,
           options=_opts(
               "Under $1k", "$1k-$2.5k", "$2.5k-$5k", "$5k+")),
        _q("additional_info", "paragraph", "Additional Info", 17,
           required=False),
    ]
    return {
        "key": "podcast-intake",
        "name": "Link Label Studios — Podcast/Studio Intake",
        "description": "Podcast / studio production intake (Form 5).",
        "service_tag": "podcast",
        "kind": "questionnaire",
        "field_definitions": fields,
    }


def _form6_guest() -> dict:
    """Form 6 — "Link Live — Guest Intake"."""
    fields = [
        _q("name", "short_text", "Your Name", 1, prefill="contact.name"),
        _q("email", "email", "Email", 2, required=False),
        _q("business_name", "short_text", "Business Name", 3),
        _q("bio", "paragraph", "Brief Bio", 4),
        _q("challenges_lessons", "paragraph",
           "Key Challenges & Lessons", 5),
        _q("innovative_strategies", "paragraph",
           "Innovative Strategies", 6),
        _q("current_approach", "paragraph",
           "Current Marketing Approach", 7),
        _q("industry_trends", "paragraph", "Industry Trends", 8,
           required=False),
        _q("goals", "paragraph", "Personal / Business Goals", 9),
        _q("recording_times", "single_choice",
           "Preferred Recording Times", 10,
           options=_opts("Morning", "Afternoon", "Evening")),
        _q("additional_comments", "paragraph", "Additional Comments", 11),
    ]
    return {
        "key": "guest-intake",
        "name": "Link Live — Guest Intake",
        "description": "Podcast guest intake (Form 6).",
        "service_tag": "link-live",
        "kind": "questionnaire",
        "field_definitions": fields,
    }


def onboarding_template_specs() -> list[dict]:
    """The 8 starter specs in stable order (pure data; no DB access).

    Exposed for the seed AND the tests so neither hand-rolls the inventory.
    Each spec also carries a stable ``key`` for the from-starter route.
    """
    return [
        _form1_admin_questionnaire(),
        _form1_identity_upload(),
        _form2_strategy(),
        _form3_branding_questionnaire(),
        _form3_brand_assets_upload(),
        _form4_website(),
        _form5_podcast(),
        _form6_guest(),
    ]


# Built freshly per call (the field dicts are mutable, so callers that clone
# them never share state) — the function is the canonical accessor.
STARTERS = onboarding_template_specs()


def get_starter(key: str) -> dict | None:
    """Return the starter spec with this ``key`` (a fresh, unshared copy), or
    ``None`` if no starter matches.

    Rebuilds from ``onboarding_template_specs()`` so the returned
    ``field_definitions`` are a fresh object the caller can hand to
    ``_build_template`` without mutating the module-level ``STARTERS``.
    """
    for spec in onboarding_template_specs():
        if spec["key"] == key:
            return spec
    return None
