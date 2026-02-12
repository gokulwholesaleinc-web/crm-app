"""Tenant resolution middleware for multi-tenant white-label support.

Extracts tenant identification from incoming requests and sets it
on request.state for downstream dependencies to resolve.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class TenantMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that extracts tenant hints from request.

    Resolution order:
    1. X-Tenant-Slug header (API clients)
    2. Domain/subdomain from Host header
    3. Falls back to None (no tenant context)

    Sets request.state.tenant_slug_hint and request.state.tenant_domain_hint
    for use by downstream FastAPI dependencies which perform the actual DB lookup.
    This avoids the middleware needing its own DB session (important for testing).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        tenant_slug_hint = None
        tenant_domain_hint = None

        # 1. Check X-Tenant-Slug header first
        header_slug = request.headers.get("x-tenant-slug")
        if header_slug:
            tenant_slug_hint = header_slug

        # 2. Extract domain from Host header for subdomain matching
        if tenant_slug_hint is None:
            host = request.headers.get("host", "")
            domain = host.split(":")[0] if host else ""
            if domain and domain not in ("localhost", "127.0.0.1", "testserver", "test"):
                tenant_domain_hint = domain

        # Set hints on request.state
        request.state.tenant_slug_hint = tenant_slug_hint
        request.state.tenant_domain_hint = tenant_domain_hint

        response = await call_next(request)
        return response
