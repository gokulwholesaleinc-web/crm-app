"""Shared URL safety helpers for SSRF defense.

Factored out so webhooks, email tracking redirects, and the proposal PDF
renderer can share one implementation. All callers need the same core
check: parse a URL, reject non-HTTP(S) schemes, and reject hosts that
resolve to private/loopback/link-local IP ranges for BOTH IPv4 and IPv6.

``getaddrinfo`` is used instead of ``gethostbyname`` so that:

* Every A/AAAA record returned for the host is checked, not just the
  first one — a DNS response with a public IPv4 + private IPv6 cannot
  sneak past.
* IPv6 private ranges (``::1``, ``fc00::/7``, ``fe80::/10``, the IPv6
  metadata endpoint ``fd00:ec2::254``) are covered.

Callers that need per-fetch rebinding protection should additionally pin
the resolved IP and pass it to the fetch layer — this module only answers
"is this URL safe right now?".
"""

import ipaddress
import logging
import socket
from collections.abc import Iterable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class UnsafeUrlError(ValueError):
    """Raised when a URL fails the SSRF safety checks."""


def is_private_ip(ip_str: str) -> bool:
    """Return True if ``ip_str`` is private, loopback, link-local, or reserved.

    Works uniformly for IPv4 and IPv6. The ``ipaddress`` module handles
    both AWS ``169.254.169.254`` metadata and its IPv6 equivalents.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def _resolve_all_addresses(host: str) -> list[str]:
    """Return every A/AAAA record for ``host``.

    ``getaddrinfo`` returns ``(family, type, proto, canonname, sockaddr)``
    tuples; ``sockaddr[0]`` is the address string for both IPv4 and IPv6.
    An empty list signals a resolution failure so callers can decide how
    to treat unresolvable hosts (webhooks tolerate, PDF fetcher rejects).
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    return list({str(info[4][0]) for info in infos})


def validate_public_url(
    url: str,
    *,
    allowed_schemes: Iterable[str] = ("https",),
    allowed_hostnames: Iterable[str] | None = None,
) -> str:
    """Validate ``url`` as safe for server-side fetch.

    Steps:

    1. The URL must parse and have a hostname.
    2. Scheme must be in ``allowed_schemes`` (``https`` by default).
    3. If ``allowed_hostnames`` is provided, the host must match one of
       them (case-insensitive). That's a strict whitelist — non-matching
       hosts are rejected even if they would resolve publicly.
    4. Otherwise EVERY IP the hostname resolves to (all A + AAAA
       records) must be public. If any single address is private/
       loopback/link-local/multicast/reserved/unspecified the URL is
       rejected. This blocks SSRF against cloud metadata endpoints
       (``169.254.169.254`` / ``fd00:ec2::254``), Docker-internal IPs,
       and split-horizon DNS tricks that return a public + private pair.

    Returns the validated URL unchanged. Raises :class:`UnsafeUrlError`
    on any failure so callers can surface a consistent error.
    """
    if not url or not isinstance(url, str):
        raise UnsafeUrlError("URL is empty")

    parsed = urlparse(url)
    if parsed.scheme.lower() not in {s.lower() for s in allowed_schemes}:
        raise UnsafeUrlError(
            f"URL scheme '{parsed.scheme}' not in allowlist {tuple(allowed_schemes)}"
        )
    if not parsed.hostname:
        raise UnsafeUrlError("URL has no hostname")

    host = parsed.hostname.lower()

    if allowed_hostnames:
        normalized = {h.lower() for h in allowed_hostnames}
        if host in normalized:
            return url
        raise UnsafeUrlError(f"Host '{host}' not in hostname allowlist")

    addresses = _resolve_all_addresses(host)
    if not addresses:
        raise UnsafeUrlError(f"Could not resolve host '{host}'")

    private = sorted(addr for addr in addresses if is_private_ip(addr))
    if private:
        raise UnsafeUrlError(
            f"Host '{host}' resolves to private IP(s) {private}"
        )

    return url
