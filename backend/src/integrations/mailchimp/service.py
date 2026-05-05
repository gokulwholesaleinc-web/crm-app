"""High-level Mailchimp orchestration: connect, audience sync, campaign send.

The service wraps :class:`MailchimpClient` with the persistence + business
rules the CRM needs:

* ``connect`` validates the API key against ``/ping`` before persisting,
  so an invalid key fails fast at the UI rather than later during a
  campaign send.
* ``send_campaign_step`` is the entry point used by the campaign worker
  when ``Campaign.send_via == "mailchimp"``. It upserts every member's
  email into the audience, creates a regular Mailchimp campaign, sets
  the rendered HTML, and triggers the send. The Mailchimp campaign id
  is persisted on the CRM ``Campaign`` row so we can later fetch its
  report.
* ``sync_stats`` pulls the aggregate report and updates the local
  counters used by the campaign analytics view.

The transport (``MailchimpClient``) is injected so tests can substitute
a mock ``httpx`` transport without touching the service logic.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.campaigns.models import Campaign, CampaignMember, EmailTemplate
from src.email.branded_templates import (
    TenantBrandingHelper,
    render_campaign_wrapper,
)
from src.email.service import render_template
from src.integrations.mailchimp.client import (
    MailchimpClient,
    MailchimpError,
    split_api_key,
)
from src.integrations.mailchimp.models import MailchimpConnection

logger = logging.getLogger(__name__)


ClientFactory = Callable[[str, str], Awaitable[MailchimpClient]] | None


class MailchimpNotConnected(Exception):
    """Raised when an operation requires a connected Mailchimp account but none is set up."""


class MailchimpService:
    """Tenant-scoped Mailchimp operations.

    Pass ``client_factory`` from tests to inject a transport-mocked
    client without touching network code paths.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        client_factory: ClientFactory = None,
    ):
        self.db = db
        self._client_factory = client_factory

    async def _client(self, conn: MailchimpConnection) -> MailchimpClient:
        if self._client_factory is not None:
            return await self._client_factory(conn.api_key, conn.server_prefix)
        return MailchimpClient(conn.api_key, conn.server_prefix)

    # --- Connection lifecycle ------------------------------------

    async def get_connection(self, tenant_id: int) -> MailchimpConnection | None:
        result = await self.db.execute(
            select(MailchimpConnection).where(
                MailchimpConnection.tenant_id == tenant_id,
                MailchimpConnection.revoked_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def require_connection(self, tenant_id: int) -> MailchimpConnection:
        conn = await self.get_connection(tenant_id)
        if conn is None:
            raise MailchimpNotConnected(
                "Mailchimp is not connected for this tenant"
            )
        return conn

    async def connect(
        self,
        *,
        tenant_id: int,
        connected_by_id: int,
        api_key: str,
    ) -> MailchimpConnection:
        """Validate against ``/ping`` + ``/`` then upsert the per-tenant row.

        Re-running ``connect`` with a different key replaces the active
        credentials in place — we don't keep a history because the API
        key is the only secret and rotating it invalidates the prior
        one anyway.
        """
        api_key, server_prefix = split_api_key(api_key)
        client = (
            await self._client_factory(api_key, server_prefix)
            if self._client_factory is not None
            else MailchimpClient(api_key, server_prefix)
        )
        async with client as mc:
            await mc.ping()
            account = await mc.get_account()

        existing = await self.get_connection(tenant_id)
        now = datetime.now(UTC)
        if existing is not None:
            existing.api_key = api_key
            existing.server_prefix = server_prefix
            existing.connected_by_id = connected_by_id
            existing.connected_at = now
            existing.account_email = (account.get("email") or "")[:255] or None
            existing.account_login_id = str(account.get("account_id") or "")[:255] or None
            await self.db.flush()
            await self.db.refresh(existing)
            return existing

        conn = MailchimpConnection(
            tenant_id=tenant_id,
            api_key=api_key,
            server_prefix=server_prefix,
            connected_by_id=connected_by_id,
            connected_at=now,
            account_email=(account.get("email") or "")[:255] or None,
            account_login_id=str(account.get("account_id") or "")[:255] or None,
        )
        self.db.add(conn)
        await self.db.flush()
        await self.db.refresh(conn)
        return conn

    async def disconnect(self, tenant_id: int) -> bool:
        conn = await self.get_connection(tenant_id)
        if conn is None:
            return False
        conn.revoked_at = datetime.now(UTC)
        await self.db.flush()
        return True

    # --- Audiences -----------------------------------------------

    async def list_audiences(self, tenant_id: int) -> list[dict]:
        conn = await self.require_connection(tenant_id)
        async with await self._client(conn) as mc:
            payload = await mc.list_audiences()
        return [
            {
                "id": lst["id"],
                "name": lst.get("name", ""),
                "member_count": (lst.get("stats") or {}).get("member_count", 0),
            }
            for lst in payload.get("lists", [])
        ]

    async def set_default_audience(
        self, tenant_id: int, audience_id: str
    ) -> MailchimpConnection:
        conn = await self.require_connection(tenant_id)
        async with await self._client(conn) as mc:
            audience = await mc.get_audience(audience_id)
        conn.default_audience_id = audience_id
        conn.default_audience_name = (audience.get("name") or "")[:255] or None
        await self.db.flush()
        await self.db.refresh(conn)
        return conn

    # --- Campaign send -------------------------------------------

    async def _resolve_member_emails(
        self, campaign_id: int
    ) -> list[tuple[str, str | None, str | None]]:
        """Return ``(email, first_name, last_name)`` for every campaign member."""
        from src.contacts.models import Contact
        from src.leads.models import Lead

        result = await self.db.execute(
            select(CampaignMember).where(CampaignMember.campaign_id == campaign_id)
        )
        members = list(result.scalars().all())

        out: list[tuple[str, str | None, str | None]] = []
        for member in members:
            if member.member_type in ("contact", "contacts"):
                row = await self.db.execute(
                    select(Contact.email, Contact.first_name, Contact.last_name).where(
                        Contact.id == member.member_id
                    )
                )
            elif member.member_type in ("lead", "leads"):
                row = await self.db.execute(
                    select(Lead.email, Lead.first_name, Lead.last_name).where(
                        Lead.id == member.member_id
                    )
                )
            else:
                continue
            data = row.first()
            if data and data[0]:
                out.append((data[0], data[1], data[2]))
        return out

    async def send_campaign_step(
        self,
        *,
        campaign: Campaign,
        template_id: int,
        sent_by_id: int | None,
        tenant_id: int,
    ) -> dict:
        """Push members → audience, create + send a Mailchimp campaign.

        Returns a summary dict with the Mailchimp campaign id and the
        number of emails queued. The CRM ``Campaign`` row is updated
        with ``mailchimp_campaign_id`` and ``num_sent``.
        """
        conn = await self.require_connection(tenant_id)
        if not conn.default_audience_id:
            raise MailchimpNotConnected(
                "Mailchimp connection has no default audience selected"
            )

        tmpl_result = await self.db.execute(
            select(EmailTemplate).where(EmailTemplate.id == template_id)
        )
        template = tmpl_result.scalar_one_or_none()
        if template is None:
            raise ValueError(f"Template {template_id} not found")

        subject = render_template(template.subject_template, {}, is_html=False)
        body_html = render_template(template.body_template or "", {})

        branding = TenantBrandingHelper.get_default_branding()
        if sent_by_id:
            branding = await TenantBrandingHelper.get_branding_for_user(
                self.db, sent_by_id
            )
        unsubscribe_token = "*|UNSUB|*"
        wrapped = render_campaign_wrapper(
            branding=branding,
            campaign_body=body_html,
            unsubscribe_url=unsubscribe_token,
        )

        from_name = (branding.get("email_from_name") or "").strip() or "CRM"
        reply_to = (
            (branding.get("email_from_address") or "").strip()
            or conn.account_email
            or "no-reply@example.com"
        )

        # Idempotency guard — if a previous tick already kicked off the
        # Mailchimp send for this step but our outer transaction rolled
        # back before persisting num_sent, the row will still carry the
        # external campaign id. Don't re-fire the send in that case;
        # callers should use sync_stats to true-up the local counters.
        if campaign.mailchimp_campaign_id:
            logger.warning(
                "mailchimp send_campaign_step short-circuit: campaign %s "
                "already has mailchimp_campaign_id=%s — refusing to re-send",
                campaign.id,
                campaign.mailchimp_campaign_id,
            )
            return {
                "mailchimp_campaign_id": campaign.mailchimp_campaign_id,
                "emails_sent": 0,
                "skipped": "already_sent",
            }

        members = await self._resolve_member_emails(campaign.id)
        async with await self._client(conn) as mc:
            for email, first_name, last_name in members:
                merge: dict[str, str] = {}
                if first_name:
                    merge["FNAME"] = first_name
                if last_name:
                    merge["LNAME"] = last_name
                try:
                    await mc.upsert_member(
                        conn.default_audience_id,
                        email,
                        merge_fields=merge or None,
                    )
                except MailchimpError as exc:
                    # Mailchimp returns 400 with title="Member In
                    # Compliance State" for previously-unsubscribed or
                    # hard-bounced addresses. That's expected and we
                    # skip. Auth, quota, and unknown-shape failures
                    # mean the bulk send won't reach the right audience
                    # — re-raise so the worker marks the step failed
                    # instead of silently mailing a stale snapshot.
                    if exc.status_code == 400 and isinstance(exc.body, dict) and (
                        "compliance" in str(exc.body.get("title", "")).lower()
                    ):
                        logger.warning(
                            "mailchimp upsert skipped (compliance) email=%s body=%s",
                            email,
                            exc.body,
                        )
                        continue
                    raise

            created = await mc.create_regular_campaign(
                list_id=conn.default_audience_id,
                subject=subject,
                from_name=from_name,
                reply_to=reply_to,
                title=f"{campaign.name} — step {campaign.current_step + 1}",
            )
            mc_campaign_id = created["id"]
            await mc.set_campaign_content(mc_campaign_id, html=wrapped)

            # Persist + flush BEFORE actually sending. If the
            # transaction commits but the send call later raises, we'd
            # rather replay sync_stats than have Mailchimp deliver the
            # email twice on the next worker tick. The flush makes the
            # idempotency guard above effective for retries.
            campaign.mailchimp_campaign_id = mc_campaign_id
            await self.db.flush()

            await mc.send_campaign(mc_campaign_id)

        campaign.num_sent = (campaign.num_sent or 0) + len(members)

        now = datetime.now(UTC)
        member_result = await self.db.execute(
            select(CampaignMember).where(CampaignMember.campaign_id == campaign.id)
        )
        emails_sent = {e for e, _, _ in members}
        for member in member_result.scalars().all():
            from src.email.service import EmailService

            email_service = EmailService(self.db)
            member_email = await email_service.get_member_email(member)
            if member_email and member_email in emails_sent:
                member.status = "sent"
                member.sent_at = now

        await self.db.flush()
        return {
            "mailchimp_campaign_id": mc_campaign_id,
            "emails_sent": len(members),
        }

    # --- Stats ---------------------------------------------------

    async def sync_stats(
        self, *, campaign: Campaign, tenant_id: int
    ) -> dict:
        if not campaign.mailchimp_campaign_id:
            raise ValueError("Campaign has no mailchimp_campaign_id to sync from")
        conn = await self.require_connection(tenant_id)
        async with await self._client(conn) as mc:
            report = await mc.get_report(campaign.mailchimp_campaign_id)

        opens = report.get("opens") or {}
        clicks = report.get("clicks") or {}
        bounces = report.get("bounces") or {}
        unsubscribed = report.get("unsubscribed") or 0

        emails_sent = report.get("emails_sent", 0)
        if emails_sent:
            campaign.num_sent = emails_sent
        return {
            "campaign_id": campaign.id,
            "mailchimp_campaign_id": campaign.mailchimp_campaign_id,
            "emails_sent": emails_sent,
            "opens": opens.get("opens_total", 0),
            "unique_opens": opens.get("unique_opens", 0),
            "open_rate": opens.get("open_rate", 0.0),
            "clicks": clicks.get("clicks_total", 0),
            "unique_clicks": clicks.get("unique_clicks", 0),
            "click_rate": clicks.get("click_rate", 0.0),
            "bounces": (
                (bounces.get("hard_bounces") or 0)
                + (bounces.get("soft_bounces") or 0)
            ),
            "unsubscribes": unsubscribed,
        }
