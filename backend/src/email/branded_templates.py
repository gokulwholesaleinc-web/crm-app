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

# Tenants override via tenant_branding settings. The wrapper uses
# ``primary_color`` as the brand-spotlight gold (drives the accent
# rule + tagline pipe separators + wordmark-fallback first word) and
# ``accent_color`` as the CTA-pill background (typically a strong
# contrast — black or white). ``secondary_color`` is unused by the
# email wrapper but still drives in-app surfaces. Defaults below
# match the production Link Creative palette (primary=#CF982C gold,
# accent=#000000 black).
_DEFAULT_BRANDING = {
    "company_name": "CRM",
    "logo_url": "",
    "primary_color": "#CF982C",
    "secondary_color": "#F9F9F9",
    "accent_color": "#000000",
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
    # Email wrapper extras (migration 034). Empty strings mean "omit"
    # — the wrapper skips the corresponding header/footer block when
    # no value is present so transactional emails for tenants that
    # haven't configured these still render cleanly.
    "tagline": "",
    "social_facebook_url": "",
    "social_instagram_url": "",
    "social_tiktok_url": "",
    "social_linkedin_url": "",
    "social_youtube_url": "",
    "social_website_url": "",
}


# Footer social-row glyphs. Each tuple is
# ``(label, settings_field, icon_url, letter_fallback)`` — the URL
# renders as a bare 28-px white ``<img>``, the letter is wired to
# the image's ``alt=`` so image-blocking email clients (Outlook
# Desktop's default first-touch policy, Gmail privacy mode) still
# show a readable mark in the same cell. Brand glyphs come from
# Simple Icons (the authoritative open-source brand-mark collection
# — Facebook ``f``, IG camera, TikTok musical note + tail, LinkedIn
# ``in`` badge, YouTube play tile); the website slot uses
# ``mdi:web`` for a stroke-matched globe. All rendered in white via
# ``color=%23ffffff`` to sit against the dark footer.
_ICONIFY_BASE = "https://api.iconify.design"
_SOCIAL_PLATFORMS: tuple[tuple[str, str, str, str], ...] = (
    (
        "Facebook",
        "social_facebook_url",
        f"{_ICONIFY_BASE}/simple-icons/facebook.svg?color=%23ffffff",
        "f",
    ),
    (
        "Instagram",
        "social_instagram_url",
        f"{_ICONIFY_BASE}/simple-icons/instagram.svg?color=%23ffffff",
        "IG",
    ),
    (
        "TikTok",
        "social_tiktok_url",
        f"{_ICONIFY_BASE}/simple-icons/tiktok.svg?color=%23ffffff",
        "TT",
    ),
    (
        "LinkedIn",
        "social_linkedin_url",
        f"{_ICONIFY_BASE}/simple-icons/linkedin.svg?color=%23ffffff",
        "in",
    ),
    (
        "YouTube",
        "social_youtube_url",
        f"{_ICONIFY_BASE}/simple-icons/youtube.svg?color=%23ffffff",
        "YT",
    ),
    (
        "Website",
        "social_website_url",
        f"{_ICONIFY_BASE}/mdi/web.svg?color=%23ffffff",
        "W",
    ),
)

# Fixed near-black for the email footer. Kept hardcoded rather than
# threaded through tenant_settings: the dark footer is the design
# contract of the wrapper, not a per-tenant toggle. Tenants choose
# their wordmark + tagline + accent gold; the footer surface is the
# brand-agnostic frame.
_EMAIL_FOOTER_BG = "#0a0a0a"


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
            # Email-wrapper extras (migration 034). Missing values become
            # empty strings so the render path's truthy checks omit the
            # block instead of emitting an unconfigured placeholder.
            "tagline": s.tagline or "",
            "social_facebook_url": s.social_facebook_url or "",
            "social_instagram_url": s.social_instagram_url or "",
            "social_tiktok_url": s.social_tiktok_url or "",
            "social_linkedin_url": s.social_linkedin_url or "",
            "social_youtube_url": s.social_youtube_url or "",
            "social_website_url": s.social_website_url or "",
        }

    @staticmethod
    def get_default_branding() -> dict:
        """Default branding when no tenant is configured."""
        return dict(_DEFAULT_BRANDING)


# ---------------------------------------------------------------------------
# Base HTML email template
# ---------------------------------------------------------------------------

def _render_tagline(tagline: str, pipe_color: str) -> str:
    """Render the email-header tagline with gold-pipe separators.

    The on-disk value carries vertical bars ("ACCESSIBLE MEDIA |
    AUTHENTIC STORYTELLING | …"); this splits on ``|``, escapes each
    segment, and re-joins with a styled span that paints the bars in
    the brand accent color. Empty/whitespace-only segments are dropped
    so trailing or doubled pipes don't emit phantom dividers.
    """
    parts = [p.strip() for p in (tagline or "").split("|") if p.strip()]
    if not parts:
        return ""
    sep = (
        f'<span style="color:{pipe_color};font-weight:700;padding:0 6px;" '
        f'aria-hidden="true">|</span>'
    )
    return sep.join(escape(p) for p in parts)


def _safe_external_url(url: str | None) -> str:
    """Strict variant of :func:`_safe_url` for outbound social links.

    The social-row cells are public footer links that must always
    point to a remote profile page — site-relative paths and
    ``mailto:`` URIs are valid for other email surfaces (campaign
    unsubscribe link in particular) but here they'd produce a
    confused recipient clicking "Facebook" and landing on
    ``/admin/internal`` or popping a compose window. Reject anything
    that isn't ``http(s)://`` so the schema-layer validator's policy
    is enforced again at the render sink.
    """
    stripped = (url or "").strip()
    if not stripped:
        return ""
    if stripped.lower().startswith(("https://", "http://")):
        return stripped
    return ""


def _render_social_row(branding: dict) -> str:
    """Render the social-platform glyph links for the dark footer.

    Each platform contributes a `<td>` cell only when its URL field
    is non-empty *and* passes the strict ``http(s)://`` allowlist;
    cells are omitted otherwise so all-unsafe configurations
    collapse cleanly.

    Returns the joined ``<td>`` cells of a single ``<tr>``, or the
    empty string. The caller wraps the surviving cells in a
    ``<table><tr>`` and emits the "KEEP UP WITH US ON SOCIAL"
    heading only when this function returned non-empty.
    """
    cells: list[str] = []
    for label, key, icon_url, fallback_letter in _SOCIAL_PLATFORMS:
        href = _safe_external_url(branding.get(key))
        if not href:
            continue
        # Bare 28px white brand-icon. 10px horizontal padding each
        # side gives the six-icon row breathing room. The <a>'s
        # ``font-*`` + ``line-height:28px`` are deliberate fallback
        # styling for image-blocked clients (Outlook desktop default
        # / Gmail privacy mode) — when the iconify CDN response or
        # remote-image policy strips the inline <img>, the ``alt``
        # letter still renders at a readable 14px white inside a
        # 28-px line box, instead of collapsing to zero height.
        cells.append(
            f'<td style="padding:0 10px;" valign="middle">'
            f'<a href="{escape(href)}" target="_blank" '
            f'aria-label="{escape(label)}" '
            f'style="text-decoration:none;color:#ffffff;'
            f"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
            f'font-size:14px;font-weight:700;line-height:28px;">'
            f'<img src="{escape(icon_url)}" alt="{escape(fallback_letter)}" '
            f'width="28" height="28" '
            f'style="display:block;width:28px;height:28px;'
            f'border:0;outline:none;" />'
            f'</a></td>'
        )
    return "".join(cells)


def _base_email_html(
    branding: dict,
    headline: str,
    body_html: str,
    cta_text: str | None = None,
    cta_url: str | None = None,
    sender_title: str | None = None,
    sender_name: str | None = None,
) -> str:
    """Render content into a branded, responsive HTML email wrapper.

    Visual contract (Link Creative template, see PR #325):
      * White header with a centered wordmark logo, the brand tagline
        below with gold ``|`` separators, then a gold accent rule.
      * White body section: headline, content, optional CTA pill.
      * Near-black footer with "KEEP UP WITH US ON SOCIAL" heading,
        a row of social-icon circles (whichever URLs are configured),
        optional sender attribution, footer text, and privacy/ToS
        links.

    Uses inline CSS only — every email client (Gmail, Outlook, Apple
    Mail, web previews) strips `<style>` blocks unevenly. Includes
    dark-mode + <480px mobile media query support: paddings tighten,
    the headline + body scale down, and the CTA pill goes full-width
    so the touch target is comfortable.

    ``sender_name`` / ``sender_title`` survive as a small attribution
    caption rendered above the body (kept for API-level back-compat —
    no production caller passes them today; they used to live in the
    old two-column dark header).
    """
    # _safe_hex sanitizes each color before it reaches the inline-CSS
    # sinks below. ``escape`` is HTML-escaping, not hex validation; a
    # corrupt-row payload of "red" or "#zzz" would otherwise produce
    # ``background-color:red;`` (which clients quietly drop) and the
    # customer would see a white email with no diagnostic trace. See
    # _safe_hex docstring for why ORM-level reads bypass the schema
    # validator.
    # primary_color = brand-spotlight gold → drives the accent rule,
    #                 tagline pipe separators, and wordmark fallback's
    #                 first word.
    # accent_color  = CTA pill background + wordmark fallback's rest.
    # secondary_color is unused by the email wrapper (still drives
    # in-app surfaces).
    # Hardcode #CF982C / #000000 fallbacks so a tenant with empty
    # color fields still renders the Link Creative aesthetic.
    primary_raw = _safe_hex(branding.get("primary_color"), "#CF982C", field="primary_color")
    accent = escape(_safe_hex(branding.get("accent_color"), "#000000", field="accent_color"))
    # Light-mode page + card surfaces. The wrapper is fixed light-mode
    # (no prefers-color-scheme media query) so these always paint as
    # configured.
    # Prod's bg_color_light is #F9F9F9 (off-white); we let that flow
    # through. Surface defaults to pure #ffffff so the card stays
    # clearly readable even when an admin sets bg to a gray.
    bg_light_raw = _safe_hex(branding.get("bg_color_light"), "#f9fafb", field="bg_color_light")
    surface_light_raw = _safe_hex(branding.get("surface_color_light"), "#ffffff", field="surface_color_light")
    # Defensive clamp: if a tenant has set ``primary_color`` to a
    # value that collides with the surface or page background, the
    # gold accent rule + tagline pipes would render invisibly against
    # the header card. Fall back to the default gold so the visual
    # contract holds. ``_safe_hex`` lowercases inconsistently (it
    # only strips), so compare case-folded.
    if primary_raw.lower() in (surface_light_raw.lower(), bg_light_raw.lower()):
        logger.warning(
            "branding primary_color (%s) collides with surface/bg; falling back to #CF982C",
            primary_raw,
        )
        primary_raw = "#CF982C"
    primary = escape(primary_raw)
    bg_light = escape(bg_light_raw)
    surface_light = escape(surface_light_raw)
    company = escape(branding.get("company_name", "CRM"))
    logo_url = _safe_url(branding.get("logo_url", ""))
    footer_text = escape(branding.get("footer_text", ""))
    privacy_url = _safe_url(branding.get("privacy_policy_url", ""))
    terms_url = _safe_url(branding.get("terms_of_service_url", ""))
    safe_cta_url = _safe_url(cta_url)
    tagline_html = _render_tagline(branding.get("tagline", ""), primary)

    # Centered wordmark logo. When no logo is configured we fall back
    # to the company-name text in the same slot so the header doesn't
    # collapse — admins who skip the logo upload still get a usable
    # branded header. Multi-word company names render with the first
    # word in the primary (gold) accent and the rest in the accent
    # (typically black) — approximates the Link Creative split-word
    # wordmark so single-tenant deployments look on-brand even before
    # an admin uploads the real logo.
    if logo_url:
        logo_block = (
            f'<img src="{escape(logo_url)}" alt="{company}" '
            f'height="48" '
            f'style="display:inline-block;height:48px;width:auto;max-width:320px;'
            f'max-height:48px;" />'
        )
    else:
        # ``... or "CRM"`` only catches ``None`` and ``""`` — a
        # whitespace-only value like ``"   "`` survives that guard
        # and then strips to ``""``, which would emit an empty
        # ``<span>`` and collapse the header. Re-check the stripped
        # value before splitting and fall through to "CRM" if empty.
        raw_company = (branding.get("company_name") or "CRM").strip() or "CRM"
        font_stack = (
            "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
            "font-size:28px;font-weight:800;letter-spacing:0.5px;"
            "text-transform:uppercase;"
        )
        parts = raw_company.split(maxsplit=1)
        if len(parts) == 2:
            first, rest = parts
            logo_block = (
                f'<span style="color:{primary};{font_stack}">{escape(first)}</span>'
                f'<span style="color:{accent};{font_stack}">{escape(rest)}</span>'
            )
        else:
            logo_block = (
                f'<span style="color:{accent};{font_stack}">{escape(raw_company)}</span>'
            )

    # Tagline copy text is dark — hardcoded #111827 so it stays
    # readable regardless of how primary is configured. The pipe
    # separators inside the rendered tagline pick up `primary` (gold).
    tagline_block = (
        f'<div class="email-tagline" style="margin-top:10px;'
        f'color:#111827;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;'
        f'font-size:12px;font-weight:600;letter-spacing:1px;text-transform:uppercase;'
        f'line-height:1.4;">{tagline_html}</div>'
        if tagline_html
        else ""
    )

    # Sender attribution — small caption above the body. Kept for
    # back-compat with the old two-column header API even though no
    # production caller passes these fields today; whitespace-only
    # values are treated as absent.
    sn = (sender_name or "").strip()
    st = (sender_title or "").strip()
    sender_block = ""
    if sn or st:
        parts: list[str] = []
        if sn:
            parts.append(
                f'<span style="color:#111827;font-weight:600;">{escape(sn)}</span>'
            )
        if st:
            parts.append(
                f'<span class="email-sender-title" style="color:#6b7280;'
                f'{"margin-left:6px;" if sn else ""}">{escape(st)}</span>'
            )
        sender_block = (
            '<div class="email-sender-attribution" '
            'style="margin-bottom:12px;font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;'
            'font-size:13px;line-height:1.4;">'
            + "".join(parts)
            + "</div>"
        )

    # Headline `<h1>` only renders when the caller actually supplies
    # one. Notification emails frequently pass an empty string when the
    # body already opens with "Hello, ..." — emitting an empty `<h1>`
    # left a 22-px-tall gap of whitespace that didn't match the
    # reference template.
    headline_text = (headline or "").strip()
    if headline_text:
        headline_html = (
            f'<h1 class="email-headline" style="margin:0 0 16px;'
            f"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
            f'font-size:22px;font-weight:700;color:#111827;">'
            f'{escape(headline_text)}</h1>'
        )
    else:
        headline_html = ""

    # CTA button — only render if the URL passed the scheme allowlist.
    # email-cta-wrap / email-cta-link classes drive the <480px mobile
    # media-query override that snaps the pill to full container width
    # so the tap target is comfortable on phones.
    if cta_text and safe_cta_url:
        cta_html = (
            f'<table role="presentation" class="email-cta-wrap" cellpadding="0" cellspacing="0" '
            f'style="margin:24px auto 0;">'
            f'<tr><td style="background-color:{accent};border-radius:24px;'
            f'text-align:center;">'
            f'<a class="email-cta-link" href="{escape(safe_cta_url)}" target="_blank" '
            f'style="display:inline-block;padding:12px 28px;color:#ffffff;'
            f"font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:15px;"
            f'font-weight:600;text-decoration:none;text-transform:uppercase;letter-spacing:0.5px;">{escape(cta_text)}</a>'
            f'</td></tr></table>'
        )
    else:
        cta_html = ""

    # Footer social-icons row. Heading only renders when at least one
    # platform URL is configured; otherwise the entire block collapses
    # so tenants with no socials don't get a stranded "KEEP UP WITH
    # US ON SOCIAL" line above an empty row.
    socials_row = _render_social_row(branding)
    if socials_row:
        socials_html = (
            f'<p class="email-social-heading" '
            f'style="margin:0 0 14px;color:#ffffff;font-family:-apple-system,'
            f"BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:11px;font-weight:700;"
            f'letter-spacing:2px;text-transform:uppercase;text-align:center;">'
            f'KEEP UP WITH US ON SOCIAL</p>'
            f'<table role="presentation" cellpadding="0" cellspacing="0" align="center" '
            f'style="margin:0 auto;"><tr>{socials_row}</tr></table>'
        )
    else:
        socials_html = ""

    # Footer text links — privacy + terms render as small white
    # underlined links centered below the social row, matching the
    # Link Creative footnote style ("update your preferences or
    # unsubscribe"). Campaign emails layer an unsubscribe link in via
    # ``render_campaign_wrapper``; transactional emails just surface
    # the legal links if configured.
    footer_links_parts: list[str] = []
    if privacy_url:
        footer_links_parts.append(
            f'<a href="{escape(privacy_url)}" '
            f'style="color:#e5e7eb;text-decoration:underline;">Privacy Policy</a>'
        )
    if terms_url:
        footer_links_parts.append(
            f'<a href="{escape(terms_url)}" '
            f'style="color:#e5e7eb;text-decoration:underline;">Terms of Service</a>'
        )
    footer_links = (
        '<p style="margin:18px 0 0;color:#9ca3af;font-size:12px;text-align:center;">'
        + " &middot; ".join(footer_links_parts)
        + "</p>"
        if footer_links_parts
        else ""
    )

    footer_text_block = (
        f'<p style="margin:14px 0 0;color:#9ca3af;font-size:12px;text-align:center;">'
        f'{footer_text}</p>'
        if footer_text
        else ""
    )

    return f"""\
<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="color-scheme" content="only light"/>
<meta name="supported-color-schemes" content="light"/>
<title>{escape(headline)}</title>
<!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
<style>
/* The Link Creative wrapper is a fixed white-card / gold-rule / black-footer
   composition — no dark-mode variant by design. The meta `only light` tells
   conformant clients to skip automatic color-scheme inversion, and we leave
   every surface paint explicit inline so non-conformant clients (older
   Outlook, some web previewers) don't repaint via :root inheritance. */
@media only screen and (max-width:480px){{
  .email-outer-cell{{padding:12px 8px!important;}}
  .email-header-cell{{padding:20px 16px 16px!important;}}
  .email-body-cell{{padding:24px 18px!important;}}
  .email-footer-cell{{padding:22px 16px!important;}}
  .email-headline{{font-size:19px!important;line-height:1.3!important;}}
  .email-text{{font-size:14px!important;}}
  .email-tagline{{font-size:11px!important;letter-spacing:0.5px!important;}}
  .email-cta-wrap{{width:100%!important;margin:20px 0 0!important;}}
  .email-cta-link{{display:block!important;padding:14px 20px!important;}}
}}
</style>
</head>
<body style="margin:0;padding:0;background-color:{bg_light};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
<table role="presentation" class="email-bg" cellpadding="0" cellspacing="0" width="100%" style="background-color:{bg_light};">
<tr><td class="email-outer-cell" align="center" style="padding:24px 16px;">

<!-- Header (white surface, centered logo + tagline + gold rule) -->
<table role="presentation" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;background-color:{surface_light};">
<tr><td class="email-header-cell" align="center" style="padding:32px 32px 20px;text-align:center;border-radius:8px 8px 0 0;">
  {logo_block}
  {tagline_block}
</td></tr>
<tr><td style="height:3px;line-height:3px;font-size:0;background-color:{primary};">&nbsp;</td></tr>
</table>

<!-- Body -->
<table role="presentation" class="email-card" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;background-color:{surface_light};">
<tr><td class="email-body-cell" style="padding:32px 32px;">
  {sender_block}
  {headline_html}
  <div class="email-text" style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;font-size:15px;line-height:1.6;color:#334155;">
    {body_html}
  </div>
  {cta_html}
</td></tr>
</table>

<!-- Footer (dark surface, social-icon row + legal links) -->
<table role="presentation" class="email-footer" cellpadding="0" cellspacing="0" width="600" style="max-width:600px;width:100%;background-color:{_EMAIL_FOOTER_BG};">
<tr><td class="email-footer-cell" style="padding:28px 24px;border-radius:0 0 8px 8px;text-align:center;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;">
  {socials_html}
  {footer_text_block}
  {footer_links}
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
    sender_title: str | None = None,
    sender_name: str | None = None,
) -> str:
    """Render any content into the branded email wrapper."""
    return _base_email_html(
        branding=branding,
        headline=headline,
        body_html=body_html,
        cta_text=cta_text,
        cta_url=cta_url,
        sender_title=sender_title,
        sender_name=sender_name,
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
            f'<p>Hi {client},</p>'
            f'<p>{company} has sent you quote <strong>#{number}</strong> for your review. '
            f'Please click the button below to view the full details, and accept or decline the quote.</p>'
        )
    else:
        intro = (
            f'<p>Hi {client},</p>'
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
<p>Hi {client},</p>
<p>Here's our proposal: <strong>{title}</strong></p>
<div style="background-color:#f9fafb;border-radius:6px;padding:16px;margin:16px 0;">
  <p style="margin:0 0 8px;font-size:14px;color:#6b7280;">Summary</p>
  <p style="margin:0;font-size:15px;">{summary}</p>
</div>
<p style="font-size:16px;font-weight:700;">Proposed investment: {currency} {total}</p>
<p>Ready to move forward? Click the button below to review and accept.</p>"""

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
<p>Hi {client},</p>
<p>Your invoice #{receipt_no} has been processed. Details below.</p>
<div style="background-color:#f0fdf4;border-left:4px solid {accent};border-radius:4px;padding:16px;margin:16px 0;">
  <p style="margin:0;font-size:13px;color:#6b7280;">Amount paid</p>
  <p style="margin:4px 0 0;font-size:24px;font-weight:700;color:#111827;">{currency} {amount}</p>
</div>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin:16px 0;font-size:14px;">
<tr><td style="padding:4px 0;color:#6b7280;">Receipt #</td><td style="padding:4px 0;text-align:right;">{receipt_no}</td></tr>
<tr><td style="padding:4px 0;color:#6b7280;">Date</td><td style="padding:4px 0;text-align:right;">{pay_date}</td></tr>
<tr><td style="padding:4px 0;color:#6b7280;">Payment method</td><td style="padding:4px 0;text-align:right;">{pay_method}</td></tr>
</table>
<p style="font-size:13px;color:#6b7280;">Questions about this invoice? Reply here or contact us.</p>"""

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
<p>Hi {client},</p>
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
        '<p style="font-size:13px;color:#6b7280;">Questions about this invoice? Reply here or contact us.</p>'
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
<p>{assigner} assigned you a new lead: <strong>{lead_name}</strong></p>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f9fafb;border-radius:6px;padding:16px;margin:16px 0;font-size:14px;">
<tbody>
{''.join(rows)}
</tbody>
</table>
<p style="color:#6b7280;font-size:13px;">First step: view the lead and schedule an outreach call.</p>"""

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
<p><strong>{activity_subject}</strong> is due {due_at}.</p>
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="background-color:#f9fafb;border-radius:6px;padding:16px;margin:16px 0;font-size:14px;">
<tbody>
{''.join(rows)}
</tbody>
</table>
<p style="color:#6b7280;font-size:13px;">Jump in to complete or reschedule.</p>"""

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
        f'{escape(_safe_hex(branding.get("primary_color"), "#1e293b", field="primary_color"))};background-color:#f9fafb;'
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
        f'{escape(_safe_hex(branding.get("primary_color"), "#1e293b", field="primary_color"))};background-color:#f9fafb;'
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

    if audience == "signer":
        # Distinct copy when the PDF couldn't be rendered — saying
        # "attached for your records" while attaching nothing is
        # actively misleading.
        if data.get("pdf_pending"):
            body_html = f"""\
<p>Hi {signer_name or 'there'},</p>
<p>Thank you for signing <strong>{title}</strong>. Your signed PDF copy will be sent once it's ready — usually within a few minutes. Reply to this email if you don't see it shortly.</p>
<p>We'll follow up once the other party signs. You'll get an email confirmation at that time.</p>"""
        else:
            body_html = f"""\
<p>Hi {signer_name or 'there'},</p>
<p>Thank you for signing <strong>{title}</strong>. Your signed copy is attached.</p>
<p>We'll follow up once the other party signs. You'll get an email confirmation at that time.</p>"""
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


# ---------------------------------------------------------------------------
# Contract send email
# ---------------------------------------------------------------------------

def render_contract_send_email(
    branding: dict,
    contract_title: str,
    client_first_name: str,
    sign_url: str,
    message: str | None = None,
) -> tuple[str, str]:
    """Returns (subject, html_body) for a contract signature request email.

    Uses the centralized branded email wrapper so the layout, colors, and
    footer match every other outbound email rather than the hand-built
    inline HTML that contracts/service.py previously constructed.
    """
    title = escape(contract_title)
    name = escape(client_first_name) if client_first_name else "there"
    extra_msg = f"<p>{escape(message)}</p>" if message else ""

    body_html = f"""\
<p>Hi {name},</p>
<p>We've prepared <strong>{title}</strong> for your signature.</p>
{extra_msg}
<p>Review and sign using the button below. The link is valid for 7 days.</p>
<p>Questions? Reply to this email.</p>"""

    subject = f"Contract for signature — {contract_title}"
    html = render_branded_email(
        branding=branding,
        subject=subject,
        headline="Contract ready to sign",
        body_html=body_html,
        cta_text="Review & Sign",
        cta_url=sign_url,
    )
    return subject, html
