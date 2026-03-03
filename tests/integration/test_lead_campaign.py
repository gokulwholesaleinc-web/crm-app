"""Tests for lead email campaign endpoint.

Tests cover:
- Sending campaign to valid leads with emails
- Handling invalid lead IDs (returns errors)
- Template variable replacement in subject and body
- Authentication requirement
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.leads.models import Lead, LeadSource
from src.email.models import EmailQueue


class TestSendCampaign:
    """Tests for the POST /api/leads/send-campaign endpoint."""

    @pytest.mark.asyncio
    async def test_send_campaign_to_valid_leads(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test sending campaign emails to valid leads with email addresses."""
        response = await client.post(
            "/api/leads/send-campaign",
            headers=auth_headers,
            json={
                "lead_ids": [test_lead.id],
                "subject": "Hello there",
                "body_template": "Hi, this is a test campaign.",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sent_count"] == 1
        assert data["errors"] == []
        assert data["total_requested"] == 1

        # Verify email was queued in the database
        result = await db_session.execute(
            select(EmailQueue).where(
                EmailQueue.entity_type == "leads",
                EmailQueue.entity_id == test_lead.id,
            )
        )
        queued_email = result.scalar_one_or_none()
        assert queued_email is not None
        assert queued_email.to_email == test_lead.email
        assert queued_email.subject == "Hello there"
        assert queued_email.body == "Hi, this is a test campaign."
        assert queued_email.sent_by_id == test_user.id

    @pytest.mark.asyncio
    async def test_send_campaign_with_invalid_lead_ids(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test that invalid lead IDs are reported as errors."""
        response = await client.post(
            "/api/leads/send-campaign",
            headers=auth_headers,
            json={
                "lead_ids": [99999],
                "subject": "Test",
                "body_template": "Body text",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sent_count"] == 0
        assert data["total_requested"] == 1
        assert len(data["errors"]) == 1
        assert data["errors"][0]["lead_id"] == 99999
        assert "not found" in data["errors"][0]["error"].lower()

    @pytest.mark.asyncio
    async def test_send_campaign_template_variables_replaced(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test that {{first_name}} and other placeholders are replaced."""
        response = await client.post(
            "/api/leads/send-campaign",
            headers=auth_headers,
            json={
                "lead_ids": [test_lead.id],
                "subject": "Offer for {{first_name}}",
                "body_template": "Hi {{first_name}} {{last_name}} at {{company_name}}, we have an offer for {{full_name}}.",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sent_count"] == 1

        # Verify the personalized content was stored
        result = await db_session.execute(
            select(EmailQueue).where(
                EmailQueue.entity_type == "leads",
                EmailQueue.entity_id == test_lead.id,
            )
        )
        queued_email = result.scalar_one_or_none()
        assert queued_email is not None
        # test_lead: first_name="Jane", last_name="Smith", company_name="Potential Client LLC"
        assert queued_email.subject == f"Offer for {test_lead.first_name}"
        assert test_lead.first_name in queued_email.body
        assert test_lead.last_name in queued_email.body
        assert test_lead.company_name in queued_email.body
        assert test_lead.full_name in queued_email.body
        assert "{{first_name}}" not in queued_email.body
        assert "{{last_name}}" not in queued_email.body

    @pytest.mark.asyncio
    async def test_send_campaign_requires_authentication(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test that the endpoint returns 401 without auth headers."""
        response = await client.post(
            "/api/leads/send-campaign",
            json={
                "lead_ids": [1],
                "subject": "Test",
                "body_template": "Body",
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_send_campaign_lead_without_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test that leads without email addresses are reported as errors."""
        # Create a lead without email
        lead_no_email = Lead(
            first_name="No",
            last_name="Email",
            email=None,
            company_name="Test Corp",
            status="new",
            score=0,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(lead_no_email)
        await db_session.commit()
        await db_session.refresh(lead_no_email)

        response = await client.post(
            "/api/leads/send-campaign",
            headers=auth_headers,
            json={
                "lead_ids": [lead_no_email.id],
                "subject": "Test",
                "body_template": "Body text",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sent_count"] == 0
        assert len(data["errors"]) == 1
        assert data["errors"][0]["lead_id"] == lead_no_email.id

    @pytest.mark.asyncio
    async def test_send_campaign_mixed_valid_and_invalid(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test campaign with mix of valid and invalid lead IDs."""
        response = await client.post(
            "/api/leads/send-campaign",
            headers=auth_headers,
            json={
                "lead_ids": [test_lead.id, 99999],
                "subject": "Test subject",
                "body_template": "Test body",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sent_count"] == 1
        assert data["total_requested"] == 2
        assert len(data["errors"]) == 1
        assert data["errors"][0]["lead_id"] == 99999
