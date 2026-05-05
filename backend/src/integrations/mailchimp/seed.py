"""Boot-time seed that materialises a MailchimpConnection from env vars.

Single-tenant deployments (the Link Creative box, for example) want to
configure Mailchimp once via Railway env without then having to log in
and click through Settings → Integrations on every restart. This
module reads ``MAILCHIMP_API_KEY`` and the optional
``MAILCHIMP_DEFAULT_AUDIENCE_ID`` and creates an active connection for
any tenant that doesn't already have one.

The UI Connect form remains the source of truth for ad-hoc edits — if
a tenant already has an active connection (revoked_at IS NULL), we
leave it alone, even if the API key in the row differs from the env
value. That way an operator can rotate the key in the UI without
having the next restart silently put the env value back.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.integrations.mailchimp.client import MailchimpError
from src.integrations.mailchimp.service import ClientFactory, MailchimpService
from src.whitelabel.models import Tenant

logger = logging.getLogger(__name__)


async def seed_mailchimp_from_env(
    db: AsyncSession, *, client_factory: ClientFactory = None
) -> int:
    """Create a MailchimpConnection per tenant from MAILCHIMP_API_KEY.

    Returns the number of tenants that received a fresh connection.
    Returns 0 (and is a no-op) when the env var is empty.

    ``client_factory`` is forwarded to :class:`MailchimpService` so
    tests can substitute a mock-transport client without monkey-
    patching the production class.
    """
    api_key = (settings.MAILCHIMP_API_KEY or "").strip()
    if not api_key:
        return 0

    default_audience = (settings.MAILCHIMP_DEFAULT_AUDIENCE_ID or "").strip() or None

    tenants = (
        (await db.execute(select(Tenant).where(Tenant.is_active == True))).scalars().all()
    )
    if not tenants:
        return 0

    service = MailchimpService(db, client_factory=client_factory)
    seeded = 0
    for tenant in tenants:
        existing = await service.get_connection(tenant.id)
        if existing is not None:
            continue
        # Use a synthetic user id of None for the connected_by_id —
        # there's no human at the wheel for boot-time seeds, and the
        # column is nullable. Pass an admin user id when one is
        # available so audit trails show *something*; the seed runs
        # before any HTTP context exists, so we don't have one here.
        try:
            conn = await service.connect(
                tenant_id=tenant.id,
                connected_by_id=_pick_seed_user_id(),
                api_key=api_key,
            )
        except (ValueError, MailchimpError) as exc:
            logger.warning(
                "mailchimp seed skipped tenant=%s reason=%s", tenant.slug, exc
            )
            continue
        if default_audience:
            try:
                await service.set_default_audience(tenant.id, default_audience)
            except MailchimpError as exc:
                logger.warning(
                    "mailchimp seed could not pin audience tenant=%s id=%s reason=%s",
                    tenant.slug,
                    default_audience,
                    exc,
                )
        seeded += 1
        logger.info(
            "mailchimp seed: created connection tenant=%s server=%s account=%s",
            tenant.slug,
            conn.server_prefix,
            conn.account_email,
        )
    if seeded:
        await db.commit()
    return seeded


def _pick_seed_user_id() -> int | None:
    """Connection rows can be created without an attributed user.

    A future improvement is to look up the admin email from
    ``ADMIN_EMAILS`` and attribute the row to that user, but that adds
    a DB round-trip per tenant for no functional gain right now. The
    UI Connect form will overwrite ``connected_by_id`` if/when an
    operator re-runs the connect there.
    """
    return None
