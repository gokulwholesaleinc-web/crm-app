"""Client IP extraction that respects the reverse proxy in front of us.

Railway terminates TLS at its edge and forwards to the app over a
private network. `request.client.host` therefore returns the proxy's
internal address (a 10.x RFC1918 IP) instead of the real client —
which previously made every audit row + view-tracking row look like
it came from the same place.

Use ``get_client_ip(request)`` from any handler that wants to record
the real visitor IP for audit, ledger, or rate-limit purposes.

NOT auth-grade. XFF is set by Railway's proxy in prod, but nothing
inside the app verifies the request actually came through a trusted
proxy — a deploy that ever exposes the app's origin directly (or runs
without a proxy) would let a client spoof their IP via a self-supplied
XFF. We only honour XFF (not CF-Connecting-IP / X-Real-IP) so the
spoof surface matches the pre-existing rate-limiter behaviour. If the
deploy ever moves behind Cloudflare specifically, gate that header
behind a TRUST_PROXY_HEADERS env flag — don't add it back unguarded.
"""

from fastapi import Request


def get_client_ip(request: Request) -> str | None:
    """Return the visitor's real IP, or None if it can't be determined."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None
