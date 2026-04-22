"""Shared HTML→PDF rendering with SSRF-safe resource loading.

Both quotes and proposals need to ship PDFs as email attachments. They
share the same SSRF concern — weasyprint will happily fetch ``file://``
or private-IP URLs for logos, fonts, and CSS if we let it — so the fetch
gate lives here and both callers reuse it.

The env var name (``PROPOSAL_LOGO_ALLOWED_HOSTS``) is preserved for
backwards compatibility with existing deployments; it now acts as a
cross-document allowlist.
"""

import logging
import os

from src.core.url_safety import UnsafeUrlError, validate_public_url

logger = logging.getLogger(__name__)


def pdf_logo_allowed_hosts() -> list[str] | None:
    """Return the optional allowlist of hostnames permitted for PDF resources.

    Read from ``PROPOSAL_LOGO_ALLOWED_HOSTS`` (env name kept for backwards
    compatibility). When unset, :func:`validate_public_url` falls back to
    ``https`` + non-private-IP enforcement.
    """
    raw = os.getenv("PROPOSAL_LOGO_ALLOWED_HOSTS", "").strip()
    if not raw:
        return None
    return [h.strip().lower() for h in raw.split(",") if h.strip()]


def safe_pdf_url_fetcher(url: str):
    """weasyprint url_fetcher that rejects unsafe URLs before fetching."""
    try:
        validate_public_url(
            url,
            allowed_schemes=("https",),
            allowed_hostnames=pdf_logo_allowed_hosts(),
        )
    except UnsafeUrlError as exc:
        logger.warning("Rejected unsafe PDF resource URL: %s", exc)
        raise
    from weasyprint import default_url_fetcher  # pyright: ignore[reportMissingImports]
    return default_url_fetcher(url)


def render_html_to_pdf(html: str) -> bytes:
    """Render an HTML document to PDF bytes.

    Falls back to the HTML as UTF-8 bytes when weasyprint is unavailable
    so callers get *something* rather than an exception — they can detect
    the fallback by checking the leading bytes if it matters. The SSRF
    allowlist above still runs on every resource weasyprint tries to load.
    """
    try:
        import weasyprint  # pyright: ignore[reportMissingImports]
    except ImportError:
        logger.warning("weasyprint not installed — returning HTML bytes in place of PDF")
        return html.encode("utf-8")

    return weasyprint.HTML(string=html, url_fetcher=safe_pdf_url_fetcher).write_pdf()
