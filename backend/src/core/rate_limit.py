"""Shared rate limiter safe for use behind reverse proxies."""

from fastapi import Request
from slowapi import Limiter


def get_remote_address(request: Request) -> str:
    """Get client IP from X-Forwarded-For header (reverse proxy) or request.client."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "127.0.0.1"


limiter = Limiter(key_func=get_remote_address)
