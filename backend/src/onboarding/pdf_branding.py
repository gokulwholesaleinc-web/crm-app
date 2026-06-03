"""Shared LinkCreative brand header for GENERATED onboarding artifacts (§B.3).

The questionnaire summary PDF and the upload_request manifest PDF both render a
brand header — logo + company name + a primary-color rule — resolved from the
SAME ``TenantSettings`` source as the web fill page
(``resolve_public_branding``), so the generated PDF matches the already-branded
fill page (one brand source of truth). ``esign_pdf`` is UNAFFECTED: it stamps
Lorenzo's already-branded uploaded form.

Degrades gracefully and NEVER fails the artifact on a logo problem:
  * no ``TenantSettings`` row              → no header (empty list)
  * ``logo_url`` unset / unfetchable / bad → text-only company-name header
  * logo present                            → embedded, scaled, then the name

``fetch_logo=False`` (used on the Phase-A ``dry_run``) skips the network fetch:
the logo can never affect producibility (it degrades), so the dry-run stays
fast and only validates the answer content render.
"""

from __future__ import annotations

import io
import logging
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph
from reportlab.platypus.flowables import Flowable, HRFlowable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_LOGO_MAX_W = 1.8 * inch
_LOGO_MAX_H = 0.6 * inch
_LOGO_FETCH_TIMEOUT = 4.0
_LOGO_MAX_BYTES = 5 * 1024 * 1024
_DEFAULT_PRIMARY = "#6366f1"


async def brand_header_flowables(
    db: AsyncSession, *, fetch_logo: bool = True
) -> list[Flowable]:
    """Return Platypus flowables for the sender-brand header.

    Reuses ``resolve_public_branding`` (DRY — the web fill page's brand source).
    Returns ``[]`` when there is neither a logo nor a company name to show, so
    the artifact simply renders without a header rather than failing.
    """
    # Lazy import: public_helpers reaches into the app graph; keep this module
    # importable in any order (it is pulled in by the kind handlers).
    from src.onboarding.public_helpers import resolve_public_branding

    branding = await resolve_public_branding(db)
    if branding is None:
        return []

    primary = _safe_color(getattr(branding, "primary_color", None))
    company = (getattr(branding, "company_name", None) or "").strip()
    flow: list[Flowable] = []

    if fetch_logo:
        logo = await _fetch_logo(getattr(branding, "logo_url", None))
        if logo is not None:
            image = _safe_image(logo)
            if image is not None:
                flow.append(image)

    if company:
        company_style = ParagraphStyle(
            "OnbBrandCompany",
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=primary,
            spaceBefore=2,
            spaceAfter=2,
        )
        flow.append(Paragraph(escape(company), company_style))

    if not flow:
        return []
    flow.append(
        HRFlowable(
            width="100%", thickness=2, color=primary, spaceBefore=4, spaceAfter=12
        )
    )
    return flow


async def _fetch_logo(url: str | None) -> bytes | None:
    """Fetch the logo bytes server-side. ANY failure → ``None`` (text fallback)."""
    if not url:
        return None
    try:
        import httpx

        async with httpx.AsyncClient(
            timeout=_LOGO_FETCH_TIMEOUT, follow_redirects=True
        ) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            return None
        data = resp.content
        if not data or len(data) > _LOGO_MAX_BYTES:
            return None
        return data
    except Exception:  # noqa: BLE001 — a logo fetch must never fail the artifact
        logger.warning("onboarding brand header: logo fetch failed for %s", url)
        return None


def _safe_image(data: bytes) -> Image | None:
    """Build a scaled Platypus ``Image`` from logo bytes; ``None`` if undecodable."""
    try:
        from reportlab.lib.utils import ImageReader

        reader = ImageReader(io.BytesIO(data))
        iw, ih = reader.getSize()
        if not iw or not ih:
            return None
        scale = min(_LOGO_MAX_W / iw, _LOGO_MAX_H / ih, 1.0)
        return Image(io.BytesIO(data), width=iw * scale, height=ih * scale)
    except Exception:  # noqa: BLE001 — undecodable logo → text fallback
        logger.warning("onboarding brand header: logo decode failed; text fallback")
        return None


def _safe_color(value: str | None) -> Color:
    try:
        return HexColor(value) if value else HexColor(_DEFAULT_PRIMARY)
    except Exception:  # noqa: BLE001 — bad hex → default brand color
        return HexColor(_DEFAULT_PRIMARY)
