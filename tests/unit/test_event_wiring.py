"""
Tests that verify event emissions are wired into entity routers.

Each test creates/updates an entity via the API and verifies the correct
event type was emitted with the expected payload structure. No mocking is used;
a real event handler is registered to capture emitted events.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.leads.models import Lead, LeadSource
from src.contacts.models import Contact
from src.companies.models import Company
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.quotes.models import Quote
from src.proposals.models import Proposal
from src.events.service import on, off, clear_handlers


class _EventCollector:
    """Collects emitted events for test assertions."""

    def __init__(self):
        self.events = []

    async def handler(self, event_type, payload):
        self.events.append({"event_type": event_type, "payload": payload})

    def find(self, event_type):
        return [e for e in self.events if e["event_type"] == event_type]


@pytest.fixture(autouse=True)
def event_collector():
    """Register an event collector for all event types and clean up after each test."""
    from src.events.service import (
        LEAD_CREATED, LEAD_UPDATED,
        CONTACT_CREATED, CONTACT_UPDATED,
        COMPANY_CREATED, COMPANY_UPDATED,
        OPPORTUNITY_CREATED, OPPORTUNITY_UPDATED, OPPORTUNITY_STAGE_CHANGED,
        ACTIVITY_CREATED,
        QUOTE_SENT, QUOTE_ACCEPTED,
        PROPOSAL_SENT, PROPOSAL_ACCEPTED,
        PAYMENT_RECEIVED,
    )

    collector = _EventCollector()
    all_events = [
        LEAD_CREATED, LEAD_UPDATED,
        CONTACT_CREATED, CONTACT_UPDATED,
        COMPANY_CREATED, COMPANY_UPDATED,
        OPPORTUNITY_CREATED, OPPORTUNITY_UPDATED, OPPORTUNITY_STAGE_CHANGED,
        ACTIVITY_CREATED,
        QUOTE_SENT, QUOTE_ACCEPTED,
        PROPOSAL_SENT, PROPOSAL_ACCEPTED,
        PAYMENT_RECEIVED,
    ]
    for evt in all_events:
        on(evt, collector.handler)

    yield collector

    for evt in all_events:
        off(evt, collector.handler)


class TestLeadEventWiring:
    """Verify events are emitted when leads are created/updated."""

    @pytest.mark.asyncio
    async def test_lead_created_event(
        self, client: AsyncClient, auth_headers: dict, test_lead_source: LeadSource, event_collector: _EventCollector
    ):
        response = await client.post(
            "/api/leads",
            headers=auth_headers,
            json={
                "first_name": "Event",
                "last_name": "Test",
                "email": "eventtest@example.com",
                "status": "new",
                "source_id": test_lead_source.id,
            },
        )
        assert response.status_code == 201

        events = event_collector.find("lead.created")
        assert len(events) == 1
        payload = events[0]["payload"]
        assert payload["entity_type"] == "lead"
        assert payload["entity_id"] == response.json()["id"]
        assert "user_id" in payload
        assert payload["data"]["first_name"] == "Event"

    @pytest.mark.asyncio
    async def test_lead_updated_event(
        self, client: AsyncClient, auth_headers: dict, test_lead: Lead, event_collector: _EventCollector
    ):
        response = await client.patch(
            f"/api/leads/{test_lead.id}",
            headers=auth_headers,
            json={"status": "contacted"},
        )
        assert response.status_code == 200

        events = event_collector.find("lead.updated")
        assert len(events) == 1
        payload = events[0]["payload"]
        assert payload["entity_id"] == test_lead.id
        assert payload["entity_type"] == "lead"


class TestContactEventWiring:
    """Verify events are emitted when contacts are created/updated."""

    @pytest.mark.asyncio
    async def test_contact_created_event(
        self, client: AsyncClient, auth_headers: dict, test_company: Company, event_collector: _EventCollector
    ):
        response = await client.post(
            "/api/contacts",
            headers=auth_headers,
            json={
                "first_name": "Contact",
                "last_name": "Event",
                "email": "contactevent@example.com",
                "company_id": test_company.id,
                "status": "active",
            },
        )
        assert response.status_code == 201

        events = event_collector.find("contact.created")
        assert len(events) == 1
        payload = events[0]["payload"]
        assert payload["entity_type"] == "contact"
        assert payload["entity_id"] == response.json()["id"]

    @pytest.mark.asyncio
    async def test_contact_updated_event(
        self, client: AsyncClient, auth_headers: dict, test_contact: Contact, event_collector: _EventCollector
    ):
        response = await client.patch(
            f"/api/contacts/{test_contact.id}",
            headers=auth_headers,
            json={"first_name": "Updated"},
        )
        assert response.status_code == 200

        events = event_collector.find("contact.updated")
        assert len(events) == 1
        assert events[0]["payload"]["entity_id"] == test_contact.id


class TestCompanyEventWiring:
    """Verify events are emitted when companies are created/updated."""

    @pytest.mark.asyncio
    async def test_company_created_event(
        self, client: AsyncClient, auth_headers: dict, event_collector: _EventCollector
    ):
        response = await client.post(
            "/api/companies",
            headers=auth_headers,
            json={
                "name": "Event Corp",
                "industry": "Tech",
                "status": "prospect",
            },
        )
        assert response.status_code == 201

        events = event_collector.find("company.created")
        assert len(events) == 1
        payload = events[0]["payload"]
        assert payload["entity_type"] == "company"
        assert payload["data"]["name"] == "Event Corp"

    @pytest.mark.asyncio
    async def test_company_updated_event(
        self, client: AsyncClient, auth_headers: dict, test_company: Company, event_collector: _EventCollector
    ):
        response = await client.patch(
            f"/api/companies/{test_company.id}",
            headers=auth_headers,
            json={"name": "Updated Corp"},
        )
        assert response.status_code == 200

        events = event_collector.find("company.updated")
        assert len(events) == 1
        assert events[0]["payload"]["entity_id"] == test_company.id


class TestOpportunityEventWiring:
    """Verify events are emitted when opportunities are created/updated, including stage changes."""

    @pytest.mark.asyncio
    async def test_opportunity_created_event(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_pipeline_stage: PipelineStage,
        test_contact: Contact,
        test_company: Company,
        event_collector: _EventCollector,
    ):
        response = await client.post(
            "/api/opportunities",
            headers=auth_headers,
            json={
                "name": "Event Deal",
                "pipeline_stage_id": test_pipeline_stage.id,
                "amount": 10000,
                "contact_id": test_contact.id,
                "company_id": test_company.id,
            },
        )
        assert response.status_code == 201

        events = event_collector.find("opportunity.created")
        assert len(events) == 1
        payload = events[0]["payload"]
        assert payload["entity_type"] == "opportunity"
        assert payload["data"]["name"] == "Event Deal"

    @pytest.mark.asyncio
    async def test_opportunity_updated_event(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_opportunity: Opportunity,
        event_collector: _EventCollector,
    ):
        response = await client.patch(
            f"/api/opportunities/{test_opportunity.id}",
            headers=auth_headers,
            json={"name": "Updated Deal"},
        )
        assert response.status_code == 200

        events = event_collector.find("opportunity.updated")
        assert len(events) == 1
        assert events[0]["payload"]["entity_id"] == test_opportunity.id

    @pytest.mark.asyncio
    async def test_opportunity_stage_changed_event(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_opportunity: Opportunity,
        test_won_stage: PipelineStage,
        event_collector: _EventCollector,
    ):
        response = await client.patch(
            f"/api/opportunities/{test_opportunity.id}",
            headers=auth_headers,
            json={"pipeline_stage_id": test_won_stage.id},
        )
        assert response.status_code == 200

        stage_events = event_collector.find("opportunity.stage_changed")
        assert len(stage_events) == 1
        payload = stage_events[0]["payload"]
        assert payload["data"]["new_stage_id"] == test_won_stage.id

        # Also verify opportunity.updated was emitted alongside stage_changed
        updated_events = event_collector.find("opportunity.updated")
        assert len(updated_events) == 1


class TestActivityEventWiring:
    """Verify events are emitted when activities are created."""

    @pytest.mark.asyncio
    async def test_activity_created_event(
        self, client: AsyncClient, auth_headers: dict, test_contact: Contact, event_collector: _EventCollector
    ):
        response = await client.post(
            "/api/activities",
            headers=auth_headers,
            json={
                "activity_type": "call",
                "subject": "Test Call",
                "entity_type": "contacts",
                "entity_id": test_contact.id,
                "priority": "normal",
            },
        )
        assert response.status_code == 201

        events = event_collector.find("activity.created")
        assert len(events) == 1
        payload = events[0]["payload"]
        assert payload["entity_type"] == "activity"
        assert payload["data"]["subject"] == "Test Call"
        assert payload["data"]["activity_type"] == "call"


class TestQuoteEventWiring:
    """Verify events are emitted when quotes are sent/accepted."""

    @pytest.mark.asyncio
    async def test_quote_accepted_event(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
        test_company: Company,
        event_collector: _EventCollector,
    ):
        # Create a quote
        quote = Quote(
            quote_number="QE-001",
            title="Event Test Quote",
            status="sent",
            contact_id=test_contact.id,
            company_id=test_company.id,
            subtotal=1000.0,
            total=1000.0,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(quote)
        await db_session.commit()
        await db_session.refresh(quote)

        response = await client.post(
            f"/api/quotes/{quote.id}/accept",
            headers=auth_headers,
        )
        assert response.status_code == 200

        events = event_collector.find("quote.accepted")
        assert len(events) == 1
        payload = events[0]["payload"]
        assert payload["entity_type"] == "quote"
        assert payload["entity_id"] == quote.id


class TestProposalEventWiring:
    """Verify events are emitted when proposals are accepted."""

    @pytest.mark.asyncio
    async def test_proposal_accepted_event(
        self,
        client: AsyncClient,
        auth_headers: dict,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
        test_company: Company,
        event_collector: _EventCollector,
    ):
        # Create a proposal in sent status
        proposal = Proposal(
            proposal_number="PE-001",
            title="Event Test Proposal",
            status="sent",
            content="Test content",
            contact_id=test_contact.id,
            company_id=test_company.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(proposal)
        await db_session.commit()
        await db_session.refresh(proposal)

        response = await client.post(
            f"/api/proposals/{proposal.id}/accept",
            headers=auth_headers,
        )
        assert response.status_code == 200

        events = event_collector.find("proposal.accepted")
        assert len(events) == 1
        payload = events[0]["payload"]
        assert payload["entity_type"] == "proposal"
        assert payload["entity_id"] == proposal.id
