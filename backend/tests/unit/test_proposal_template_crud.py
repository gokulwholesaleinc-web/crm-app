"""
Unit tests for proposal template CRUD and create-from-template functionality.

Tests template CRUD operations, merge variable replacement, legal terms preservation,
custom variables, and validation.
"""

import pytest
from datetime import date
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.proposals.models import Proposal, ProposalTemplate
from src.contacts.models import Contact
from src.companies.models import Company


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def sample_template(db_session: AsyncSession, test_user: User) -> ProposalTemplate:
    """Create a sample proposal template with merge variables."""
    template = ProposalTemplate(
        name="Standard Consulting Proposal",
        description="A reusable consulting proposal template",
        body=(
            "Dear {{contact_name}},\n\n"
            "We are pleased to present this proposal to {{company_name}} "
            "on {{date}}.\n\n"
            "Please contact us at {{contact_email}} or {{contact_phone}} "
            "if you have any questions.\n\n"
            "Company address on file: {{company_address}}"
        ),
        legal_terms=(
            "This agreement is between {{company_name}} and the service provider. "
            "Effective date: {{date}}. "
            "Contact: {{contact_name}} ({{contact_email}})."
        ),
        category="consulting",
        is_default=False,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


@pytest.fixture
async def default_template(db_session: AsyncSession, test_user: User) -> ProposalTemplate:
    """Create a default proposal template."""
    template = ProposalTemplate(
        name="Default Template",
        description="The default template",
        body="Hello {{contact_name}}, this is a default template for {{company_name}}.",
        category="service",
        is_default=True,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


# =============================================================================
# Template CRUD Tests
# =============================================================================

class TestTemplateList:
    """Tests for listing proposal templates."""

    @pytest.mark.asyncio
    async def test_list_templates_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test listing templates when none exist."""
        response = await client.get("/api/proposals/templates", headers=auth_headers)
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_templates_returns_all(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sample_template: ProposalTemplate,
        default_template: ProposalTemplate,
    ):
        """Test listing returns all templates."""
        response = await client.get("/api/proposals/templates", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

    @pytest.mark.asyncio
    async def test_list_templates_filter_by_category(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sample_template: ProposalTemplate,
        default_template: ProposalTemplate,
    ):
        """Test filtering templates by category."""
        response = await client.get(
            "/api/proposals/templates",
            params={"category": "consulting"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["category"] == "consulting"

    @pytest.mark.asyncio
    async def test_list_templates_unauthorized(
        self,
        client: AsyncClient,
    ):
        """Test listing templates without auth returns 401."""
        response = await client.get("/api/proposals/templates")
        assert response.status_code == 401


class TestTemplateCreate:
    """Tests for creating proposal templates."""

    @pytest.mark.asyncio
    async def test_create_template(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating a new template."""
        payload = {
            "name": "New Template",
            "body": "Dear {{contact_name}}, this is a new template.",
            "description": "A new test template",
            "category": "product",
            "is_default": False,
        }
        response = await client.post(
            "/api/proposals/templates",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Template"
        assert data["body"] == payload["body"]
        assert data["category"] == "product"
        assert data["is_default"] is False
        assert data["id"] is not None

    @pytest.mark.asyncio
    async def test_create_template_with_legal_terms(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating a template with legal terms."""
        payload = {
            "name": "Legal Template",
            "body": "Proposal body for {{company_name}}.",
            "legal_terms": "LEGAL NOTICE: This is binding. Contact: {{contact_name}}.",
            "category": "consulting",
        }
        response = await client.post(
            "/api/proposals/templates",
            json=payload,
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["legal_terms"] == payload["legal_terms"]

    @pytest.mark.asyncio
    async def test_create_template_requires_name_and_body(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test that name and body are required."""
        response = await client.post(
            "/api/proposals/templates",
            json={"description": "Missing name and body"},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestTemplateGet:
    """Tests for getting a single template."""

    @pytest.mark.asyncio
    async def test_get_template_by_id(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sample_template: ProposalTemplate,
    ):
        """Test getting a template by ID."""
        response = await client.get(
            f"/api/proposals/templates/{sample_template.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_template.id
        assert data["name"] == sample_template.name
        assert data["body"] == sample_template.body
        assert data["legal_terms"] == sample_template.legal_terms

    @pytest.mark.asyncio
    async def test_get_template_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test getting a non-existent template returns 404."""
        response = await client.get(
            "/api/proposals/templates/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestTemplateUpdate:
    """Tests for updating a template."""

    @pytest.mark.asyncio
    async def test_update_template_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sample_template: ProposalTemplate,
    ):
        """Test updating a template's name."""
        response = await client.patch(
            f"/api/proposals/templates/{sample_template.id}",
            json={"name": "Updated Name"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        # Body should remain unchanged
        assert data["body"] == sample_template.body

    @pytest.mark.asyncio
    async def test_update_template_body(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sample_template: ProposalTemplate,
    ):
        """Test updating a template's body."""
        new_body = "Completely new body for {{contact_name}}."
        response = await client.patch(
            f"/api/proposals/templates/{sample_template.id}",
            json={"body": new_body},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["body"] == new_body

    @pytest.mark.asyncio
    async def test_update_template_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test updating a non-existent template returns 404."""
        response = await client.patch(
            "/api/proposals/templates/99999",
            json={"name": "Should Fail"},
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestTemplateDelete:
    """Tests for deleting a template."""

    @pytest.mark.asyncio
    async def test_delete_template(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sample_template: ProposalTemplate,
    ):
        """Test deleting a template."""
        response = await client.delete(
            f"/api/proposals/templates/{sample_template.id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Verify it's gone
        result = await db_session.execute(
            select(ProposalTemplate).where(ProposalTemplate.id == sample_template.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_template_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test deleting a non-existent template returns 404."""
        response = await client.delete(
            "/api/proposals/templates/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404


# =============================================================================
# Create From Template Tests
# =============================================================================

class TestCreateFromTemplate:
    """Tests for creating a proposal from a template with merge variable replacement."""

    @pytest.mark.asyncio
    async def test_create_from_template_replaces_variables(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sample_template: ProposalTemplate,
        test_contact: Contact,
        test_company: Company,
    ):
        """Test that merge variables are replaced correctly."""
        response = await client.post(
            "/api/proposals/from-template",
            json={
                "template_id": sample_template.id,
                "contact_id": test_contact.id,
                "company_id": test_company.id,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()

        # Title should be the template name
        assert data["title"] == sample_template.name

        # Content should have variables replaced
        content = data["content"]
        assert "John Doe" in content  # contact_name
        assert "Test Company Inc" in content  # company_name
        assert "{{contact_name}}" not in content
        assert "{{company_name}}" not in content

    @pytest.mark.asyncio
    async def test_create_from_template_preserves_legal_terms(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sample_template: ProposalTemplate,
        test_contact: Contact,
        test_company: Company,
    ):
        """Test that legal terms are preserved and variables replaced in them."""
        response = await client.post(
            "/api/proposals/from-template",
            json={
                "template_id": sample_template.id,
                "contact_id": test_contact.id,
                "company_id": test_company.id,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()

        # Legal terms should be in the proposal terms field
        terms = data["terms"]
        assert terms is not None
        assert "This agreement is between" in terms
        assert "Test Company Inc" in terms
        assert "John Doe" in terms
        # Variables should be replaced
        assert "{{company_name}}" not in terms
        assert "{{contact_name}}" not in terms

    @pytest.mark.asyncio
    async def test_create_from_template_includes_date(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sample_template: ProposalTemplate,
        test_contact: Contact,
        test_company: Company,
    ):
        """Test that the date variable is replaced with today's date."""
        response = await client.post(
            "/api/proposals/from-template",
            json={
                "template_id": sample_template.id,
                "contact_id": test_contact.id,
                "company_id": test_company.id,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()

        # Date should be today formatted
        today = date.today()
        today_formatted = today.strftime("%B %d, %Y")
        assert today_formatted in data["content"]
        assert "{{date}}" not in data["content"]

    @pytest.mark.asyncio
    async def test_create_from_template_replaces_contact_details(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sample_template: ProposalTemplate,
        test_contact: Contact,
        test_company: Company,
    ):
        """Test that contact email and phone are replaced."""
        response = await client.post(
            "/api/proposals/from-template",
            json={
                "template_id": sample_template.id,
                "contact_id": test_contact.id,
                "company_id": test_company.id,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()

        content = data["content"]
        assert test_contact.email in content
        assert test_contact.phone in content

    @pytest.mark.asyncio
    async def test_create_from_template_with_custom_variables(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test that custom variables are merged and replaced."""
        # Create a template with a custom variable
        template = ProposalTemplate(
            name="Custom Var Template",
            body="Dear {{contact_name}}, your discount is {{discount_rate}}.",
            category="product",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(template)
        await db_session.commit()
        await db_session.refresh(template)

        response = await client.post(
            "/api/proposals/from-template",
            json={
                "template_id": template.id,
                "contact_id": test_contact.id,
                "custom_variables": {"discount_rate": "15%"},
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()

        content = data["content"]
        assert "15%" in content
        assert "{{discount_rate}}" not in content

    @pytest.mark.asyncio
    async def test_create_from_template_without_company(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sample_template: ProposalTemplate,
        test_contact: Contact,
    ):
        """Test creating from template without a company (company fields empty)."""
        response = await client.post(
            "/api/proposals/from-template",
            json={
                "template_id": sample_template.id,
                "contact_id": test_contact.id,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()

        # Contact name should be there, company name should be empty string
        assert "John Doe" in data["content"]
        assert "{{contact_name}}" not in data["content"]

    @pytest.mark.asyncio
    async def test_create_from_template_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test creating from a non-existent template returns 404."""
        response = await client.post(
            "/api/proposals/from-template",
            json={
                "template_id": 99999,
                "contact_id": test_contact.id,
            },
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_from_template_contact_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sample_template: ProposalTemplate,
    ):
        """Test creating from template with non-existent contact returns 404."""
        response = await client.post(
            "/api/proposals/from-template",
            json={
                "template_id": sample_template.id,
                "contact_id": 99999,
            },
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_from_template_creates_draft_proposal(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sample_template: ProposalTemplate,
        test_contact: Contact,
    ):
        """Test that proposals created from templates start as draft."""
        response = await client.post(
            "/api/proposals/from-template",
            json={
                "template_id": sample_template.id,
                "contact_id": test_contact.id,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "draft"
        assert data["proposal_number"] is not None  # auto-generated

    @pytest.mark.asyncio
    async def test_create_from_template_sets_contact_and_company(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        sample_template: ProposalTemplate,
        test_contact: Contact,
        test_company: Company,
    ):
        """Test that the created proposal has correct contact and company IDs."""
        response = await client.post(
            "/api/proposals/from-template",
            json={
                "template_id": sample_template.id,
                "contact_id": test_contact.id,
                "company_id": test_company.id,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["contact_id"] == test_contact.id
        assert data["company_id"] == test_company.id
