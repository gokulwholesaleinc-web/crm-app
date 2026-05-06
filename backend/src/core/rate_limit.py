"""Shared rate limiter safe for use behind reverse proxies."""

from fastapi import Request
from slowapi import Limiter

from src.core.client_ip import get_client_ip


def get_remote_address(request: Request) -> str:
    """Get client IP for slowapi — string key (cannot be None)."""
    return get_client_ip(request) or "127.0.0.1"


limiter = Limiter(key_func=get_remote_address)
