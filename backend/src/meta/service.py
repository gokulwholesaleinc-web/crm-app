"""Meta (Facebook Graph API) service layer."""
import logging
from datetime import datetime, timezone
from typing import Optional
import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.config import settings
from src.meta.models import CompanyMetaData

logger = logging.getLogger(__name__)


class MetaService:
    """Service for Meta/Facebook Graph API integration."""

    GRAPH_API_BASE = "https://graph.facebook.com/v19.0"

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_company(self, company_id: int) -> Optional[CompanyMetaData]:
        """Get Meta data for a company."""
        result = await self.db.execute(
            select(CompanyMetaData).where(CompanyMetaData.company_id == company_id)
        )
        return result.scalar_one_or_none()

    async def sync_page(self, company_id: int, page_id: str) -> CompanyMetaData:
        """Sync Meta page data for a company via Graph API."""
        access_token = getattr(settings, "META_ACCESS_TOKEN", "")

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
            existing.last_synced_at = datetime.now(timezone.utc)
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
                last_synced_at=datetime.now(timezone.utc),
            )
            self.db.add(meta)
            await self.db.flush()
            await self.db.refresh(meta)
            return meta

    async def _fetch_page_data(self, page_id: str, access_token: str) -> dict:
        """Fetch page data from Meta Graph API."""
        fields = "id,name,about,category,fan_count,followers_count,website,link"
        url = f"{self.GRAPH_API_BASE}/{page_id}"
        params = {"fields": fields, "access_token": access_token}

        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    async def export_csv(self, company_id: int) -> Optional[str]:
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
        writer.writerow(["Last Synced", str(meta.last_synced_at or "")])
        return output.getvalue()
