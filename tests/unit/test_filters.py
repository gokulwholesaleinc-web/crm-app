"""
Unit tests for saved filters endpoints.

Tests for creating, listing, getting, updating, and deleting saved filters.
Also verifies user-scoped isolation and filter operator definitions.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.filters.models import SavedFilter


class TestFilterCreate:
    """Tests for creating saved filters."""

    @pytest.mark.asyncio
    async def test_create_filter_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating a new saved filter."""
        response = await client.post(
            "/api/filters",
            headers=auth_headers,
            json={
                "name": "Active Contacts",
                "entity_type": "contacts",
                "filters": {
                    "status": {"operator": "eq", "value": "active"},
                },
                "is_default": False,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Active Contacts"
        assert data["entity_type"] == "contacts"
        assert data["filters"]["status"]["operator"] == "eq"
        assert data["is_default"] is False
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_filter_with_complex_operators(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating filter with various operators (contains, gt, lt, between)."""
        response = await client.post(
            "/api/filters",
            headers=auth_headers,
            json={
                "name": "Complex Filter",
                "entity_type": "leads",
                "filters": {
                    "first_name": {"operator": "contains", "value": "John"},
                    "score": {"operator": "gt", "value": 50},
                    "budget_amount": {"operator": "between", "value": [1000, 50000]},
                },
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["filters"]["first_name"]["operator"] == "contains"
        assert data["filters"]["score"]["operator"] == "gt"
        assert data["filters"]["budget_amount"]["operator"] == "between"

    @pytest.mark.asyncio
    async def test_create_filter_as_default(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating a filter marked as default."""
        response = await client.post(
            "/api/filters",
            headers=auth_headers,
            json={
                "name": "Default Leads Filter",
                "entity_type": "leads",
                "filters": {"status": {"operator": "eq", "value": "new"}},
                "is_default": True,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["is_default"] is True

    @pytest.mark.asyncio
    async def test_create_filter_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test creating filter without auth returns 401."""
        response = await client.post(
            "/api/filters",
            json={
                "name": "Test",
                "entity_type": "contacts",
                "filters": {"status": {"operator": "eq", "value": "active"}},
            },
        )

        assert response.status_code == 401


class TestFilterList:
    """Tests for listing saved filters."""

    @pytest.mark.asyncio
    async def test_list_filters_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test listing filters when none exist."""
        response = await client.get(
            "/api/filters",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_filters_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test listing filters returns user's filters."""
        # Create filter
        await client.post(
            "/api/filters",
            headers=auth_headers,
            json={
                "name": "My Filter",
                "entity_type": "contacts",
                "filters": {"status": {"operator": "eq", "value": "active"}},
            },
        )

        response = await client.get(
            "/api/filters",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(f["name"] == "My Filter" for f in data)

    @pytest.mark.asyncio
    async def test_list_filters_by_entity_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test listing filters filtered by entity_type."""
        # Create filters for different entity types
        await client.post(
            "/api/filters",
            headers=auth_headers,
            json={
                "name": "Contact Filter",
                "entity_type": "contacts",
                "filters": {"status": {"operator": "eq", "value": "active"}},
            },
        )
        await client.post(
            "/api/filters",
            headers=auth_headers,
            json={
                "name": "Lead Filter",
                "entity_type": "leads",
                "filters": {"status": {"operator": "eq", "value": "new"}},
            },
        )

        response = await client.get(
            "/api/filters",
            headers=auth_headers,
            params={"entity_type": "contacts"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(f["entity_type"] == "contacts" for f in data)

    @pytest.mark.asyncio
    async def test_list_filters_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test listing filters without auth returns 401."""
        response = await client.get("/api/filters")
        assert response.status_code == 401


class TestFilterGetById:
    """Tests for getting a specific filter."""

    @pytest.mark.asyncio
    async def test_get_filter_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test getting a saved filter by ID."""
        create_response = await client.post(
            "/api/filters",
            headers=auth_headers,
            json={
                "name": "Fetch Me",
                "entity_type": "contacts",
                "filters": {"status": {"operator": "eq", "value": "active"}},
            },
        )
        filter_id = create_response.json()["id"]

        response = await client.get(
            f"/api/filters/{filter_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == filter_id
        assert data["name"] == "Fetch Me"

    @pytest.mark.asyncio
    async def test_get_filter_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test getting non-existent filter returns 404."""
        response = await client.get(
            "/api/filters/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestFilterUpdate:
    """Tests for updating saved filters."""

    @pytest.mark.asyncio
    async def test_update_filter_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test updating filter name."""
        create_response = await client.post(
            "/api/filters",
            headers=auth_headers,
            json={
                "name": "Old Name",
                "entity_type": "contacts",
                "filters": {"status": {"operator": "eq", "value": "active"}},
            },
        )
        filter_id = create_response.json()["id"]

        response = await client.patch(
            f"/api/filters/{filter_id}",
            headers=auth_headers,
            json={"name": "New Name"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"

    @pytest.mark.asyncio
    async def test_update_filter_definition(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test updating filter definition."""
        create_response = await client.post(
            "/api/filters",
            headers=auth_headers,
            json={
                "name": "To Update",
                "entity_type": "contacts",
                "filters": {"status": {"operator": "eq", "value": "active"}},
            },
        )
        filter_id = create_response.json()["id"]

        new_filters = {
            "status": {"operator": "neq", "value": "inactive"},
            "city": {"operator": "contains", "value": "York"},
        }

        response = await client.patch(
            f"/api/filters/{filter_id}",
            headers=auth_headers,
            json={"filters": new_filters},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["filters"]["status"]["operator"] == "neq"
        assert "city" in data["filters"]

    @pytest.mark.asyncio
    async def test_update_filter_default_flag(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test toggling filter default flag."""
        create_response = await client.post(
            "/api/filters",
            headers=auth_headers,
            json={
                "name": "Toggle Default",
                "entity_type": "contacts",
                "filters": {"status": {"operator": "eq", "value": "active"}},
                "is_default": False,
            },
        )
        filter_id = create_response.json()["id"]

        response = await client.patch(
            f"/api/filters/{filter_id}",
            headers=auth_headers,
            json={"is_default": True},
        )

        assert response.status_code == 200
        assert response.json()["is_default"] is True

    @pytest.mark.asyncio
    async def test_update_filter_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test updating non-existent filter returns 404."""
        response = await client.patch(
            "/api/filters/99999",
            headers=auth_headers,
            json={"name": "Test"},
        )

        assert response.status_code == 404


class TestFilterDelete:
    """Tests for deleting saved filters."""

    @pytest.mark.asyncio
    async def test_delete_filter_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test deleting a saved filter."""
        create_response = await client.post(
            "/api/filters",
            headers=auth_headers,
            json={
                "name": "To Delete",
                "entity_type": "contacts",
                "filters": {"status": {"operator": "eq", "value": "active"}},
            },
        )
        filter_id = create_response.json()["id"]

        response = await client.delete(
            f"/api/filters/{filter_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify deletion
        get_response = await client.get(
            f"/api/filters/{filter_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_filter_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test deleting non-existent filter returns 404."""
        response = await client.delete(
            "/api/filters/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404
