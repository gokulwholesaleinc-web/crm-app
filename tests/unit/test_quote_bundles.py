"""
Unit tests for product bundle CRUD endpoints and add-bundle-to-quote functionality.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import get_password_hash, create_access_token
from src.quotes.models import Quote, QuoteLineItem, ProductBundle, ProductBundleItem


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def test_bundle_user(db_session: AsyncSession) -> User:
    """Create a test user for bundle tests."""
    user = User(
        email="bundle_user@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Bundle User",
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
def bundle_auth_headers(test_bundle_user: User) -> dict:
    """Auth headers for bundle test user."""
    token = create_access_token(data={"sub": str(test_bundle_user.id)})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def test_bundle(db_session: AsyncSession, test_bundle_user: User) -> ProductBundle:
    """Create a test product bundle with items."""
    bundle = ProductBundle(
        name="Starter Pack",
        description="A starter bundle",
        is_active=True,
        created_by_id=test_bundle_user.id,
    )
    db_session.add(bundle)
    await db_session.flush()

    item1 = ProductBundleItem(
        bundle_id=bundle.id,
        description="Widget A",
        quantity=2,
        unit_price=100.00,
        sort_order=0,
    )
    item2 = ProductBundleItem(
        bundle_id=bundle.id,
        description="Widget B",
        quantity=1,
        unit_price=250.00,
        sort_order=1,
    )
    db_session.add_all([item1, item2])
    await db_session.commit()
    await db_session.refresh(bundle)
    return bundle


@pytest.fixture
async def test_inactive_bundle(db_session: AsyncSession, test_bundle_user: User) -> ProductBundle:
    """Create an inactive test bundle."""
    bundle = ProductBundle(
        name="Inactive Pack",
        description="An inactive bundle",
        is_active=False,
        created_by_id=test_bundle_user.id,
    )
    db_session.add(bundle)
    await db_session.commit()
    await db_session.refresh(bundle)
    return bundle


@pytest.fixture
async def test_quote_for_bundle(db_session: AsyncSession, test_bundle_user: User) -> Quote:
    """Create a test quote for bundle tests."""
    quote = Quote(
        quote_number="QT-BDL-0001",
        title="Bundle Test Quote",
        status="draft",
        currency="USD",
        subtotal=0,
        tax_rate=0,
        tax_amount=0,
        total=0,
        owner_id=test_bundle_user.id,
        created_by_id=test_bundle_user.id,
    )
    db_session.add(quote)
    await db_session.commit()
    await db_session.refresh(quote)
    return quote


# =============================================================================
# Bundle List Tests
# =============================================================================

class TestBundlesList:
    """Tests for GET /api/quotes/bundles."""

    @pytest.mark.asyncio
    async def test_list_bundles_empty(self, client: AsyncClient, bundle_auth_headers: dict):
        """List bundles returns empty list when none exist."""
        response = await client.get("/api/quotes/bundles", headers=bundle_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_bundles_with_data(
        self, client: AsyncClient, bundle_auth_headers: dict, test_bundle: ProductBundle
    ):
        """List bundles returns existing bundles."""
        response = await client.get("/api/quotes/bundles", headers=bundle_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Starter Pack"
        assert len(data["items"][0]["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_bundles_filter_active(
        self,
        client: AsyncClient,
        bundle_auth_headers: dict,
        test_bundle: ProductBundle,
        test_inactive_bundle: ProductBundle,
    ):
        """Filter bundles by is_active."""
        response = await client.get(
            "/api/quotes/bundles?is_active=true", headers=bundle_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Starter Pack"

    @pytest.mark.asyncio
    async def test_list_bundles_search_token(
        self, client: AsyncClient, bundle_auth_headers: dict, test_bundle: ProductBundle
    ):
        """Token-based search: 'star pa' matches 'Starter Pack'."""
        response = await client.get(
            "/api/quotes/bundles?search=star+pa", headers=bundle_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "Starter Pack"

    @pytest.mark.asyncio
    async def test_list_bundles_search_token_no_match(
        self, client: AsyncClient, bundle_auth_headers: dict, test_bundle: ProductBundle
    ):
        """Token-based search: 'star xyz' should not match 'Starter Pack'."""
        response = await client.get(
            "/api/quotes/bundles?search=star+xyz", headers=bundle_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_bundles_unauthenticated(self, client: AsyncClient):
        """Unauthenticated request returns 401."""
        response = await client.get("/api/quotes/bundles")
        assert response.status_code == 401


# =============================================================================
# Bundle Create Tests
# =============================================================================

class TestBundleCreate:
    """Tests for POST /api/quotes/bundles."""

    @pytest.mark.asyncio
    async def test_create_bundle(self, client: AsyncClient, bundle_auth_headers: dict):
        """Create a bundle with items."""
        payload = {
            "name": "Premium Pack",
            "description": "Premium bundle",
            "is_active": True,
            "items": [
                {"description": "Premium Widget", "quantity": 1, "unit_price": 500.0, "sort_order": 0},
                {"description": "Support Plan", "quantity": 1, "unit_price": 200.0, "sort_order": 1},
            ],
        }
        response = await client.post("/api/quotes/bundles", json=payload, headers=bundle_auth_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Premium Pack"
        assert data["is_active"] is True
        assert len(data["items"]) == 2
        assert data["items"][0]["description"] == "Premium Widget"

    @pytest.mark.asyncio
    async def test_create_bundle_without_items(self, client: AsyncClient, bundle_auth_headers: dict):
        """Create a bundle without items."""
        payload = {"name": "Empty Bundle"}
        response = await client.post("/api/quotes/bundles", json=payload, headers=bundle_auth_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Empty Bundle"
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_create_bundle_missing_name(self, client: AsyncClient, bundle_auth_headers: dict):
        """Create a bundle without name returns 422."""
        payload = {"description": "No name"}
        response = await client.post("/api/quotes/bundles", json=payload, headers=bundle_auth_headers)
        assert response.status_code == 422


# =============================================================================
# Bundle Get Tests
# =============================================================================

class TestBundleGetById:
    """Tests for GET /api/quotes/bundles/{bundle_id}."""

    @pytest.mark.asyncio
    async def test_get_bundle(
        self, client: AsyncClient, bundle_auth_headers: dict, test_bundle: ProductBundle
    ):
        """Get a bundle by ID."""
        response = await client.get(
            f"/api/quotes/bundles/{test_bundle.id}", headers=bundle_auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Starter Pack"
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_get_bundle_not_found(self, client: AsyncClient, bundle_auth_headers: dict):
        """Get non-existent bundle returns 404."""
        response = await client.get("/api/quotes/bundles/99999", headers=bundle_auth_headers)
        assert response.status_code == 404


# =============================================================================
# Bundle Update Tests
# =============================================================================

class TestBundleUpdate:
    """Tests for PATCH /api/quotes/bundles/{bundle_id}."""

    @pytest.mark.asyncio
    async def test_update_bundle_name(
        self, client: AsyncClient, bundle_auth_headers: dict, test_bundle: ProductBundle
    ):
        """Update bundle name."""
        payload = {"name": "Updated Pack"}
        response = await client.patch(
            f"/api/quotes/bundles/{test_bundle.id}",
            json=payload,
            headers=bundle_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Pack"

    @pytest.mark.asyncio
    async def test_update_bundle_deactivate(
        self, client: AsyncClient, bundle_auth_headers: dict, test_bundle: ProductBundle
    ):
        """Deactivate a bundle."""
        payload = {"is_active": False}
        response = await client.patch(
            f"/api/quotes/bundles/{test_bundle.id}",
            json=payload,
            headers=bundle_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_bundle_replace_items(
        self, client: AsyncClient, bundle_auth_headers: dict, test_bundle: ProductBundle
    ):
        """Update bundle replaces items when items provided."""
        payload = {
            "items": [
                {"description": "New Widget", "quantity": 3, "unit_price": 75.0, "sort_order": 0},
            ],
        }
        response = await client.patch(
            f"/api/quotes/bundles/{test_bundle.id}",
            json=payload,
            headers=bundle_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["description"] == "New Widget"


# =============================================================================
# Bundle Delete Tests
# =============================================================================

class TestBundleDelete:
    """Tests for DELETE /api/quotes/bundles/{bundle_id}."""

    @pytest.mark.asyncio
    async def test_delete_bundle(
        self, client: AsyncClient, bundle_auth_headers: dict, test_bundle: ProductBundle
    ):
        """Delete a bundle."""
        response = await client.delete(
            f"/api/quotes/bundles/{test_bundle.id}", headers=bundle_auth_headers
        )
        assert response.status_code == 204

        # Verify deleted
        response = await client.get(
            f"/api/quotes/bundles/{test_bundle.id}", headers=bundle_auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_bundle_not_found(self, client: AsyncClient, bundle_auth_headers: dict):
        """Delete non-existent bundle returns 404."""
        response = await client.delete("/api/quotes/bundles/99999", headers=bundle_auth_headers)
        assert response.status_code == 404


# =============================================================================
# Add Bundle to Quote Tests
# =============================================================================

class TestAddBundleToQuote:
    """Tests for POST /api/quotes/{quote_id}/add-bundle/{bundle_id}."""

    @pytest.mark.asyncio
    async def test_add_bundle_to_quote(
        self,
        client: AsyncClient,
        bundle_auth_headers: dict,
        test_quote_for_bundle: Quote,
        test_bundle: ProductBundle,
    ):
        """Add bundle items to a quote."""
        response = await client.post(
            f"/api/quotes/{test_quote_for_bundle.id}/add-bundle/{test_bundle.id}",
            headers=bundle_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["line_items"]) == 2
        assert data["line_items"][0]["description"] == "Widget A"
        assert data["line_items"][1]["description"] == "Widget B"
        assert data["total"] > 0

    @pytest.mark.asyncio
    async def test_add_bundle_not_found(
        self,
        client: AsyncClient,
        bundle_auth_headers: dict,
        test_quote_for_bundle: Quote,
    ):
        """Add non-existent bundle returns 400."""
        response = await client.post(
            f"/api/quotes/{test_quote_for_bundle.id}/add-bundle/99999",
            headers=bundle_auth_headers,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_add_inactive_bundle(
        self,
        client: AsyncClient,
        bundle_auth_headers: dict,
        test_quote_for_bundle: Quote,
        test_inactive_bundle: ProductBundle,
    ):
        """Add inactive bundle returns 400."""
        response = await client.post(
            f"/api/quotes/{test_quote_for_bundle.id}/add-bundle/{test_inactive_bundle.id}",
            headers=bundle_auth_headers,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_add_bundle_preserves_existing_items(
        self,
        client: AsyncClient,
        bundle_auth_headers: dict,
        db_session: AsyncSession,
        test_quote_for_bundle: Quote,
        test_bundle: ProductBundle,
    ):
        """Adding bundle preserves existing line items."""
        # Add an existing line item
        item = QuoteLineItem(
            quote_id=test_quote_for_bundle.id,
            description="Existing Item",
            quantity=1,
            unit_price=50.0,
            discount=0,
            total=50.0,
            sort_order=0,
        )
        db_session.add(item)
        await db_session.commit()

        response = await client.post(
            f"/api/quotes/{test_quote_for_bundle.id}/add-bundle/{test_bundle.id}",
            headers=bundle_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # Original item + 2 bundle items = 3 total
        assert len(data["line_items"]) == 3
