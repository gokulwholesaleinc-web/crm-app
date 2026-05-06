"""Client IP extraction that respects the reverse proxy in front of us.

Railway and Cloudflare both terminate TLS at their edge and forward to
the app over a private network. `request.client.host` therefore returns
the proxy's internal address (a 10.x RFC1918 IP) instead of the real
client — which previously made every audit row + view-tracking row look
like it came from the same place.

Use ``get_client_ip(request)`` from any handler that wants to record the
real visitor IP for audit, ledger, or rate-limit purposes.
"""

from fastapi import Request


def get_client_ip(request: Request) -> str | None:
    """Return the visitor's real IP, or None if it can't be determined.

    Preference order, highest first:
    - ``CF-Connecting-IP`` (Cloudflare's signed header — only present
      when traffic actually came through Cloudflare)
    - ``X-Forwarded-For`` first hop (Railway and most reverse proxies)
    - ``X-Real-IP`` (nginx fallback)
    - ``request.client.host`` — only useful when the app sits on the
      public internet directly, which prod doesn't.
    """
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client:
        return request.client.host
    return None
