"""
Unit tests for public quote view and e-sign functionality.

Tests for:
- Public quote retrieval (no auth required)
- Branding resolution for public quotes
- Auto-transition from sent to viewed on public access
- E-sign acceptance with signer_name, signer_email, signer_ip
- Public rejection with optional reason
- Status guard (only sent/viewed can be accepted/rejected)
- Quote not found handling
- View URL inclusion in branded email
"""

import pytest
from datetime import date, timedelta
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.quotes.models import Quote, QuoteLineItem
from src.contacts.models import Contact
from src.companies.models import Company
from src.email.models import EmailQueue
from src.whitelabel.models import Tenant, TenantSettings, TenantUser


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def branded_tenant(db_session: AsyncSession) -> Tenant:
    """Create a tenant with branding for public view tests."""
    tenant = Tenant(
        name="Public View Co",
        slug="public-view-co",
        domain="public.example.com",
        is_active=True,
        plan="professional",
        max_users=10,
    )
    db_session.add(tenant)
    await db_session.flush()

    settings = TenantSettings(
        tenant_id=tenant.id,
        company_name="Public View Inc",
        logo_url="https://example.com/public-logo.png",
        primary_color="#2563eb",
        secondary_color="#7c3aed",
        accent_color="#059669",
        footer_text="Public View Inc - Premium Services",
    )
    db_session.add(settings)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest.fixture
async def branded_tenant_user(
    db_session: AsyncSession, branded_tenant: Tenant, test_user: User
) -> TenantUser:
    """Link test_user to the branded tenant."""
    tenant_user = TenantUser(
        tenant_id=branded_tenant.id,
        user_id=test_user.id,
        role="admin",
        is_primary=True,
    )
    db_session.add(tenant_user)
    await db_session.commit()
    await db_session.refresh(tenant_user)
    return tenant_user


@pytest.fixture
async def sent_quote_with_items(
    db_session: AsyncSession, test_user: User, test_contact: Contact, test_company: Company
) -> Quote:
    """Create a sent quote with line items for public view testing."""
    quote = Quote(
        quote_number="QT-2026-PUB-001",
        title="Website Redesign Package",
        description="Complete website overhaul",
        status="sent",
        currency="USD",
        subtotal=10000.0,
        tax_rate=8.5,
        tax_amount=850.0,
        total=10850.0,
        discount_type="percent",
        discount_value=0,
        valid_until=date.today() + timedelta(days=30),
        terms_and_conditions="Payment due within 30 days of acceptance.",
        contact_id=test_contact.id,
        company_id=test_company.id,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(quote)
    await db_session.flush()

    item1 = QuoteLineItem(
        quote_id=quote.id,
        description="UI/UX Design",
        quantity=1,
        unit_price=4000.0,
        discount=0,
        total=4000.0,
        sort_order=0,
    )
    item2 = QuoteLineItem(
        quote_id=quote.id,
        description="Frontend Development",
        quantity=80,
        unit_price=75.0,
        discount=0,
        total=6000.0,
        sort_order=1,
    )
    db_session.add_all([item1, item2])
    await db_session.commit()
    await db_session.refresh(quote)
    return quote


@pytest.fixture
async def draft_quote(
    db_session: AsyncSession, test_user: User
) -> Quote:
    """Create a draft quote for testing status guards."""
    quote = Quote(
        quote_number="QT-2026-PUB-DRAFT",
        title="Draft Quote",
        status="draft",
        currency="USD",
        subtotal=500.0,
        total=500.0,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(quote)
    await db_session.commit()
    await db_session.refresh(quote)
    return quote


@pytest.fixture
async def accepted_quote(
    db_session: AsyncSession, test_user: User
) -> Quote:
    """Create an already-accepted quote."""
    quote = Quote(
        quote_number="QT-2026-PUB-ACCEPTED",
        title="Already Accepted Quote",
        status="accepted",
        currency="USD",
        subtotal=1000.0,
        total=1000.0,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(quote)
    await db_session.commit()
    await db_session.refresh(quote)
    return quote


# =============================================================================
# Public Quote Retrieval Tests
# =============================================================================


class TestPublicQuoteRetrieval:
    """Tests for GET /api/quotes/public/{quote_number}."""

    @pytest.mark.asyncio
    async def test_get_public_quote_returns_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_quote_with_items: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test that the public endpoint returns quote data without auth."""
        response = await client.get(
            f"/api/quotes/public/{sent_quote_with_items.quote_number}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["quote_number"] == "QT-2026-PUB-001"
        assert data["title"] == "Website Redesign Package"
        assert data["currency"] == "USD"
        assert data["total"] == 10850.0

    @pytest.mark.asyncio
    async def test_public_quote_includes_line_items(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_quote_with_items: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test that line items are included in public response."""
        response = await client.get(
            f"/api/quotes/public/{sent_quote_with_items.quote_number}"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["line_items"]) == 2
        descriptions = [item["description"] for item in data["line_items"]]
        assert "UI/UX Design" in descriptions
        assert "Frontend Development" in descriptions

    @pytest.mark.asyncio
    async def test_public_quote_includes_branding(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_quote_with_items: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test that branding data is included in the response."""
        response = await client.get(
            f"/api/quotes/public/{sent_quote_with_items.quote_number}"
        )

        assert response.status_code == 200
        data = response.json()
        branding = data["branding"]
        assert branding is not None
        assert branding["company_name"] == "Public View Inc"
        assert branding["primary_color"] == "#2563eb"
        assert branding["accent_color"] == "#059669"
        assert branding["footer_text"] == "Public View Inc - Premium Services"

    @pytest.mark.asyncio
    async def test_public_quote_auto_transitions_to_viewed(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_quote_with_items: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test that accessing a sent quote auto-transitions it to viewed."""
        assert sent_quote_with_items.status == "sent"

        response = await client.get(
            f"/api/quotes/public/{sent_quote_with_items.quote_number}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "viewed"

        # Verify in DB
        await db_session.refresh(sent_quote_with_items)
        assert sent_quote_with_items.status == "viewed"

    @pytest.mark.asyncio
    async def test_public_quote_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test that requesting a non-existent quote returns 404."""
        response = await client.get("/api/quotes/public/QT-NONEXISTENT")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_public_quote_includes_contact_brief(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_quote_with_items: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test that contact info is included in public response."""
        response = await client.get(
            f"/api/quotes/public/{sent_quote_with_items.quote_number}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["contact"] is not None
        assert data["contact"]["full_name"] == "John Doe"

    @pytest.mark.asyncio
    async def test_public_quote_includes_company_brief(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_quote_with_items: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test that company info is included in public response."""
        response = await client.get(
            f"/api/quotes/public/{sent_quote_with_items.quote_number}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["company"] is not None
        assert data["company"]["name"] == "Test Company Inc"


# =============================================================================
# E-Sign Accept Tests
# =============================================================================


class TestPublicQuoteAccept:
    """Tests for POST /api/quotes/public/{quote_number}/accept."""

    @pytest.mark.asyncio
    async def test_accept_quote_with_esign(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_quote_with_items: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test accepting a quote captures e-sign data."""
        response = await client.post(
            f"/api/quotes/public/{sent_quote_with_items.quote_number}/accept",
            json={"signer_name": "John Doe", "signer_email": "john@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"

        # Verify e-sign data in DB
        await db_session.refresh(sent_quote_with_items)
        assert sent_quote_with_items.status == "accepted"
        assert sent_quote_with_items.signer_name == "John Doe"
        assert sent_quote_with_items.signer_email == "john@example.com"
        assert sent_quote_with_items.signer_ip is not None
        assert sent_quote_with_items.signed_at is not None
        assert sent_quote_with_items.accepted_at is not None

    @pytest.mark.asyncio
    async def test_accept_returns_branding(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_quote_with_items: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test that accept response includes branding data."""
        response = await client.post(
            f"/api/quotes/public/{sent_quote_with_items.quote_number}/accept",
            json={"signer_name": "Jane Doe", "signer_email": "jane@example.com"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["branding"] is not None
        assert data["branding"]["company_name"] == "Public View Inc"

    @pytest.mark.asyncio
    async def test_cannot_accept_draft_quote(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        draft_quote: Quote,
    ):
        """Test that accepting a draft quote returns 400."""
        response = await client.post(
            f"/api/quotes/public/{draft_quote.quote_number}/accept",
            json={"signer_name": "Test", "signer_email": "test@example.com"},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_cannot_accept_already_accepted_quote(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        accepted_quote: Quote,
    ):
        """Test that accepting an already-accepted quote returns 400."""
        response = await client.post(
            f"/api/quotes/public/{accepted_quote.quote_number}/accept",
            json={"signer_name": "Test", "signer_email": "test@example.com"},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_accept_nonexistent_quote_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test that accepting a non-existent quote returns 404."""
        response = await client.post(
            "/api/quotes/public/QT-NONEXISTENT/accept",
            json={"signer_name": "Test", "signer_email": "test@example.com"},
        )

        assert response.status_code == 404


# =============================================================================
# Public Reject Tests
# =============================================================================


class TestPublicQuoteReject:
    """Tests for POST /api/quotes/public/{quote_number}/reject."""

    @pytest.mark.asyncio
    async def test_reject_quote_publicly(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_quote_with_items: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test rejecting a quote via public link."""
        response = await client.post(
            f"/api/quotes/public/{sent_quote_with_items.quote_number}/reject",
            json={"reason": "Budget constraints"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"

        # Verify in DB
        await db_session.refresh(sent_quote_with_items)
        assert sent_quote_with_items.status == "rejected"
        assert sent_quote_with_items.rejection_reason == "Budget constraints"
        assert sent_quote_with_items.rejected_at is not None

    @pytest.mark.asyncio
    async def test_reject_without_reason(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_quote_with_items: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test rejecting a quote without providing a reason."""
        response = await client.post(
            f"/api/quotes/public/{sent_quote_with_items.quote_number}/reject",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "rejected"

        await db_session.refresh(sent_quote_with_items)
        assert sent_quote_with_items.rejection_reason is None

    @pytest.mark.asyncio
    async def test_reject_returns_branding(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sent_quote_with_items: Quote,
        branded_tenant_user: TenantUser,
    ):
        """Test that reject response includes branding."""
        response = await client.post(
            f"/api/quotes/public/{sent_quote_with_items.quote_number}/reject",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["branding"] is not None

    @pytest.mark.asyncio
    async def test_cannot_reject_draft_quote(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        draft_quote: Quote,
    ):
        """Test that rejecting a draft quote returns 400."""
        response = await client.post(
            f"/api/quotes/public/{draft_quote.quote_number}/reject",
            json={},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_cannot_reject_already_accepted_quote(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        accepted_quote: Quote,
    ):
        """Test that rejecting an already-accepted quote returns 400."""
        response = await client.post(
            f"/api/quotes/public/{accepted_quote.quote_number}/reject",
            json={},
        )

        assert response.status_code == 400


# =============================================================================
# Email View URL Tests
# =============================================================================


class TestQuoteEmailViewUrl:
    """Tests for view_url inclusion in branded quote emails."""

    @pytest.mark.asyncio
    async def test_sent_email_contains_view_url(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
        branded_tenant_user: TenantUser,
    ):
        """Test that sent quote email includes a public view URL CTA."""
        quote = Quote(
            quote_number="QT-2026-VIEWURL-001",
            title="View URL Test Quote",
            status="draft",
            currency="USD",
            subtotal=1000.0,
            total=1000.0,
            contact_id=test_contact.id,
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

        assert response.status_code == 200

        result = await db_session.execute(
            select(EmailQueue).where(
                EmailQueue.entity_type == "quotes",
                EmailQueue.entity_id == quote.id,
            )
        )
        email = result.scalar_one_or_none()
        assert email is not None
        # Check the email body contains the CTA with the public URL
        assert "Review" in email.body
        assert "Accept Quote" in email.body
        assert f"/quotes/public/{quote.quote_number}" in email.body
