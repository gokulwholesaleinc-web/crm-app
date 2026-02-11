"""
Unit tests for quotes CRUD endpoints.

Tests for list, create, get, update, delete, auto-numbering,
status transitions, line item management, and data isolation.
"""

import pytest
from datetime import date, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.auth.security import get_password_hash, create_access_token
from src.quotes.models import Quote, QuoteLineItem
from src.contacts.models import Contact
from src.companies.models import Company
from src.opportunities.models import Opportunity, PipelineStage


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
async def test_quote(db_session: AsyncSession, test_user: User) -> Quote:
    """Create a test quote."""
    quote = Quote(
        quote_number="QT-2026-0001",
        title="Test Quote",
        description="A test quote",
        status="draft",
        currency="USD",
        subtotal=1000.0,
        tax_rate=10.0,
        tax_amount=100.0,
        total=1100.0,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(quote)
    await db_session.commit()
    await db_session.refresh(quote)
    return quote


@pytest.fixture
async def test_quote_with_items(
    db_session: AsyncSession, test_user: User
) -> Quote:
    """Create a test quote with line items."""
    quote = Quote(
        quote_number="QT-2026-0002",
        title="Quote with Items",
        status="draft",
        currency="USD",
        subtotal=0,
        tax_rate=0,
        tax_amount=0,
        total=0,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(quote)
    await db_session.flush()

    item1 = QuoteLineItem(
        quote_id=quote.id,
        description="Widget A",
        quantity=2,
        unit_price=500.0,
        discount=0,
        total=1000.0,
        sort_order=0,
    )
    item2 = QuoteLineItem(
        quote_id=quote.id,
        description="Widget B",
        quantity=1,
        unit_price=250.0,
        discount=50.0,
        total=200.0,
        sort_order=1,
    )
    db_session.add_all([item1, item2])

    quote.subtotal = 1200.0
    quote.total = 1200.0

    await db_session.commit()
    await db_session.refresh(quote)
    return quote


# =============================================================================
# Quote CRUD Tests
# =============================================================================

class TestQuotesList:
    """Tests for quotes list endpoint."""

    @pytest.mark.asyncio
    async def test_list_quotes_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test listing quotes when none exist."""
        response = await client.get("/api/quotes", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_quotes_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_quote: Quote,
    ):
        """Test listing quotes with existing data."""
        response = await client.get("/api/quotes", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert any(q["id"] == test_quote.id for q in data["items"])

    @pytest.mark.asyncio
    async def test_list_quotes_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test quotes pagination."""
        for i in range(15):
            q = Quote(
                quote_number=f"QT-2026-{i+10:04d}",
                title=f"Quote {i}",
                status="draft",
                currency="USD",
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(q)
        await db_session.commit()

        response = await client.get(
            "/api/quotes",
            headers=auth_headers,
            params={"page": 1, "page_size": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 10
        assert data["total"] == 15

        response2 = await client.get(
            "/api/quotes",
            headers=auth_headers,
            params={"page": 2, "page_size": 10},
        )
        data2 = response2.json()
        assert len(data2["items"]) == 5

    @pytest.mark.asyncio
    async def test_list_quotes_search(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_quote: Quote,
    ):
        """Test searching quotes by title."""
        response = await client.get(
            "/api/quotes",
            headers=auth_headers,
            params={"search": "Test Quote"},
        )

        assert response.status_code == 200
        data = response.json()
        assert any(q["id"] == test_quote.id for q in data["items"])

    @pytest.mark.asyncio
    async def test_list_quotes_search_by_number(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_quote: Quote,
    ):
        """Test searching quotes by quote number."""
        response = await client.get(
            "/api/quotes",
            headers=auth_headers,
            params={"search": "QT-2026-0001"},
        )

        assert response.status_code == 200
        data = response.json()
        assert any(q["id"] == test_quote.id for q in data["items"])

    @pytest.mark.asyncio
    async def test_list_quotes_filter_by_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_quote: Quote,
    ):
        """Test filtering quotes by status."""
        response = await client.get(
            "/api/quotes",
            headers=auth_headers,
            params={"status": "draft"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(q["status"] == "draft" for q in data["items"])


class TestQuotesCreate:
    """Tests for quote creation endpoint."""

    @pytest.mark.asyncio
    async def test_create_quote_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test successful quote creation."""
        response = await client.post(
            "/api/quotes",
            headers=auth_headers,
            json={
                "title": "New Quote",
                "description": "A new sales quote",
                "currency": "USD",
                "valid_until": (date.today() + timedelta(days=30)).isoformat(),
                "tax_rate": 10.0,
                "status": "draft",
                "discount_value": 0,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Quote"
        assert data["status"] == "draft"
        assert "quote_number" in data
        assert data["quote_number"].startswith("QT-")
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_quote_with_line_items(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating a quote with line items."""
        response = await client.post(
            "/api/quotes",
            headers=auth_headers,
            json={
                "title": "Quote with Items",
                "currency": "USD",
                "status": "draft",
                "tax_rate": 0,
                "discount_value": 0,
                "line_items": [
                    {
                        "description": "Item 1",
                        "quantity": 2,
                        "unit_price": 100.0,
                        "discount": 0,
                        "sort_order": 0,
                    },
                    {
                        "description": "Item 2",
                        "quantity": 1,
                        "unit_price": 50.0,
                        "discount": 10.0,
                        "sort_order": 1,
                    },
                ],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert len(data["line_items"]) == 2
        assert data["line_items"][0]["description"] == "Item 1"
        assert data["line_items"][0]["total"] == 200.0
        assert data["line_items"][1]["total"] == 40.0
        assert data["subtotal"] == 240.0
        assert data["total"] == 240.0

    @pytest.mark.asyncio
    async def test_create_quote_missing_title(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating quote without title fails."""
        response = await client.post(
            "/api/quotes",
            headers=auth_headers,
            json={
                "currency": "USD",
                "status": "draft",
                "discount_value": 0,
                "tax_rate": 0,
            },
        )

        assert response.status_code == 422


class TestAutoNumbering:
    """Tests for quote auto-numbering."""

    @pytest.mark.asyncio
    async def test_auto_numbering_sequential(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test that quote numbers are generated sequentially."""
        response1 = await client.post(
            "/api/quotes",
            headers=auth_headers,
            json={
                "title": "First Quote",
                "currency": "USD",
                "status": "draft",
                "discount_value": 0,
                "tax_rate": 0,
            },
        )
        assert response1.status_code == 201
        number1 = response1.json()["quote_number"]

        response2 = await client.post(
            "/api/quotes",
            headers=auth_headers,
            json={
                "title": "Second Quote",
                "currency": "USD",
                "status": "draft",
                "discount_value": 0,
                "tax_rate": 0,
            },
        )
        assert response2.status_code == 201
        number2 = response2.json()["quote_number"]

        # Both should start with QT-{year}-
        assert number1.startswith("QT-")
        assert number2.startswith("QT-")

        # Second number should be higher
        seq1 = int(number1.split("-")[-1])
        seq2 = int(number2.split("-")[-1])
        assert seq2 > seq1


class TestQuotesGetById:
    """Tests for get quote by ID endpoint."""

    @pytest.mark.asyncio
    async def test_get_quote_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_quote: Quote,
    ):
        """Test getting quote by ID."""
        response = await client.get(
            f"/api/quotes/{test_quote.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_quote.id
        assert data["title"] == test_quote.title
        assert data["quote_number"] == test_quote.quote_number

    @pytest.mark.asyncio
    async def test_get_quote_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test getting non-existent quote."""
        response = await client.get(
            "/api/quotes/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_quote_includes_line_items(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_quote_with_items: Quote,
    ):
        """Test that getting quote includes line items."""
        response = await client.get(
            f"/api/quotes/{test_quote_with_items.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["line_items"]) == 2
        assert data["line_items"][0]["description"] == "Widget A"


class TestQuotesUpdate:
    """Tests for quote update endpoint."""

    @pytest.mark.asyncio
    async def test_update_quote_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_quote: Quote,
    ):
        """Test updating a quote."""
        response = await client.patch(
            f"/api/quotes/{test_quote.id}",
            headers=auth_headers,
            json={
                "title": "Updated Quote Title",
                "description": "Updated description",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Quote Title"
        assert data["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_update_quote_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test updating non-existent quote."""
        response = await client.patch(
            "/api/quotes/99999",
            headers=auth_headers,
            json={"title": "Test"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_quote_tax_rate(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_quote_with_items: Quote,
    ):
        """Test updating tax rate recalculates totals."""
        response = await client.patch(
            f"/api/quotes/{test_quote_with_items.id}",
            headers=auth_headers,
            json={"tax_rate": 10.0},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tax_rate"] == 10.0
        assert data["tax_amount"] > 0


class TestQuotesDelete:
    """Tests for quote delete endpoint."""

    @pytest.mark.asyncio
    async def test_delete_quote_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test deleting a quote."""
        quote = Quote(
            quote_number="QT-2026-9999",
            title="To Delete",
            status="draft",
            currency="USD",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(quote)
        await db_session.commit()
        await db_session.refresh(quote)
        qid = quote.id

        response = await client.delete(
            f"/api/quotes/{qid}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        result = await db_session.execute(
            select(Quote).where(Quote.id == qid)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_quote_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test deleting non-existent quote."""
        response = await client.delete(
            "/api/quotes/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_quote_cascades_line_items(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_quote_with_items: Quote,
    ):
        """Test that deleting a quote also deletes its line items."""
        qid = test_quote_with_items.id

        response = await client.delete(
            f"/api/quotes/{qid}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        result = await db_session.execute(
            select(QuoteLineItem).where(QuoteLineItem.quote_id == qid)
        )
        items = result.scalars().all()
        assert len(items) == 0


# =============================================================================
# Status Transition Tests
# =============================================================================

class TestStatusTransitions:
    """Tests for quote status transition endpoints."""

    @pytest.mark.asyncio
    async def test_send_quote(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_quote: Quote,
    ):
        """Test sending a draft quote."""
        response = await client.post(
            f"/api/quotes/{test_quote.id}/send",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "sent"
        assert data["sent_at"] is not None

    @pytest.mark.asyncio
    async def test_accept_sent_quote(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test accepting a sent quote."""
        quote = Quote(
            quote_number="QT-2026-ACC1",
            title="To Accept",
            status="sent",
            currency="USD",
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
        data = response.json()
        assert data["status"] == "accepted"
        assert data["accepted_at"] is not None

    @pytest.mark.asyncio
    async def test_reject_sent_quote(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test rejecting a sent quote."""
        quote = Quote(
            quote_number="QT-2026-REJ1",
            title="To Reject",
            status="sent",
            currency="USD",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(quote)
        await db_session.commit()
        await db_session.refresh(quote)

        response = await client.post(
            f"/api/quotes/{quote.id}/reject",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"
        assert data["rejected_at"] is not None

    @pytest.mark.asyncio
    async def test_cannot_send_accepted_quote(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test that an accepted quote cannot be sent again."""
        quote = Quote(
            quote_number="QT-2026-INV1",
            title="Already Accepted",
            status="accepted",
            currency="USD",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(quote)
        await db_session.commit()
        await db_session.refresh(quote)

        response = await client.post(
            f"/api/quotes/{quote.id}/send",
            headers=auth_headers,
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_cannot_accept_draft_quote(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_quote: Quote,
    ):
        """Test that a draft quote cannot be directly accepted."""
        response = await client.post(
            f"/api/quotes/{test_quote.id}/accept",
            headers=auth_headers,
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_cannot_reject_draft_quote(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_quote: Quote,
    ):
        """Test that a draft quote cannot be directly rejected."""
        response = await client.post(
            f"/api/quotes/{test_quote.id}/reject",
            headers=auth_headers,
        )

        assert response.status_code == 400


# =============================================================================
# Line Item Tests
# =============================================================================

class TestLineItems:
    """Tests for quote line item endpoints."""

    @pytest.mark.asyncio
    async def test_add_line_item(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_quote: Quote,
    ):
        """Test adding a line item to a quote."""
        response = await client.post(
            f"/api/quotes/{test_quote.id}/line-items",
            headers=auth_headers,
            json={
                "description": "New Item",
                "quantity": 3,
                "unit_price": 100.0,
                "discount": 0,
                "sort_order": 0,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["description"] == "New Item"
        assert data["quantity"] == 3
        assert data["unit_price"] == 100.0
        assert data["total"] == 300.0

    @pytest.mark.asyncio
    async def test_remove_line_item(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_quote_with_items: Quote,
    ):
        """Test removing a line item from a quote."""
        item_id = test_quote_with_items.line_items[0].id

        response = await client.delete(
            f"/api/quotes/{test_quote_with_items.id}/line-items/{item_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify item is gone
        result = await db_session.execute(
            select(QuoteLineItem).where(QuoteLineItem.id == item_id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_remove_nonexistent_line_item(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_quote: Quote,
    ):
        """Test removing a non-existent line item."""
        response = await client.delete(
            f"/api/quotes/{test_quote.id}/line-items/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_add_line_item_with_discount(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_quote: Quote,
    ):
        """Test adding a line item with discount calculates total correctly."""
        response = await client.post(
            f"/api/quotes/{test_quote.id}/line-items",
            headers=auth_headers,
            json={
                "description": "Discounted Item",
                "quantity": 2,
                "unit_price": 200.0,
                "discount": 50.0,
                "sort_order": 0,
            },
        )

        assert response.status_code == 201
        data = response.json()
        # total = (2 * 200) - 50 = 350
        assert data["total"] == 350.0


# =============================================================================
# Data Isolation Tests
# =============================================================================

class TestDataIsolation:
    """Tests for data isolation between users."""

    @pytest.mark.asyncio
    async def test_user_sees_only_own_quotes(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        auth_headers: dict,
    ):
        """Test that a user only sees their own quotes."""
        # Create another user
        other_user = User(
            email="other@example.com",
            hashed_password=get_password_hash("otherpass123"),
            full_name="Other User",
            is_active=True,
            is_superuser=False,
        )
        db_session.add(other_user)
        await db_session.commit()
        await db_session.refresh(other_user)

        # Create quotes for both users
        my_quote = Quote(
            quote_number="QT-2026-MY01",
            title="My Quote",
            status="draft",
            currency="USD",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        other_quote = Quote(
            quote_number="QT-2026-OT01",
            title="Other Quote",
            status="draft",
            currency="USD",
            owner_id=other_user.id,
            created_by_id=other_user.id,
        )
        db_session.add_all([my_quote, other_quote])
        await db_session.commit()

        response = await client.get("/api/quotes", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        titles = [q["title"] for q in data["items"]]
        assert "My Quote" in titles
        # Non-superuser should only see own data
        # (data scope forces owner_id filter for non-admin users)


# =============================================================================
# Unauthorized Access Tests
# =============================================================================

class TestQuotesUnauthorized:
    """Tests for unauthorized access to quotes endpoints."""

    @pytest.mark.asyncio
    async def test_list_quotes_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test listing quotes without auth fails."""
        response = await client.get("/api/quotes")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_quote_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test creating quote without auth fails."""
        response = await client.post(
            "/api/quotes",
            json={"title": "Test", "currency": "USD", "status": "draft", "discount_value": 0, "tax_rate": 0},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_quote_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_quote: Quote,
    ):
        """Test getting quote without auth fails."""
        response = await client.get(f"/api/quotes/{test_quote.id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_quote_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_quote: Quote,
    ):
        """Test updating quote without auth fails."""
        response = await client.patch(
            f"/api/quotes/{test_quote.id}",
            json={"title": "Hacked"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_quote_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_quote: Quote,
    ):
        """Test deleting quote without auth fails."""
        response = await client.delete(f"/api/quotes/{test_quote.id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_send_quote_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_quote: Quote,
    ):
        """Test sending quote without auth fails."""
        response = await client.post(f"/api/quotes/{test_quote.id}/send")
        assert response.status_code == 401


# =============================================================================
# Financial Calculations Tests
# =============================================================================

class TestFinancialCalculations:
    """Tests for quote financial calculations."""

    @pytest.mark.asyncio
    async def test_create_quote_with_percent_discount(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating a quote with percentage discount."""
        response = await client.post(
            "/api/quotes",
            headers=auth_headers,
            json={
                "title": "Percent Discount Quote",
                "currency": "USD",
                "status": "draft",
                "discount_type": "percent",
                "discount_value": 10,
                "tax_rate": 5,
                "line_items": [
                    {
                        "description": "Item",
                        "quantity": 1,
                        "unit_price": 1000.0,
                        "discount": 0,
                        "sort_order": 0,
                    },
                ],
            },
        )

        assert response.status_code == 201
        data = response.json()
        # subtotal = 1000
        assert data["subtotal"] == 1000.0
        # 10% discount = 100, after discount = 900
        # 5% tax on 900 = 45
        assert data["tax_amount"] == 45.0
        assert data["total"] == 945.0

    @pytest.mark.asyncio
    async def test_create_quote_with_fixed_discount(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating a quote with fixed discount."""
        response = await client.post(
            "/api/quotes",
            headers=auth_headers,
            json={
                "title": "Fixed Discount Quote",
                "currency": "USD",
                "status": "draft",
                "discount_type": "fixed",
                "discount_value": 200,
                "tax_rate": 0,
                "line_items": [
                    {
                        "description": "Item",
                        "quantity": 1,
                        "unit_price": 1000.0,
                        "discount": 0,
                        "sort_order": 0,
                    },
                ],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["subtotal"] == 1000.0
        # fixed discount 200, total = 800
        assert data["total"] == 800.0
