"""
Unit tests for contracts CRUD endpoints.

Tests for list, create, get, update, delete, and filtering operations.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.contacts.models import Contact
from src.companies.models import Company
from src.contracts.models import Contract


class TestContractsList:
    """Tests for contracts list endpoint with pagination."""

    @pytest.mark.asyncio
    async def test_list_contracts_empty(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test listing contracts when none exist."""
        response = await client.get("/api/contracts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_contracts_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
    ):
        """Test listing contracts with existing data."""
        response = await client.get("/api/contracts", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1
        assert any(c["id"] == test_contract.id for c in data["items"])

    @pytest.mark.asyncio
    async def test_list_contracts_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test contracts pagination."""
        for i in range(15):
            contract = Contract(
                title=f"Contract {i}",
                status="draft",
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(contract)
        await db_session.commit()

        response = await client.get(
            "/api/contracts",
            headers=auth_headers,
            params={"page": 1, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["page"] == 1
        assert data["total"] == 15

        response = await client.get(
            "/api/contracts",
            headers=auth_headers,
            params={"page": 2, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 5

    @pytest.mark.asyncio
    async def test_list_contracts_filter_by_contact(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
        test_contact: Contact,
    ):
        """Test filtering contracts by contact_id."""
        response = await client.get(
            "/api/contracts",
            headers=auth_headers,
            params={"contact_id": test_contact.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert all(c["contact_id"] == test_contact.id for c in data["items"])

    @pytest.mark.asyncio
    async def test_list_contracts_filter_by_company(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
        test_company: Company,
    ):
        """Test filtering contracts by company_id."""
        response = await client.get(
            "/api/contracts",
            headers=auth_headers,
            params={"company_id": test_company.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert all(c["company_id"] == test_company.id for c in data["items"])

    @pytest.mark.asyncio
    async def test_list_contracts_filter_by_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
    ):
        """Test filtering contracts by status."""
        response = await client.get(
            "/api/contracts",
            headers=auth_headers,
            params={"status": "draft"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(c["status"] == "draft" for c in data["items"])


class TestContractsCreate:
    """Tests for contract creation."""

    @pytest.mark.asyncio
    async def test_create_contract_minimal(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating a contract with minimal data."""
        response = await client.post(
            "/api/contracts",
            headers=auth_headers,
            json={"title": "Minimal Contract"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Minimal Contract"
        assert data["status"] == "draft"
        assert data["currency"] == "USD"
        assert data["id"] is not None

    @pytest.mark.asyncio
    async def test_create_contract_full(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
        test_company: Company,
    ):
        """Test creating a contract with all fields."""
        response = await client.post(
            "/api/contracts",
            headers=auth_headers,
            json={
                "title": "Full Contract",
                "contact_id": test_contact.id,
                "company_id": test_company.id,
                "start_date": "2026-01-01",
                "end_date": "2026-12-31",
                "scope": "Full service agreement",
                "value": 100000.0,
                "currency": "EUR",
                "status": "active",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Full Contract"
        assert data["contact_id"] == test_contact.id
        assert data["company_id"] == test_company.id
        assert data["start_date"] == "2026-01-01"
        assert data["end_date"] == "2026-12-31"
        assert data["scope"] == "Full service agreement"
        assert data["value"] == 100000.0
        assert data["currency"] == "EUR"
        assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_create_contract_missing_title(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating a contract without a title fails validation."""
        response = await client.post(
            "/api/contracts",
            headers=auth_headers,
            json={"value": 5000},
        )

        assert response.status_code == 422


class TestContractsGet:
    """Tests for get contract by ID."""

    @pytest.mark.asyncio
    async def test_get_contract(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
    ):
        """Test getting a contract by ID."""
        response = await client.get(
            f"/api/contracts/{test_contract.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_contract.id
        assert data["title"] == test_contract.title

    @pytest.mark.asyncio
    async def test_get_contract_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test getting a non-existent contract returns 404."""
        response = await client.get(
            "/api/contracts/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestContractsUpdate:
    """Tests for contract update."""

    @pytest.mark.asyncio
    async def test_update_contract_title(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
    ):
        """Test updating a contract title."""
        response = await client.patch(
            f"/api/contracts/{test_contract.id}",
            headers=auth_headers,
            json={"title": "Updated Contract Title"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Contract Title"

    @pytest.mark.asyncio
    async def test_update_contract_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
    ):
        """Test updating contract status."""
        response = await client.patch(
            f"/api/contracts/{test_contract.id}",
            headers=auth_headers,
            json={"status": "active"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_update_contract_value_and_dates(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
    ):
        """Test updating contract value and dates."""
        response = await client.patch(
            f"/api/contracts/{test_contract.id}",
            headers=auth_headers,
            json={
                "value": 50000.0,
                "start_date": "2026-06-01",
                "end_date": "2027-05-31",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["value"] == 50000.0
        assert data["start_date"] == "2026-06-01"
        assert data["end_date"] == "2027-05-31"

    @pytest.mark.asyncio
    async def test_update_contract_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test updating a non-existent contract returns 404."""
        response = await client.patch(
            "/api/contracts/99999",
            headers=auth_headers,
            json={"title": "Updated"},
        )

        assert response.status_code == 404


class TestContractsDelete:
    """Tests for contract deletion."""

    @pytest.mark.asyncio
    async def test_delete_contract(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
    ):
        """Test deleting a contract."""
        response = await client.delete(
            f"/api/contracts/{test_contract.id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify contract is deleted
        response = await client.get(
            f"/api/contracts/{test_contract.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_contract_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test deleting a non-existent contract returns 404."""
        response = await client.delete(
            "/api/contracts/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestContractsStatusTransitions:
    """Tests for contract status transitions."""

    @pytest.mark.asyncio
    async def test_status_draft_to_active(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
    ):
        """Test transitioning contract from draft to active."""
        assert test_contract.status == "draft"

        response = await client.patch(
            f"/api/contracts/{test_contract.id}",
            headers=auth_headers,
            json={"status": "active"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "active"

    @pytest.mark.asyncio
    async def test_status_active_to_expired(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
    ):
        """Test transitioning contract from active to expired."""
        # First set to active
        await client.patch(
            f"/api/contracts/{test_contract.id}",
            headers=auth_headers,
            json={"status": "active"},
        )

        # Then set to expired
        response = await client.patch(
            f"/api/contracts/{test_contract.id}",
            headers=auth_headers,
            json={"status": "expired"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "expired"

    @pytest.mark.asyncio
    async def test_status_active_to_terminated(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
    ):
        """Test transitioning contract from active to terminated."""
        # First set to active
        await client.patch(
            f"/api/contracts/{test_contract.id}",
            headers=auth_headers,
            json={"status": "active"},
        )

        # Then set to terminated
        response = await client.patch(
            f"/api/contracts/{test_contract.id}",
            headers=auth_headers,
            json={"status": "terminated"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "terminated"
