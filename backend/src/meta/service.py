"""Meta (Facebook/Instagram Graph API) service layer.

Handles OAuth2 flow, page/Instagram data sync, and lead capture webhook processing.
Requires META_APP_ID and META_APP_SECRET for OAuth. Falls back to META_ACCESS_TOKEN for legacy.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.meta.models import CompanyMetaData, MetaCredential, MetaLeadCapture

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"
META_AUTH_URL = "https://www.facebook.com/v19.0/dialog/oauth"
META_TOKEN_URL = f"{GRAPH_API_BASE}/oauth/access_token"
META_SCOPES = "pages_show_list,pages_read_engagement,instagram_basic,leads_retrieval"


class MetaService:
    """Service for Meta/Facebook/Instagram Graph API integration."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # =========================================================================
    # OAuth2 Flow
    # =========================================================================

    def get_authorization_url(self, redirect_uri: str, state: str | None = None) -> str:
        """Build the Meta OAuth2 authorization URL."""
        params = {
            "client_id": settings.META_APP_ID,
            "redirect_uri": redirect_uri,
            "scope": META_SCOPES,
            "response_type": "code",
        }
        if state:
            params["state"] = state
        return f"{META_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str, user_id: int) -> MetaCredential:
        """Exchange authorization code for a long-lived access token."""
        # Short-lived token
        async with httpx.AsyncClient() as client:
            response = await client.get(META_TOKEN_URL, params={
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "redirect_uri": redirect_uri,
                "code": code,
            })
            response.raise_for_status()
            short_token_data = response.json()

            # Exchange for long-lived token (60 days)
            ll_response = await client.get(META_TOKEN_URL, params={
                "grant_type": "fb_exchange_token",
                "client_id": settings.META_APP_ID,
                "client_secret": settings.META_APP_SECRET,
                "fb_exchange_token": short_token_data["access_token"],
            })
            ll_response.raise_for_status()
            ll_data = ll_response.json()

        expiry = datetime.now(UTC) + timedelta(seconds=ll_data.get("expires_in", 5184000))

        # Upsert credential
        existing = await self.get_credential(user_id)
        if existing:
            existing.access_token = ll_data["access_token"]
            existing.token_expiry = expiry
            existing.scopes = META_SCOPES
            existing.is_active = True
            await self.db.flush()
            return existing

        credential = MetaCredential(
            user_id=user_id,
            access_token=ll_data["access_token"],
            token_expiry=expiry,
            scopes=META_SCOPES,
        )
        self.db.add(credential)
        await self.db.flush()
        return credential

    async def get_credential(self, user_id: int) -> MetaCredential | None:
        """Get stored Meta credential for a user."""
        result = await self.db.execute(
            select(MetaCredential).where(MetaCredential.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def disconnect(self, user_id: int) -> bool:
        """Remove Meta connection for a user."""
        credential = await self.get_credential(user_id)
        if not credential:
            return False
        await self.db.delete(credential)
        await self.db.flush()
        return True

    async def get_connection_status(self, user_id: int) -> dict[str, Any]:
        """Get Meta connection status including linked pages."""
        credential = await self.get_credential(user_id)
        if not credential or not credential.is_active:
            return {"connected": False, "scopes": None, "token_expiry": None, "pages": []}

        pages = []
        try:
            pages = await self._fetch_user_pages(credential.access_token)
        except Exception as e:
            logger.warning("Failed to fetch pages for user %s: %s", user_id, e)

        return {
            "connected": True,
            "scopes": credential.scopes,
            "token_expiry": credential.token_expiry,
            "pages": pages,
        }

    # =========================================================================
    # Facebook Page Sync
    # =========================================================================

    async def get_by_company(self, company_id: int) -> CompanyMetaData | None:
        """Get Meta data for a company."""
        result = await self.db.execute(
            select(CompanyMetaData).where(CompanyMetaData.company_id == company_id)
        )
        return result.scalar_one_or_none()

    async def sync_page(self, company_id: int, page_id: str) -> CompanyMetaData:
        """Sync Meta page data for a company via Graph API."""
        access_token = settings.META_ACCESS_TOKEN

        page_data = {}
        if access_token:
            try:
                page_data = await self._fetch_page_data(page_id, access_token)
            except Exception as e:
                logger.warning("Failed to fetch Meta page data for %s: %s", page_id, e)

        # Upsert
        existing = await self.get_by_company(company_id)
        if existing:
            existing.page_id = page_id
            existing.page_name = page_data.get("name", existing.page_name)
            existing.followers_count = page_data.get("followers_count", existing.followers_count)
            existing.likes_count = page_data.get("fan_count", existing.likes_count)
            existing.category = page_data.get("category", existing.category)
            existing.about = page_data.get("about", existing.about)
            existing.website = page_data.get("website", existing.website)
            existing.raw_json = page_data or existing.raw_json
            existing.last_synced_at = datetime.now(UTC)
            await self.db.flush()
            await self.db.refresh(existing)
            return existing
        else:
            meta = CompanyMetaData(
                company_id=company_id,
                page_id=page_id,
                page_name=page_data.get("name"),
                followers_count=page_data.get("followers_count"),
                likes_count=page_data.get("fan_count"),
                category=page_data.get("category"),
                about=page_data.get("about"),
                website=page_data.get("website"),
                raw_json=page_data or None,
                last_synced_at=datetime.now(UTC),
            )
            self.db.add(meta)
            await self.db.flush()
            await self.db.refresh(meta)
            return meta

    # =========================================================================
    # Instagram Sync
    # =========================================================================

    async def sync_instagram(self, company_id: int, page_id: str, access_token: str) -> CompanyMetaData | None:
        """Sync Instagram business account data linked to a Facebook page."""
        try:
            ig_data = await self._fetch_instagram_data(page_id, access_token)
        except Exception as e:
            logger.warning("Failed to fetch Instagram data for page %s: %s", page_id, e)
            return None

        if not ig_data:
            return None

        existing = await self.get_by_company(company_id)
        if not existing:
            return None

        existing.instagram_id = ig_data.get("id")
        existing.instagram_username = ig_data.get("username")
        existing.instagram_followers = ig_data.get("followers_count")
        existing.instagram_media_count = ig_data.get("media_count")
        existing.last_synced_at = datetime.now(UTC)
        await self.db.flush()
        await self.db.refresh(existing)
        return existing

    # =========================================================================
    # Lead Capture (Webhooks)
    # =========================================================================

    async def process_lead_webhook(self, payload: dict[str, Any]) -> list[MetaLeadCapture]:
        """Process incoming Meta Lead Ads webhook payload.

        Creates MetaLeadCapture records for each lead and optionally
        converts them to CRM leads if an access token is available.
        """
        captures = []
        for entry in payload.get("entry", []):
            page_id = str(entry.get("id", ""))
            for change in entry.get("changes", []):
                if change.get("field") != "leadgen":
                    continue
                value = change.get("value", {})
                leadgen_id = str(value.get("leadgen_id", ""))
                form_id = str(value.get("form_id", ""))
                ad_id = value.get("ad_id")

                # Skip duplicates
                existing = await self.db.execute(
                    select(MetaLeadCapture).where(MetaLeadCapture.leadgen_id == leadgen_id)
                )
                if existing.scalar_one_or_none():
                    continue

                # Fetch full lead data if token available
                lead_data = None
                access_token = settings.META_ACCESS_TOKEN
                if access_token and leadgen_id:
                    try:
                        lead_data = await self._fetch_lead_data(leadgen_id, access_token)
                    except Exception as e:
                        logger.warning("Failed to fetch lead data for %s: %s", leadgen_id, e)

                capture = MetaLeadCapture(
                    form_id=form_id,
                    leadgen_id=leadgen_id,
                    page_id=page_id,
                    ad_id=str(ad_id) if ad_id else None,
                    raw_data=lead_data,
                )
                self.db.add(capture)
                captures.append(capture)

        await self.db.flush()

        # Auto-create CRM leads from captured data
        for capture in captures:
            if capture.raw_data:
                lead_id = await self._create_lead_from_capture(capture)
                if lead_id:
                    capture.lead_id = lead_id
                    capture.processed = True

        await self.db.flush()
        return captures

    async def get_unprocessed_captures(self, page: int = 1, page_size: int = 50) -> list[MetaLeadCapture]:
        offset = (page - 1) * page_size
        result = await self.db.execute(
            select(MetaLeadCapture)
            .where(MetaLeadCapture.processed == False)
            .order_by(MetaLeadCapture.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        return list(result.scalars().all())

    # =========================================================================
    # CSV Export
    # =========================================================================

    async def export_csv(self, company_id: int) -> str | None:
        """Export Meta data as CSV string."""
        meta = await self.get_by_company(company_id)
        if not meta:
            return None

        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Field", "Value"])
        writer.writerow(["Page ID", meta.page_id or ""])
        writer.writerow(["Page Name", meta.page_name or ""])
        writer.writerow(["Followers", meta.followers_count or ""])
        writer.writerow(["Likes", meta.likes_count or ""])
        writer.writerow(["Category", meta.category or ""])
        writer.writerow(["About", meta.about or ""])
        writer.writerow(["Website", meta.website or ""])
        writer.writerow(["Instagram Username", meta.instagram_username or ""])
        writer.writerow(["Instagram Followers", meta.instagram_followers or ""])
        writer.writerow(["Instagram Media Count", meta.instagram_media_count or ""])
        writer.writerow(["Last Synced", str(meta.last_synced_at or "")])
        return output.getvalue()

    # =========================================================================
    # Private helpers
    # =========================================================================

    async def _fetch_page_data(self, page_id: str, access_token: str) -> dict:
        """Fetch page data from Meta Graph API."""
        fields = "id,name,about,category,fan_count,followers_count,website,link"
        url = f"{GRAPH_API_BASE}/{page_id}"
        params = {"fields": fields, "access_token": access_token}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def _fetch_instagram_data(self, page_id: str, access_token: str) -> dict | None:
        """Fetch Instagram business account linked to a Facebook page."""
        url = f"{GRAPH_API_BASE}/{page_id}"
        params = {
            "fields": "instagram_business_account{id,username,followers_count,media_count}",
            "access_token": access_token,
        }
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("instagram_business_account")

    async def _fetch_user_pages(self, access_token: str) -> list[dict[str, Any]]:
        """Fetch Facebook pages the user manages."""
        url = f"{GRAPH_API_BASE}/me/accounts"
        params = {"fields": "id,name,category,fan_count", "access_token": access_token}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json().get("data", [])

    async def _fetch_lead_data(self, leadgen_id: str, access_token: str) -> dict:
        """Fetch full lead data from Meta Lead Ads API."""
        url = f"{GRAPH_API_BASE}/{leadgen_id}"
        params = {"access_token": access_token}
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def _create_lead_from_capture(self, capture: MetaLeadCapture) -> int | None:
        """Convert a MetaLeadCapture into a CRM Lead."""
        from src.leads.models import Lead

        if not capture.raw_data:
            return None

        field_data = capture.raw_data.get("field_data", [])
        fields = {f["name"]: f["values"][0] if f.get("values") else "" for f in field_data}

        # Map common Meta lead form fields
        first_name = fields.get("first_name", fields.get("full_name", "Unknown"))
        last_name = fields.get("last_name", "")
        email = fields.get("email", "")
        phone = fields.get("phone_number", fields.get("phone", ""))
        company = fields.get("company_name", fields.get("company", ""))

        lead = Lead(
            first_name=first_name,
            last_name=last_name,
            email=email or None,
            phone=phone or None,
            company=company or None,
            source="meta_lead_ads",
            status="new",
        )
        self.db.add(lead)
        await self.db.flush()
        return lead.id
