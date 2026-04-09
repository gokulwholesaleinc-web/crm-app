"""Tests for LinkedIn campaign workflow: CSV detection, import-to-campaign, throttle, volume stats."""

import pytest
from datetime import date, datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.campaigns.models import Campaign, CampaignMember, EmailTemplate, EmailCampaignStep
from src.contacts.models import Contact
from src.leads.models import Lead, LeadSource
from src.email.models import EmailQueue, EmailSettings
from src.import_export.csv_handler import detect_linkedin_format, _normalize_header, CSVHandler


# =========================================================================
# LinkedIn CSV Detection
# =========================================================================

class TestLinkedInCSVDetection:
    """Tests for LinkedIn Sales Navigator CSV format detection."""

    def test_detect_linkedin_format_positive(self):
        """Should detect LinkedIn CSV when 4+ signature headers present."""
        headers = ["First Name", "Last Name", "Company", "Title", "Email", "LinkedIn Profile URL"]
        assert detect_linkedin_format(headers) is True

    def test_detect_linkedin_format_minimal_match(self):
        """Should detect with exactly 4 matching headers."""
        headers = ["First Name", "Last Name", "Email", "Geography"]
        assert detect_linkedin_format(headers) is True

    def test_detect_linkedin_format_negative(self):
        """Should not detect with fewer than 4 matching headers."""
        headers = ["First Name", "Last Name", "Phone"]
        assert detect_linkedin_format(headers) is False

    def test_detect_linkedin_format_empty(self):
        """Should not detect with empty headers."""
        assert detect_linkedin_format([]) is False

    def test_detect_linkedin_format_generic_csv(self):
        """Should not detect for generic CRM CSV exports."""
        headers = ["first_name", "last_name", "email", "phone", "city", "state"]
        assert detect_linkedin_format(headers) is False

    def test_detect_linkedin_with_extra_headers(self):
        """Should detect LinkedIn even with extra non-LinkedIn headers."""
        headers = [
            "First Name", "Last Name", "Company", "Title",
            "LinkedIn Profile URL", "Email", "Geography", "Industry",
            "Custom Field 1", "Notes",
        ]
        assert detect_linkedin_format(headers) is True


class TestLinkedInCSVPreview:
    """Tests for LinkedIn CSV preview with source detection."""

    @pytest.mark.asyncio
    async def test_preview_linkedin_csv(self, client: AsyncClient, auth_headers: dict):
        """Should detect linkedin_sales_navigator in preview."""
        csv_content = (
            "First Name,Last Name,Company,Title,LinkedIn Profile URL,Email,Geography,Industry\n"
            "Alice,Wonderland,Acme Corp,CEO,https://linkedin.com/in/alice,alice@acme.com,New York,Tech\n"
        )
        import io
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        response = await client.post(
            "/api/import-export/preview/contacts",
            headers=auth_headers,
            files=files,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["source_detected"] == "linkedin_sales_navigator"

    @pytest.mark.asyncio
    async def test_preview_leads_linkedin_csv(self, client: AsyncClient, auth_headers: dict):
        """Should detect LinkedIn format for leads preview."""
        csv_content = (
            "First Name,Last Name,Company,Title,Email,Geography,Industry,LinkedIn Profile URL\n"
            "Bob,Builder,BuildCo,CTO,bob@build.co,Chicago,Construction,https://linkedin.com/in/bob\n"
        )
        import io
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        response = await client.post(
            "/api/import-export/preview/leads",
            headers=auth_headers,
            files=files,
        )
        assert response.status_code == 200
        assert response.json()["source_detected"] == "linkedin_sales_navigator"

    @pytest.mark.asyncio
    async def test_preview_non_linkedin_csv(self, client: AsyncClient, auth_headers: dict):
        """Should return None source for generic CSV."""
        csv_content = "first_name,last_name,email,phone\nJohn,Doe,john@test.com,555-1234\n"
        import io
        files = {"file": ("test.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        response = await client.post(
            "/api/import-export/preview/contacts",
            headers=auth_headers,
            files=files,
        )
        assert response.status_code == 200
        assert response.json()["source_detected"] is None


class TestLinkedInCSVImport:
    """Tests for LinkedIn CSV import with source tagging."""

    @pytest.mark.asyncio
    async def test_import_linkedin_leads_tags_source(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead_source: LeadSource,
    ):
        """LinkedIn leads import should auto-set source_details."""
        csv_content = (
            "First Name,Last Name,Company,Title,Email,Geography,Industry,LinkedIn Profile URL\n"
            f"Alice,LinkedIn,Acme,CEO,alice_linkedin@example.com,NYC,Tech,https://linkedin.com/in/alice\n"
        )
        import io
        files = {"file": ("leads.csv", io.BytesIO(csv_content.encode()), "text/csv")}
        response = await client.post(
            "/api/import-export/import/leads",
            headers=auth_headers,
            files=files,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["imported_count"] >= 1

        result = await db_session.execute(
            select(Lead).where(Lead.email == "alice_linkedin@example.com")
        )
        lead = result.scalar_one_or_none()
        assert lead is not None
        assert lead.source_details == "linkedin_sales_navigator"


# =========================================================================
# Import-to-Campaign Flow
# =========================================================================

class TestCreateFromImport:
    """Tests for POST /api/campaigns/create-from-import."""

    @pytest.mark.asyncio
    async def test_create_campaign_from_import(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Should create a campaign with members from import IDs."""
        response = await client.post(
            "/api/campaigns/create-from-import",
            headers=auth_headers,
            json={
                "name": "LinkedIn Outreach Q2",
                "member_ids": [test_contact.id],
                "member_type": "contacts",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "LinkedIn Outreach Q2"
        assert data["campaign_type"] == "email"
        assert data["status"] == "planned"

        # Verify member was added
        result = await db_session.execute(
            select(CampaignMember).where(CampaignMember.campaign_id == data["id"])
        )
        members = list(result.scalars().all())
        assert len(members) == 1
        assert members[0].member_id == test_contact.id
        assert members[0].member_type == "contacts"

    @pytest.mark.asyncio
    async def test_create_campaign_from_import_with_template(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Should create first step when template_id is provided."""
        template = EmailTemplate(
            name="Welcome Email",
            subject_template="Welcome {{first_name}}!",
            body_template="<p>Hello {{first_name}}</p>",
            created_by_id=test_user.id,
        )
        db_session.add(template)
        await db_session.flush()

        response = await client.post(
            "/api/campaigns/create-from-import",
            headers=auth_headers,
            json={
                "name": "LinkedIn Outreach with Template",
                "member_ids": [test_contact.id],
                "member_type": "contacts",
                "template_id": template.id,
                "delay_days": 2,
            },
        )
        assert response.status_code == 201
        campaign_id = response.json()["id"]

        # Verify step was created
        result = await db_session.execute(
            select(EmailCampaignStep).where(EmailCampaignStep.campaign_id == campaign_id)
        )
        steps = list(result.scalars().all())
        assert len(steps) == 1
        assert steps[0].template_id == template.id
        assert steps[0].delay_days == 2
        assert steps[0].step_order == 1

    @pytest.mark.asyncio
    async def test_create_campaign_from_import_with_leads(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Should work with lead member_type."""
        response = await client.post(
            "/api/campaigns/create-from-import",
            headers=auth_headers,
            json={
                "name": "Lead Nurture Campaign",
                "member_ids": [test_lead.id],
                "member_type": "leads",
            },
        )
        assert response.status_code == 201

        result = await db_session.execute(
            select(CampaignMember).where(
                CampaignMember.campaign_id == response.json()["id"]
            )
        )
        members = list(result.scalars().all())
        assert len(members) == 1
        assert members[0].member_type == "leads"

    @pytest.mark.asyncio
    async def test_create_campaign_empty_members(
        self,
        client: AsyncClient,
        auth_headers: dict,
    ):
        """Should create campaign with zero members when list is empty."""
        response = await client.post(
            "/api/campaigns/create-from-import",
            headers=auth_headers,
            json={
                "name": "Empty Campaign",
                "member_ids": [],
                "member_type": "contacts",
            },
        )
        assert response.status_code == 201


# =========================================================================
# Email Throttle Logic
# =========================================================================

class TestEmailThrottle:
    """Tests for EmailThrottleService."""

    @pytest.mark.asyncio
    async def test_default_daily_limit(self, db_session: AsyncSession):
        """Default daily limit should be 200."""
        from src.email.throttle import EmailThrottleService
        throttle = EmailThrottleService(db_session)
        limit = await throttle.get_effective_daily_limit()
        assert limit == 200

    @pytest.mark.asyncio
    async def test_can_send_when_under_limit(self, db_session: AsyncSession):
        """Should return True when no emails sent today."""
        from src.email.throttle import EmailThrottleService
        throttle = EmailThrottleService(db_session)
        assert await throttle.can_send() is True

    @pytest.mark.asyncio
    async def test_warmup_day_1_limit(self, db_session: AsyncSession):
        """Warmup day 1-3 should return 20/day."""
        from src.email.throttle import EmailThrottleService
        throttle = EmailThrottleService(db_session)
        settings = await throttle.get_settings()
        settings.warmup_enabled = True
        settings.warmup_start_date = date.today()
        settings.warmup_target_daily = 200
        await db_session.flush()

        limit = await throttle.get_effective_daily_limit()
        assert limit == 20

    @pytest.mark.asyncio
    async def test_warmup_day_5_limit(self, db_session: AsyncSession):
        """Warmup day 4-6 should return 40/day."""
        from src.email.throttle import EmailThrottleService
        throttle = EmailThrottleService(db_session)
        settings = await throttle.get_settings()
        settings.warmup_enabled = True
        settings.warmup_start_date = date.today() - timedelta(days=4)
        settings.warmup_target_daily = 200
        await db_session.flush()

        limit = await throttle.get_effective_daily_limit()
        assert limit == 40

    @pytest.mark.asyncio
    async def test_warmup_day_8_limit(self, db_session: AsyncSession):
        """Warmup day 7-9 should return 60/day."""
        from src.email.throttle import EmailThrottleService
        throttle = EmailThrottleService(db_session)
        settings = await throttle.get_settings()
        settings.warmup_enabled = True
        settings.warmup_start_date = date.today() - timedelta(days=7)
        settings.warmup_target_daily = 200
        await db_session.flush()

        limit = await throttle.get_effective_daily_limit()
        assert limit == 60

    @pytest.mark.asyncio
    async def test_warmup_day_10_plus_ramp(self, db_session: AsyncSession):
        """Warmup after day 9 should increase by 20% per day."""
        from src.email.throttle import EmailThrottleService
        throttle = EmailThrottleService(db_session)
        settings = await throttle.get_settings()
        settings.warmup_enabled = True
        settings.warmup_start_date = date.today() - timedelta(days=9)
        settings.warmup_target_daily = 200
        await db_session.flush()

        limit = await throttle.get_effective_daily_limit()
        # Day 10: 60 * 1.2^1 = 72
        assert limit == 72

    @pytest.mark.asyncio
    async def test_warmup_caps_at_target(self, db_session: AsyncSession):
        """Warmup limit should never exceed target."""
        from src.email.throttle import EmailThrottleService
        throttle = EmailThrottleService(db_session)
        settings = await throttle.get_settings()
        settings.warmup_enabled = True
        settings.warmup_start_date = date.today() - timedelta(days=30)
        settings.warmup_target_daily = 100
        await db_session.flush()

        limit = await throttle.get_effective_daily_limit()
        assert limit <= 100

    @pytest.mark.asyncio
    async def test_get_volume_stats(self, db_session: AsyncSession):
        """Volume stats should return correct structure."""
        from src.email.throttle import EmailThrottleService
        throttle = EmailThrottleService(db_session)
        stats = await throttle.get_volume_stats()

        assert "sent_today" in stats
        assert "daily_limit" in stats
        assert "warmup_enabled" in stats
        assert "remaining_today" in stats
        assert stats["sent_today"] == 0
        assert stats["remaining_today"] == 200

    @pytest.mark.asyncio
    async def test_update_settings(self, db_session: AsyncSession):
        """Should update email settings."""
        from src.email.throttle import EmailThrottleService
        throttle = EmailThrottleService(db_session)
        settings = await throttle.update_settings(
            daily_send_limit=500,
            warmup_enabled=True,
            warmup_start_date=date.today(),
            warmup_target_daily=300,
        )
        assert settings.daily_send_limit == 500
        assert settings.warmup_enabled is True
        assert settings.warmup_start_date == date.today()
        assert settings.warmup_target_daily == 300


# =========================================================================
# Volume Stats Endpoint
# =========================================================================

class TestVolumeStatsEndpoint:
    """Tests for GET /api/email/volume-stats."""

    @pytest.mark.asyncio
    async def test_get_volume_stats(self, client: AsyncClient, auth_headers: dict):
        """Should return volume stats."""
        response = await client.get("/api/email/volume-stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "sent_today" in data
        assert "daily_limit" in data
        assert "remaining_today" in data
        assert data["sent_today"] == 0

    @pytest.mark.asyncio
    async def test_volume_stats_with_warmup(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict,
    ):
        """Should show warmup info when warmup is enabled."""
        settings = EmailSettings(
            warmup_enabled=True,
            warmup_start_date=date.today(),
            warmup_target_daily=200,
        )
        db_session.add(settings)
        await db_session.flush()

        response = await client.get("/api/email/volume-stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["warmup_enabled"] is True
        assert data["warmup_day"] == 1
        assert data["warmup_current_limit"] == 20


# =========================================================================
# Email Settings Endpoints
# =========================================================================

class TestEmailSettingsEndpoints:
    """Tests for /api/settings/email and /api/email/settings."""

    @pytest.mark.asyncio
    async def test_get_email_settings(self, client: AsyncClient, manager_auth_headers: dict):
        """Should return default email settings (manager+ only)."""
        response = await client.get("/api/settings/email", headers=manager_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["daily_send_limit"] == 200
        assert data["warmup_enabled"] is False

    @pytest.mark.asyncio
    async def test_update_email_settings(self, client: AsyncClient, admin_auth_headers: dict):
        """Should update and return email settings (superuser/admin only)."""
        response = await client.put(
            "/api/settings/email",
            headers=admin_auth_headers,
            json={
                "daily_send_limit": 500,
                "warmup_enabled": True,
                "warmup_start_date": str(date.today()),
                "warmup_target_daily": 300,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["daily_send_limit"] == 500
        assert data["warmup_enabled"] is True
        assert data["warmup_target_daily"] == 300

    @pytest.mark.asyncio
    async def test_get_settings_via_email_router(self, client: AsyncClient, auth_headers: dict):
        """Should also work via /api/email/settings."""
        response = await client.get("/api/email/settings", headers=auth_headers)
        assert response.status_code == 200
        assert "daily_send_limit" in response.json()

    @pytest.mark.asyncio
    async def test_update_settings_via_email_router(self, client: AsyncClient, auth_headers: dict):
        """Should also work via /api/email/settings."""
        response = await client.put(
            "/api/email/settings",
            headers=auth_headers,
            json={"daily_send_limit": 100},
        )
        assert response.status_code == 200
        assert response.json()["daily_send_limit"] == 100
