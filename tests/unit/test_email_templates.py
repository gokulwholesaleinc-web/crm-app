"""
Unit tests for email templates and campaign steps endpoints.

Tests for CRUD operations on email templates and campaign step sequences.
"""

import pytest
from datetime import date, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.campaigns.models import Campaign, EmailTemplate, EmailCampaignStep


@pytest.fixture
async def test_campaign(db_session: AsyncSession, test_user: User) -> Campaign:
    """Create a test campaign."""
    campaign = Campaign(
        name="Email Drip Campaign",
        campaign_type="email",
        status="planned",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)
    return campaign


@pytest.fixture
async def test_email_template(db_session: AsyncSession, test_user: User) -> EmailTemplate:
    """Create a test email template."""
    template = EmailTemplate(
        name="Welcome Email",
        subject_template="Welcome to {{company_name}}!",
        body_template="<h1>Hello {{name}}</h1><p>Welcome aboard!</p>",
        category="onboarding",
        created_by_id=test_user.id,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


class TestEmailTemplatesCRUD:
    """Tests for email template CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_create_email_template(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating a new email template."""
        response = await client.post(
            "/api/campaigns/templates",
            headers=auth_headers,
            json={
                "name": "Follow Up Template",
                "subject_template": "Following up on our conversation",
                "body_template": "<p>Hi {{name}}, just checking in...</p>",
                "category": "follow_up",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Follow Up Template"
        assert data["subject_template"] == "Following up on our conversation"
        assert data["category"] == "follow_up"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_email_template_minimal(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating template with only required fields."""
        response = await client.post(
            "/api/campaigns/templates",
            headers=auth_headers,
            json={
                "name": "Simple Template",
                "subject_template": "Hello",
                "body_template": "Body text",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Simple Template"
        assert data["category"] is None

    @pytest.mark.asyncio
    async def test_list_email_templates(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_email_template: EmailTemplate,
    ):
        """Test listing email templates."""
        response = await client.get(
            "/api/campaigns/templates",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(t["id"] == test_email_template.id for t in data)

    @pytest.mark.asyncio
    async def test_list_templates_filter_by_category(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_email_template: EmailTemplate,
    ):
        """Test filtering templates by category."""
        response = await client.get(
            "/api/campaigns/templates",
            headers=auth_headers,
            params={"category": "onboarding"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(t["category"] == "onboarding" for t in data)

    @pytest.mark.asyncio
    async def test_get_email_template(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_email_template: EmailTemplate,
    ):
        """Test getting an email template by ID."""
        response = await client.get(
            f"/api/campaigns/templates/{test_email_template.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_email_template.id
        assert data["name"] == "Welcome Email"

    @pytest.mark.asyncio
    async def test_get_email_template_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting non-existent template returns 404."""
        response = await client.get(
            "/api/campaigns/templates/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_email_template(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_email_template: EmailTemplate,
    ):
        """Test updating an email template."""
        response = await client.put(
            f"/api/campaigns/templates/{test_email_template.id}",
            headers=auth_headers,
            json={
                "name": "Updated Welcome Email",
                "subject_template": "Welcome back!",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Welcome Email"
        assert data["subject_template"] == "Welcome back!"
        # Unchanged fields stay the same
        assert data["body_template"] == test_email_template.body_template

    @pytest.mark.asyncio
    async def test_delete_email_template(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test deleting an email template."""
        template = EmailTemplate(
            name="To Delete",
            subject_template="Delete me",
            body_template="Goodbye",
            created_by_id=test_user.id,
        )
        db_session.add(template)
        await db_session.commit()
        await db_session.refresh(template)
        template_id = template.id

        response = await client.delete(
            f"/api/campaigns/templates/{template_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        result = await db_session.execute(
            select(EmailTemplate).where(EmailTemplate.id == template_id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_template_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test deleting non-existent template returns 404."""
        response = await client.delete(
            "/api/campaigns/templates/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestEmailTemplatesUnauthorized:
    """Tests for unauthorized access to email template endpoints."""

    @pytest.mark.asyncio
    async def test_create_template_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.post(
            "/api/campaigns/templates",
            json={"name": "Test", "subject_template": "s", "body_template": "b"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_templates_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.get("/api/campaigns/templates")
        assert response.status_code == 401


class TestCampaignSteps:
    """Tests for campaign step endpoints."""

    @pytest.mark.asyncio
    async def test_add_campaign_step(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
        test_email_template: EmailTemplate,
    ):
        """Test adding a step to a campaign."""
        response = await client.post(
            f"/api/campaigns/{test_campaign.id}/steps",
            headers=auth_headers,
            json={
                "template_id": test_email_template.id,
                "delay_days": 0,
                "step_order": 1,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["campaign_id"] == test_campaign.id
        assert data["template_id"] == test_email_template.id
        assert data["step_order"] == 1
        assert data["delay_days"] == 0

    @pytest.mark.asyncio
    async def test_get_campaign_steps(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
        test_email_template: EmailTemplate,
    ):
        """Test getting campaign steps."""
        # Create steps
        step1 = EmailCampaignStep(
            campaign_id=test_campaign.id,
            template_id=test_email_template.id,
            delay_days=0,
            step_order=1,
        )
        step2 = EmailCampaignStep(
            campaign_id=test_campaign.id,
            template_id=test_email_template.id,
            delay_days=3,
            step_order=2,
        )
        db_session.add_all([step1, step2])
        await db_session.commit()

        response = await client.get(
            f"/api/campaigns/{test_campaign.id}/steps",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["step_order"] == 1
        assert data[1]["step_order"] == 2

    @pytest.mark.asyncio
    async def test_update_campaign_step(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
        test_email_template: EmailTemplate,
    ):
        """Test updating a campaign step."""
        step = EmailCampaignStep(
            campaign_id=test_campaign.id,
            template_id=test_email_template.id,
            delay_days=1,
            step_order=1,
        )
        db_session.add(step)
        await db_session.commit()
        await db_session.refresh(step)

        response = await client.put(
            f"/api/campaigns/{test_campaign.id}/steps/{step.id}",
            headers=auth_headers,
            json={"delay_days": 5, "step_order": 2},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["delay_days"] == 5
        assert data["step_order"] == 2

    @pytest.mark.asyncio
    async def test_delete_campaign_step(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
        test_email_template: EmailTemplate,
    ):
        """Test deleting a campaign step."""
        step = EmailCampaignStep(
            campaign_id=test_campaign.id,
            template_id=test_email_template.id,
            delay_days=0,
            step_order=1,
        )
        db_session.add(step)
        await db_session.commit()
        await db_session.refresh(step)
        step_id = step.id

        response = await client.delete(
            f"/api/campaigns/{test_campaign.id}/steps/{step_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        result = await db_session.execute(
            select(EmailCampaignStep).where(EmailCampaignStep.id == step_id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_add_step_campaign_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_email_template: EmailTemplate,
    ):
        """Test adding step to non-existent campaign."""
        response = await client.post(
            "/api/campaigns/99999/steps",
            headers=auth_headers,
            json={
                "template_id": test_email_template.id,
                "delay_days": 0,
                "step_order": 1,
            },
        )

        assert response.status_code == 404


class TestCampaignExecution:
    """Tests for campaign execution endpoint."""

    @pytest.mark.asyncio
    async def test_execute_campaign(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
    ):
        """Test triggering campaign execution."""
        response = await client.post(
            f"/api/campaigns/{test_campaign.id}/execute",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"
        assert "message" in data

    @pytest.mark.asyncio
    async def test_execute_campaign_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test executing non-existent campaign."""
        response = await client.post(
            "/api/campaigns/99999/execute",
            headers=auth_headers,
        )

        assert response.status_code == 404
