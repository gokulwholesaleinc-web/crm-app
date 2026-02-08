"""
Unit tests for campaigns CRUD endpoints.

Tests for list, create, get, update, delete, campaign member operations,
email templates, campaign steps, stats, and execute.
"""

import pytest
from datetime import date, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.campaigns.models import Campaign, CampaignMember, EmailTemplate, EmailCampaignStep
from src.contacts.models import Contact
from src.leads.models import Lead


@pytest.fixture
async def test_campaign(db_session: AsyncSession, test_user: User) -> Campaign:
    """Create a test campaign."""
    campaign = Campaign(
        name="Test Email Campaign",
        description="A test marketing campaign",
        campaign_type="email",
        status="planned",
        start_date=date.today(),
        end_date=date.today() + timedelta(days=30),
        budget_amount=5000.0,
        budget_currency="USD",
        target_audience="Enterprise customers",
        expected_revenue=50000.0,
        expected_response=100,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)
    return campaign


class TestCampaignsList:
    """Tests for campaigns list endpoint with pagination."""

    @pytest.mark.asyncio
    async def test_list_campaigns_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test listing campaigns when none exist."""
        response = await client.get("/api/campaigns", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_campaigns_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
    ):
        """Test listing campaigns with existing data."""
        response = await client.get("/api/campaigns", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1
        assert any(c["id"] == test_campaign.id for c in data["items"])

    @pytest.mark.asyncio
    async def test_list_campaigns_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test campaigns pagination."""
        # Create multiple campaigns
        for i in range(15):
            campaign = Campaign(
                name=f"Campaign {i}",
                campaign_type="email",
                status="planned",
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(campaign)
        await db_session.commit()

        # First page
        response = await client.get(
            "/api/campaigns",
            headers=auth_headers,
            params={"page": 1, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["page"] == 1
        assert data["total"] == 15

        # Second page
        response = await client.get(
            "/api/campaigns",
            headers=auth_headers,
            params={"page": 2, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5
        assert data["page"] == 2

    @pytest.mark.asyncio
    async def test_list_campaigns_filter_by_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
    ):
        """Test filtering campaigns by type."""
        response = await client.get(
            "/api/campaigns",
            headers=auth_headers,
            params={"campaign_type": "email"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(c["campaign_type"] == "email" for c in data["items"])

    @pytest.mark.asyncio
    async def test_list_campaigns_filter_by_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
    ):
        """Test filtering campaigns by status."""
        response = await client.get(
            "/api/campaigns",
            headers=auth_headers,
            params={"status": "planned"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(c["status"] == "planned" for c in data["items"])

    @pytest.mark.asyncio
    async def test_list_campaigns_search(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
    ):
        """Test searching campaigns."""
        response = await client.get(
            "/api/campaigns",
            headers=auth_headers,
            params={"search": "Email Campaign"},
        )

        assert response.status_code == 200
        data = response.json()
        assert any(c["id"] == test_campaign.id for c in data["items"])


class TestCampaignsCreate:
    """Tests for campaign creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_campaign_success(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test successful campaign creation."""
        response = await client.post(
            "/api/campaigns",
            headers=auth_headers,
            json={
                "name": "New Product Launch",
                "description": "Campaign for new product launch",
                "campaign_type": "webinar",
                "status": "planned",
                "start_date": date.today().isoformat(),
                "end_date": (date.today() + timedelta(days=14)).isoformat(),
                "budget_amount": 10000.0,
                "budget_currency": "USD",
                "target_audience": "Small businesses",
                "expected_revenue": 100000.0,
                "expected_response": 200,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Product Launch"
        assert data["campaign_type"] == "webinar"
        assert data["budget_amount"] == 10000.0
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_campaign_minimal(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating campaign with minimal required fields."""
        response = await client.post(
            "/api/campaigns",
            headers=auth_headers,
            json={
                "name": "Minimal Campaign",
                "campaign_type": "email",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal Campaign"
        assert data["status"] == "planned"  # Default
        assert data["budget_currency"] == "USD"  # Default

    @pytest.mark.asyncio
    async def test_create_campaign_missing_name(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating campaign without name fails."""
        response = await client.post(
            "/api/campaigns",
            headers=auth_headers,
            json={
                "campaign_type": "email",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_campaign_missing_type(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating campaign without type fails."""
        response = await client.post(
            "/api/campaigns",
            headers=auth_headers,
            json={
                "name": "No Type Campaign",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_campaign_with_all_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test creating campaign with all fields populated."""
        response = await client.post(
            "/api/campaigns",
            headers=auth_headers,
            json={
                "name": "Complete Campaign",
                "description": "A fully specified campaign",
                "campaign_type": "event",
                "status": "active",
                "start_date": date.today().isoformat(),
                "end_date": (date.today() + timedelta(days=60)).isoformat(),
                "budget_amount": 25000.0,
                "actual_cost": 5000.0,
                "budget_currency": "EUR",
                "target_audience": "Mid-market companies",
                "expected_revenue": 200000.0,
                "expected_response": 500,
                "owner_id": test_user.id,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["budget_currency"] == "EUR"
        assert data["status"] == "active"
        assert data["expected_response"] == 500


class TestCampaignsGetById:
    """Tests for get campaign by ID endpoint."""

    @pytest.mark.asyncio
    async def test_get_campaign_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
    ):
        """Test getting campaign by ID."""
        response = await client.get(
            f"/api/campaigns/{test_campaign.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_campaign.id
        assert data["name"] == test_campaign.name
        assert data["campaign_type"] == test_campaign.campaign_type

    @pytest.mark.asyncio
    async def test_get_campaign_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting non-existent campaign."""
        response = await client.get(
            "/api/campaigns/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestCampaignsUpdate:
    """Tests for campaign update endpoint."""

    @pytest.mark.asyncio
    async def test_update_campaign_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
    ):
        """Test updating campaign."""
        response = await client.patch(
            f"/api/campaigns/{test_campaign.id}",
            headers=auth_headers,
            json={
                "name": "Updated Campaign Name",
                "status": "active",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Campaign Name"
        assert data["status"] == "active"
        # Other fields unchanged
        assert data["campaign_type"] == test_campaign.campaign_type

    @pytest.mark.asyncio
    async def test_update_campaign_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test updating non-existent campaign."""
        response = await client.patch(
            "/api/campaigns/99999",
            headers=auth_headers,
            json={"name": "Test"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_campaign_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
    ):
        """Test updating campaign status."""
        response = await client.patch(
            f"/api/campaigns/{test_campaign.id}",
            headers=auth_headers,
            json={"status": "completed"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

    @pytest.mark.asyncio
    async def test_update_campaign_results(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
    ):
        """Test updating campaign results."""
        response = await client.patch(
            f"/api/campaigns/{test_campaign.id}",
            headers=auth_headers,
            json={
                "actual_revenue": 75000.0,
                "num_sent": 1000,
                "num_responses": 150,
                "num_converted": 25,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["actual_revenue"] == 75000.0
        assert data["num_sent"] == 1000
        assert data["num_responses"] == 150
        assert data["num_converted"] == 25
        # Check calculated rates
        assert data["response_rate"] == 15.0  # 150/1000 * 100
        assert abs(data["conversion_rate"] - 16.67) < 0.1  # ~25/150 * 100


class TestCampaignsDelete:
    """Tests for campaign delete endpoint."""

    @pytest.mark.asyncio
    async def test_delete_campaign_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test deleting campaign."""
        # Create a campaign to delete
        campaign = Campaign(
            name="To Delete Campaign",
            campaign_type="email",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(campaign)
        await db_session.commit()
        await db_session.refresh(campaign)
        campaign_id = campaign.id

        response = await client.delete(
            f"/api/campaigns/{campaign_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify deletion
        result = await db_session.execute(
            select(Campaign).where(Campaign.id == campaign_id)
        )
        deleted_campaign = result.scalar_one_or_none()
        assert deleted_campaign is None

    @pytest.mark.asyncio
    async def test_delete_campaign_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test deleting non-existent campaign."""
        response = await client.delete(
            "/api/campaigns/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestCampaignStats:
    """Tests for campaign statistics endpoint."""

    @pytest.mark.asyncio
    async def test_get_campaign_stats(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
    ):
        """Test getting campaign statistics."""
        response = await client.get(
            f"/api/campaigns/{test_campaign.id}/stats",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "total_members" in data
        assert "pending" in data
        assert "sent" in data
        assert "responded" in data
        assert "converted" in data

    @pytest.mark.asyncio
    async def test_get_campaign_stats_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting stats for non-existent campaign."""
        response = await client.get(
            "/api/campaigns/99999/stats",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestCampaignMembers:
    """Tests for campaign member endpoints."""

    @pytest.mark.asyncio
    async def test_list_campaign_members_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
    ):
        """Test listing campaign members when none exist."""
        response = await client.get(
            f"/api/campaigns/{test_campaign.id}/members",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_add_contact_members_to_campaign(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
        test_contact: Contact,
    ):
        """Test adding contacts as campaign members."""
        response = await client.post(
            f"/api/campaigns/{test_campaign.id}/members",
            headers=auth_headers,
            json={
                "member_type": "contact",
                "member_ids": [test_contact.id],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["added"] == 1

    @pytest.mark.asyncio
    async def test_add_lead_members_to_campaign(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
        test_lead: Lead,
    ):
        """Test adding leads as campaign members."""
        response = await client.post(
            f"/api/campaigns/{test_campaign.id}/members",
            headers=auth_headers,
            json={
                "member_type": "lead",
                "member_ids": [test_lead.id],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["added"] == 1

    @pytest.mark.asyncio
    async def test_add_members_campaign_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test adding members to non-existent campaign."""
        response = await client.post(
            "/api/campaigns/99999/members",
            headers=auth_headers,
            json={
                "member_type": "contact",
                "member_ids": [1],
            },
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_campaign_member(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
        test_contact: Contact,
    ):
        """Test updating campaign member status."""
        # First add a member
        member = CampaignMember(
            campaign_id=test_campaign.id,
            member_type="contact",
            member_id=test_contact.id,
            status="pending",
        )
        db_session.add(member)
        await db_session.commit()
        await db_session.refresh(member)

        response = await client.patch(
            f"/api/campaigns/{test_campaign.id}/members/{member.id}",
            headers=auth_headers,
            json={
                "status": "sent",
                "sent_at": date.today().isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"

    @pytest.mark.asyncio
    async def test_remove_campaign_member(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
        test_contact: Contact,
    ):
        """Test removing a campaign member."""
        # First add a member
        member = CampaignMember(
            campaign_id=test_campaign.id,
            member_type="contact",
            member_id=test_contact.id,
            status="pending",
        )
        db_session.add(member)
        await db_session.commit()
        await db_session.refresh(member)
        member_id = member.id

        response = await client.delete(
            f"/api/campaigns/{test_campaign.id}/members/{member_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify deletion
        result = await db_session.execute(
            select(CampaignMember).where(CampaignMember.id == member_id)
        )
        deleted_member = result.scalar_one_or_none()
        assert deleted_member is None


class TestCampaignsUnauthorized:
    """Tests for unauthorized access to campaigns endpoints."""

    @pytest.mark.asyncio
    async def test_list_campaigns_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test listing campaigns without auth fails."""
        response = await client.get("/api/campaigns")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_campaign_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test creating campaign without auth fails."""
        response = await client.post(
            "/api/campaigns",
            json={"name": "Test", "campaign_type": "email"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_campaign_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_campaign: Campaign
    ):
        """Test getting campaign without auth fails."""
        response = await client.get(f"/api/campaigns/{test_campaign.id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_campaign_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_campaign: Campaign
    ):
        """Test updating campaign without auth fails."""
        response = await client.patch(
            f"/api/campaigns/{test_campaign.id}",
            json={"name": "Hacked"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_campaign_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_campaign: Campaign
    ):
        """Test deleting campaign without auth fails."""
        response = await client.delete(f"/api/campaigns/{test_campaign.id}")
        assert response.status_code == 401


class TestEmailTemplates:
    """Tests for email template CRUD lifecycle."""

    @pytest.mark.asyncio
    async def test_email_template_full_lifecycle(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test email template create -> list -> get -> update -> delete lifecycle."""
        # CREATE
        create_response = await client.post(
            "/api/campaigns/templates",
            headers=auth_headers,
            json={
                "name": "Welcome Email",
                "subject_template": "Welcome to {{company}}",
                "body_template": "<h1>Hello {{name}}</h1><p>Welcome aboard!</p>",
                "category": "onboarding",
            },
        )

        assert create_response.status_code == 201
        template = create_response.json()
        assert template["name"] == "Welcome Email"
        assert template["subject_template"] == "Welcome to {{company}}"
        assert template["body_template"] == "<h1>Hello {{name}}</h1><p>Welcome aboard!</p>"
        assert template["category"] == "onboarding"
        assert "id" in template
        template_id = template["id"]

        # LIST
        list_response = await client.get(
            "/api/campaigns/templates",
            headers=auth_headers,
        )

        assert list_response.status_code == 200
        templates = list_response.json()
        assert any(t["id"] == template_id for t in templates)

        # GET
        get_response = await client.get(
            f"/api/campaigns/templates/{template_id}",
            headers=auth_headers,
        )

        assert get_response.status_code == 200
        data = get_response.json()
        assert data["id"] == template_id
        assert data["name"] == "Welcome Email"

        # UPDATE
        update_response = await client.put(
            f"/api/campaigns/templates/{template_id}",
            headers=auth_headers,
            json={
                "name": "Updated Welcome Email",
                "subject_template": "Welcome to {{company}} - Updated",
            },
        )

        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["name"] == "Updated Welcome Email"
        assert updated["subject_template"] == "Welcome to {{company}} - Updated"

        # DELETE
        delete_response = await client.delete(
            f"/api/campaigns/templates/{template_id}",
            headers=auth_headers,
        )

        assert delete_response.status_code == 204

        # Verify deletion
        get_deleted = await client.get(
            f"/api/campaigns/templates/{template_id}",
            headers=auth_headers,
        )
        assert get_deleted.status_code == 404

    @pytest.mark.asyncio
    async def test_create_template_minimal(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating email template with minimal required fields."""
        response = await client.post(
            "/api/campaigns/templates",
            headers=auth_headers,
            json={
                "name": "Simple Template",
                "subject_template": "Hello",
                "body_template": "Body content",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Simple Template"
        assert data["category"] is None

    @pytest.mark.asyncio
    async def test_create_template_missing_name(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating email template without name fails."""
        response = await client.post(
            "/api/campaigns/templates",
            headers=auth_headers,
            json={
                "subject_template": "Hello",
                "body_template": "Body content",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_template_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting non-existent email template."""
        response = await client.get(
            "/api/campaigns/templates/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_template_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test updating non-existent email template."""
        response = await client.put(
            "/api/campaigns/templates/99999",
            headers=auth_headers,
            json={"name": "Updated"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_template_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test deleting non-existent email template."""
        response = await client.delete(
            "/api/campaigns/templates/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_templates_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test accessing templates without auth fails."""
        response = await client.get("/api/campaigns/templates")
        assert response.status_code == 401

        response = await client.post(
            "/api/campaigns/templates",
            json={
                "name": "Test",
                "subject_template": "Test",
                "body_template": "Test",
            },
        )
        assert response.status_code == 401


class TestCampaignSteps:
    """Tests for email campaign steps CRUD lifecycle."""

    @pytest.mark.asyncio
    async def test_campaign_steps_full_lifecycle(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
    ):
        """Test campaign steps create -> list -> update -> delete lifecycle."""
        # First create a template for the step
        template_response = await client.post(
            "/api/campaigns/templates",
            headers=auth_headers,
            json={
                "name": "Step Template",
                "subject_template": "Follow up {{day}}",
                "body_template": "<p>Following up on our conversation.</p>",
            },
        )
        assert template_response.status_code == 201
        template_id = template_response.json()["id"]

        # CREATE step
        create_response = await client.post(
            f"/api/campaigns/{test_campaign.id}/steps",
            headers=auth_headers,
            json={
                "template_id": template_id,
                "delay_days": 0,
                "step_order": 1,
            },
        )

        assert create_response.status_code == 201
        step = create_response.json()
        assert step["campaign_id"] == test_campaign.id
        assert step["template_id"] == template_id
        assert step["delay_days"] == 0
        assert step["step_order"] == 1
        step_id = step["id"]

        # LIST steps
        list_response = await client.get(
            f"/api/campaigns/{test_campaign.id}/steps",
            headers=auth_headers,
        )

        assert list_response.status_code == 200
        steps = list_response.json()
        assert len(steps) >= 1
        assert any(s["id"] == step_id for s in steps)

        # UPDATE step
        update_response = await client.put(
            f"/api/campaigns/{test_campaign.id}/steps/{step_id}",
            headers=auth_headers,
            json={
                "delay_days": 3,
                "step_order": 2,
            },
        )

        assert update_response.status_code == 200
        updated = update_response.json()
        assert updated["delay_days"] == 3
        assert updated["step_order"] == 2

        # DELETE step
        delete_response = await client.delete(
            f"/api/campaigns/{test_campaign.id}/steps/{step_id}",
            headers=auth_headers,
        )

        assert delete_response.status_code == 204

        # Verify deletion - list should be empty
        list_after = await client.get(
            f"/api/campaigns/{test_campaign.id}/steps",
            headers=auth_headers,
        )
        assert list_after.status_code == 200
        assert not any(s["id"] == step_id for s in list_after.json())

    @pytest.mark.asyncio
    async def test_create_step_campaign_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating step for non-existent campaign."""
        response = await client.post(
            "/api/campaigns/99999/steps",
            headers=auth_headers,
            json={
                "template_id": 1,
                "delay_days": 0,
                "step_order": 1,
            },
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_steps_campaign_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test listing steps for non-existent campaign."""
        response = await client.get(
            "/api/campaigns/99999/steps",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_step_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
    ):
        """Test updating non-existent campaign step."""
        response = await client.put(
            f"/api/campaigns/{test_campaign.id}/steps/99999",
            headers=auth_headers,
            json={"delay_days": 5},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_step_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
    ):
        """Test deleting non-existent campaign step."""
        response = await client.delete(
            f"/api/campaigns/{test_campaign.id}/steps/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_multiple_steps_ordering(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
    ):
        """Test creating multiple steps with different orders."""
        # Create template
        template_response = await client.post(
            "/api/campaigns/templates",
            headers=auth_headers,
            json={
                "name": "Multi Step Template",
                "subject_template": "Step {{n}}",
                "body_template": "Step body",
            },
        )
        template_id = template_response.json()["id"]

        # Create 3 steps with different orders and delays
        for order, delay in [(1, 0), (2, 3), (3, 7)]:
            response = await client.post(
                f"/api/campaigns/{test_campaign.id}/steps",
                headers=auth_headers,
                json={
                    "template_id": template_id,
                    "delay_days": delay,
                    "step_order": order,
                },
            )
            assert response.status_code == 201

        # List and verify all steps are present
        list_response = await client.get(
            f"/api/campaigns/{test_campaign.id}/steps",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        steps = list_response.json()
        assert len(steps) == 3


class TestCampaignStatsWithMembers:
    """Tests for campaign stats with actual member data."""

    @pytest.mark.asyncio
    async def test_campaign_stats_with_members(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
        test_contact: Contact,
        test_lead: Lead,
    ):
        """Test campaign stats reflect actual member statuses."""
        # Add members with different statuses
        member1 = CampaignMember(
            campaign_id=test_campaign.id,
            member_type="contact",
            member_id=test_contact.id,
            status="sent",
        )
        member2 = CampaignMember(
            campaign_id=test_campaign.id,
            member_type="lead",
            member_id=test_lead.id,
            status="pending",
        )
        db_session.add_all([member1, member2])
        await db_session.commit()

        response = await client.get(
            f"/api/campaigns/{test_campaign.id}/stats",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_members"] == 2
        assert data["pending"] == 1
        assert data["sent"] == 1


class TestCampaignExecute:
    """Tests for campaign execute endpoint."""

    @pytest.mark.asyncio
    async def test_execute_campaign_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_campaign: Campaign,
    ):
        """Test executing a campaign sets status to in_progress."""
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

    @pytest.mark.asyncio
    async def test_execute_campaign_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_campaign: Campaign,
    ):
        """Test executing campaign without auth fails."""
        response = await client.post(
            f"/api/campaigns/{test_campaign.id}/execute",
        )

        assert response.status_code == 401
