"""
Unit tests for white-label/tenant endpoints.

Tests for tenant CRUD, public config, settings, and tenant user management.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.auth.security import create_access_token
from src.whitelabel.models import Tenant, TenantSettings, TenantUser


# --- Fixtures ---


@pytest.fixture
async def superuser_token(test_superuser: User) -> str:
    """Create authentication token for superuser."""
    return create_access_token(data={"sub": str(test_superuser.id)})


@pytest.fixture
async def superuser_headers(superuser_token: str) -> dict:
    """Create authorization headers for superuser API requests."""
    return {"Authorization": f"Bearer {superuser_token}"}


@pytest.fixture
async def test_tenant(db_session: AsyncSession) -> Tenant:
    """Create a test tenant with settings."""
    tenant = Tenant(
        name="Test Tenant",
        slug="test-tenant",
        domain="test.example.com",
        is_active=True,
        plan="professional",
        max_users=10,
        max_contacts=1000,
    )
    db_session.add(tenant)
    await db_session.flush()

    settings = TenantSettings(
        tenant_id=tenant.id,
        company_name="Test Tenant Inc",
        logo_url="https://example.com/logo.png",
        favicon_url="https://example.com/favicon.ico",
        primary_color="#6366f1",
        secondary_color="#8b5cf6",
        accent_color="#22c55e",
        footer_text="Test Tenant Footer",
        privacy_policy_url="https://example.com/privacy",
        terms_of_service_url="https://example.com/terms",
        default_language="en",
        default_timezone="UTC",
        default_currency="USD",
        date_format="MM/DD/YYYY",
    )
    db_session.add(settings)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest.fixture
async def inactive_tenant(db_session: AsyncSession) -> Tenant:
    """Create an inactive test tenant."""
    tenant = Tenant(
        name="Inactive Tenant",
        slug="inactive-tenant",
        domain="inactive.example.com",
        is_active=False,
        plan="starter",
        max_users=5,
    )
    db_session.add(tenant)
    await db_session.flush()

    settings = TenantSettings(
        tenant_id=tenant.id,
        company_name="Inactive Tenant Inc",
    )
    db_session.add(settings)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


@pytest.fixture
async def test_tenant_user(
    db_session: AsyncSession, test_tenant: Tenant, test_user: User
) -> TenantUser:
    """Create a test tenant user."""
    tenant_user = TenantUser(
        tenant_id=test_tenant.id,
        user_id=test_user.id,
        role="admin",
        is_primary=True,
    )
    db_session.add(tenant_user)
    await db_session.commit()
    await db_session.refresh(tenant_user)
    return tenant_user


# --- Public Config Tests ---


class TestPublicTenantConfig:
    """Tests for public tenant configuration endpoints (no auth required)."""

    @pytest.mark.asyncio
    async def test_get_public_config_by_slug(
        self, client: AsyncClient, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test getting public tenant config by slug."""
        response = await client.get(f"/api/tenants/config/{test_tenant.slug}")

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_slug"] == test_tenant.slug
        assert data["company_name"] == "Test Tenant Inc"
        assert data["primary_color"] == "#6366f1"
        assert data["secondary_color"] == "#8b5cf6"
        assert data["accent_color"] == "#22c55e"
        assert data["logo_url"] == "https://example.com/logo.png"
        assert data["favicon_url"] == "https://example.com/favicon.ico"
        assert data["footer_text"] == "Test Tenant Footer"
        assert data["privacy_policy_url"] == "https://example.com/privacy"
        assert data["terms_of_service_url"] == "https://example.com/terms"
        assert data["default_language"] == "en"
        assert data["date_format"] == "MM/DD/YYYY"

    @pytest.mark.asyncio
    async def test_get_public_config_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test getting config for non-existent tenant returns 404."""
        response = await client.get("/api/tenants/config/non-existent-slug")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_public_config_inactive_tenant(
        self, client: AsyncClient, db_session: AsyncSession, inactive_tenant: Tenant
    ):
        """Test getting config for inactive tenant returns 404."""
        response = await client.get(f"/api/tenants/config/{inactive_tenant.slug}")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_config_by_domain(
        self, client: AsyncClient, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test getting tenant config by custom domain."""
        response = await client.get(f"/api/tenants/config/domain/{test_tenant.domain}")

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_slug"] == test_tenant.slug
        assert data["company_name"] == "Test Tenant Inc"

    @pytest.mark.asyncio
    async def test_get_config_by_domain_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test getting config for non-existent domain returns 404."""
        response = await client.get("/api/tenants/config/domain/nonexistent.example.com")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_config_by_domain_inactive_tenant(
        self, client: AsyncClient, db_session: AsyncSession, inactive_tenant: Tenant
    ):
        """Test getting config by domain for inactive tenant returns 404."""
        response = await client.get(
            f"/api/tenants/config/domain/{inactive_tenant.domain}"
        )

        assert response.status_code == 404


# --- Tenant List Tests ---


class TestTenantsList:
    """Tests for tenant list endpoint (superuser only)."""

    @pytest.mark.asyncio
    async def test_list_tenants_empty(
        self, client: AsyncClient, db_session: AsyncSession, superuser_headers: dict
    ):
        """Test listing tenants when none exist."""
        response = await client.get("/api/tenants", headers=superuser_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_list_tenants_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        superuser_headers: dict,
        test_tenant: Tenant,
    ):
        """Test listing tenants with existing data."""
        response = await client.get("/api/tenants", headers=superuser_headers)

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(t["id"] == test_tenant.id for t in data)

    @pytest.mark.asyncio
    async def test_list_tenants_active_only_by_default(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        superuser_headers: dict,
        test_tenant: Tenant,
        inactive_tenant: Tenant,
    ):
        """Test that only active tenants are listed by default."""
        response = await client.get("/api/tenants", headers=superuser_headers)

        assert response.status_code == 200
        data = response.json()
        # Active tenant should be present
        assert any(t["id"] == test_tenant.id for t in data)
        # Inactive tenant should not be present
        assert not any(t["id"] == inactive_tenant.id for t in data)

    @pytest.mark.asyncio
    async def test_list_tenants_include_inactive(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        superuser_headers: dict,
        test_tenant: Tenant,
        inactive_tenant: Tenant,
    ):
        """Test listing all tenants including inactive ones."""
        response = await client.get(
            "/api/tenants",
            headers=superuser_headers,
            params={"active_only": False},
        )

        assert response.status_code == 200
        data = response.json()
        # Both active and inactive tenants should be present
        assert any(t["id"] == test_tenant.id for t in data)
        assert any(t["id"] == inactive_tenant.id for t in data)

    @pytest.mark.asyncio
    async def test_list_tenants_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test listing tenants without auth fails."""
        response = await client.get("/api/tenants")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_tenants_non_superuser(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test listing tenants with non-superuser fails."""
        response = await client.get("/api/tenants", headers=auth_headers)

        assert response.status_code == 403


# --- Tenant Create Tests ---


class TestTenantsCreate:
    """Tests for tenant creation endpoint (superuser only)."""

    @pytest.mark.asyncio
    async def test_create_tenant_success(
        self, client: AsyncClient, db_session: AsyncSession, superuser_headers: dict
    ):
        """Test successful tenant creation."""
        response = await client.post(
            "/api/tenants",
            headers=superuser_headers,
            json={
                "name": "New Tenant",
                "slug": "new-tenant",
                "domain": "new.example.com",
                "plan": "professional",
                "max_users": 20,
                "max_contacts": 5000,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Tenant"
        assert data["slug"] == "new-tenant"
        assert data["domain"] == "new.example.com"
        assert data["plan"] == "professional"
        assert data["max_users"] == 20
        assert data["max_contacts"] == 5000
        assert data["is_active"] is True
        assert "id" in data
        # Settings should be created automatically
        assert data["settings"] is not None
        assert data["settings"]["company_name"] == "New Tenant"

    @pytest.mark.asyncio
    async def test_create_tenant_minimal(
        self, client: AsyncClient, db_session: AsyncSession, superuser_headers: dict
    ):
        """Test creating tenant with minimal fields."""
        response = await client.post(
            "/api/tenants",
            headers=superuser_headers,
            json={
                "name": "Minimal Tenant",
                "slug": "minimal-tenant",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Minimal Tenant"
        assert data["slug"] == "minimal-tenant"
        assert data["plan"] == "starter"  # Default
        assert data["max_users"] == 5  # Default
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_create_tenant_with_custom_settings(
        self, client: AsyncClient, db_session: AsyncSession, superuser_headers: dict
    ):
        """Test creating tenant with custom settings."""
        response = await client.post(
            "/api/tenants",
            headers=superuser_headers,
            json={
                "name": "Custom Settings Tenant",
                "slug": "custom-settings",
                "settings": {
                    "company_name": "Custom Company",
                    "logo_url": "https://custom.com/logo.png",
                    "primary_color": "#ff0000",
                    "secondary_color": "#00ff00",
                    "accent_color": "#0000ff",
                    "default_language": "es",
                    "default_timezone": "America/New_York",
                    "default_currency": "EUR",
                    "date_format": "DD/MM/YYYY",
                },
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["settings"]["company_name"] == "Custom Company"
        assert data["settings"]["logo_url"] == "https://custom.com/logo.png"
        assert data["settings"]["primary_color"] == "#ff0000"
        assert data["settings"]["secondary_color"] == "#00ff00"
        assert data["settings"]["accent_color"] == "#0000ff"
        assert data["settings"]["default_language"] == "es"

    @pytest.mark.asyncio
    async def test_create_tenant_duplicate_slug(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        superuser_headers: dict,
        test_tenant: Tenant,
    ):
        """Test creating tenant with duplicate slug fails."""
        response = await client.post(
            "/api/tenants",
            headers=superuser_headers,
            json={
                "name": "Another Tenant",
                "slug": test_tenant.slug,  # Duplicate
            },
        )

        assert response.status_code == 400
        assert "slug already exists" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_tenant_duplicate_domain(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        superuser_headers: dict,
        test_tenant: Tenant,
    ):
        """Test creating tenant with duplicate domain fails."""
        response = await client.post(
            "/api/tenants",
            headers=superuser_headers,
            json={
                "name": "Another Tenant",
                "slug": "another-tenant",
                "domain": test_tenant.domain,  # Duplicate
            },
        )

        assert response.status_code == 400
        assert "domain already in use" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_create_tenant_missing_name(
        self, client: AsyncClient, db_session: AsyncSession, superuser_headers: dict
    ):
        """Test creating tenant without name fails."""
        response = await client.post(
            "/api/tenants",
            headers=superuser_headers,
            json={
                "slug": "no-name-tenant",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_tenant_missing_slug(
        self, client: AsyncClient, db_session: AsyncSession, superuser_headers: dict
    ):
        """Test creating tenant without slug fails."""
        response = await client.post(
            "/api/tenants",
            headers=superuser_headers,
            json={
                "name": "No Slug Tenant",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_tenant_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test creating tenant without auth fails."""
        response = await client.post(
            "/api/tenants",
            json={
                "name": "Unauthorized Tenant",
                "slug": "unauthorized",
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_tenant_non_superuser(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating tenant with non-superuser fails."""
        response = await client.post(
            "/api/tenants",
            headers=auth_headers,
            json={
                "name": "Non-Superuser Tenant",
                "slug": "non-superuser",
            },
        )

        assert response.status_code == 403


# --- Tenant Get By ID Tests ---


class TestTenantsGetById:
    """Tests for get tenant by ID endpoint."""

    @pytest.mark.asyncio
    async def test_get_tenant_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
    ):
        """Test getting tenant by ID."""
        response = await client.get(
            f"/api/tenants/{test_tenant.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_tenant.id
        assert data["name"] == test_tenant.name
        assert data["slug"] == test_tenant.slug
        assert data["domain"] == test_tenant.domain
        assert data["is_active"] == test_tenant.is_active
        assert data["plan"] == test_tenant.plan
        assert data["max_users"] == test_tenant.max_users
        assert data["settings"] is not None

    @pytest.mark.asyncio
    async def test_get_tenant_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting non-existent tenant."""
        response = await client.get(
            "/api/tenants/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_tenant_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test getting tenant without auth fails."""
        response = await client.get(f"/api/tenants/{test_tenant.id}")

        assert response.status_code == 401


# --- Tenant Update Tests ---


class TestTenantsUpdate:
    """Tests for tenant update endpoint (superuser only)."""

    @pytest.mark.asyncio
    async def test_update_tenant_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        superuser_headers: dict,
        test_tenant: Tenant,
    ):
        """Test updating tenant."""
        response = await client.patch(
            f"/api/tenants/{test_tenant.id}",
            headers=superuser_headers,
            json={
                "name": "Updated Tenant Name",
                "plan": "enterprise",
                "max_users": 50,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Tenant Name"
        assert data["plan"] == "enterprise"
        assert data["max_users"] == 50
        # Unchanged fields should remain the same
        assert data["slug"] == test_tenant.slug
        assert data["domain"] == test_tenant.domain

    @pytest.mark.asyncio
    async def test_update_tenant_domain(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        superuser_headers: dict,
        test_tenant: Tenant,
    ):
        """Test updating tenant domain."""
        response = await client.patch(
            f"/api/tenants/{test_tenant.id}",
            headers=superuser_headers,
            json={
                "domain": "newdomain.example.com",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["domain"] == "newdomain.example.com"

    @pytest.mark.asyncio
    async def test_update_tenant_deactivate(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        superuser_headers: dict,
        test_tenant: Tenant,
    ):
        """Test deactivating a tenant."""
        response = await client.patch(
            f"/api/tenants/{test_tenant.id}",
            headers=superuser_headers,
            json={
                "is_active": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_update_tenant_not_found(
        self, client: AsyncClient, db_session: AsyncSession, superuser_headers: dict
    ):
        """Test updating non-existent tenant."""
        response = await client.patch(
            "/api/tenants/99999",
            headers=superuser_headers,
            json={"name": "Updated"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_tenant_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test updating tenant without auth fails."""
        response = await client.patch(
            f"/api/tenants/{test_tenant.id}",
            json={"name": "Hacked"},
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_tenant_non_superuser(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
    ):
        """Test updating tenant with non-superuser fails."""
        response = await client.patch(
            f"/api/tenants/{test_tenant.id}",
            headers=auth_headers,
            json={"name": "Updated by Non-Superuser"},
        )

        assert response.status_code == 403


# --- Tenant Delete Tests ---


class TestTenantsDelete:
    """Tests for tenant delete endpoint (superuser only)."""

    @pytest.mark.asyncio
    async def test_delete_tenant_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        superuser_headers: dict,
    ):
        """Test deleting tenant."""
        # Create a tenant to delete
        tenant = Tenant(
            name="To Delete",
            slug="to-delete",
            is_active=True,
        )
        db_session.add(tenant)
        await db_session.flush()

        settings = TenantSettings(
            tenant_id=tenant.id,
            company_name="To Delete Inc",
        )
        db_session.add(settings)
        await db_session.commit()
        tenant_id = tenant.id

        response = await client.delete(
            f"/api/tenants/{tenant_id}",
            headers=superuser_headers,
        )

        assert response.status_code == 204

        # Verify deletion
        result = await db_session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        deleted_tenant = result.scalar_one_or_none()
        assert deleted_tenant is None

    @pytest.mark.asyncio
    async def test_delete_tenant_not_found(
        self, client: AsyncClient, db_session: AsyncSession, superuser_headers: dict
    ):
        """Test deleting non-existent tenant."""
        response = await client.delete(
            "/api/tenants/99999",
            headers=superuser_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_tenant_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test deleting tenant without auth fails."""
        response = await client.delete(f"/api/tenants/{test_tenant.id}")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_tenant_non_superuser(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
    ):
        """Test deleting tenant with non-superuser fails."""
        response = await client.delete(
            f"/api/tenants/{test_tenant.id}",
            headers=auth_headers,
        )

        assert response.status_code == 403


# --- Tenant Settings Tests ---


class TestTenantSettings:
    """Tests for tenant settings endpoints."""

    @pytest.mark.asyncio
    async def test_get_tenant_settings_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
    ):
        """Test getting tenant settings."""
        response = await client.get(
            f"/api/tenants/{test_tenant.id}/settings",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_id"] == test_tenant.id
        assert data["company_name"] == "Test Tenant Inc"
        assert data["logo_url"] == "https://example.com/logo.png"
        assert data["primary_color"] == "#6366f1"
        assert data["secondary_color"] == "#8b5cf6"
        assert data["accent_color"] == "#22c55e"
        assert data["default_language"] == "en"
        assert data["default_timezone"] == "UTC"
        assert data["default_currency"] == "USD"
        assert data["date_format"] == "MM/DD/YYYY"

    @pytest.mark.asyncio
    async def test_get_tenant_settings_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting settings for non-existent tenant."""
        response = await client.get(
            "/api/tenants/99999/settings",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_tenant_settings_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test getting tenant settings without auth fails."""
        response = await client.get(f"/api/tenants/{test_tenant.id}/settings")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_update_tenant_settings_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
    ):
        """Test updating tenant settings."""
        response = await client.patch(
            f"/api/tenants/{test_tenant.id}/settings",
            headers=auth_headers,
            json={
                "company_name": "Updated Company Name",
                "primary_color": "#ff5733",
                "footer_text": "New Footer",
                "default_language": "es",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["company_name"] == "Updated Company Name"
        assert data["primary_color"] == "#ff5733"
        assert data["footer_text"] == "New Footer"
        assert data["default_language"] == "es"
        # Unchanged fields should remain the same
        assert data["logo_url"] == "https://example.com/logo.png"
        assert data["secondary_color"] == "#8b5cf6"

    @pytest.mark.asyncio
    async def test_update_tenant_settings_branding(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
    ):
        """Test updating tenant branding settings."""
        response = await client.patch(
            f"/api/tenants/{test_tenant.id}/settings",
            headers=auth_headers,
            json={
                "logo_url": "https://newlogo.com/logo.png",
                "favicon_url": "https://newlogo.com/favicon.ico",
                "custom_css": "body { background: #f0f0f0; }",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["logo_url"] == "https://newlogo.com/logo.png"
        assert data["favicon_url"] == "https://newlogo.com/favicon.ico"
        assert data["custom_css"] == "body { background: #f0f0f0; }"

    @pytest.mark.asyncio
    async def test_update_tenant_settings_localization(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
    ):
        """Test updating tenant localization settings."""
        response = await client.patch(
            f"/api/tenants/{test_tenant.id}/settings",
            headers=auth_headers,
            json={
                "default_language": "fr",
                "default_timezone": "Europe/Paris",
                "default_currency": "EUR",
                "date_format": "DD/MM/YYYY",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["default_language"] == "fr"
        assert data["default_timezone"] == "Europe/Paris"
        assert data["default_currency"] == "EUR"
        assert data["date_format"] == "DD/MM/YYYY"

    @pytest.mark.asyncio
    async def test_update_tenant_settings_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
    ):
        """Test updating tenant email settings."""
        response = await client.patch(
            f"/api/tenants/{test_tenant.id}/settings",
            headers=auth_headers,
            json={
                "email_from_name": "Test Sender",
                "email_from_address": "noreply@test.com",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email_from_name"] == "Test Sender"
        assert data["email_from_address"] == "noreply@test.com"

    @pytest.mark.asyncio
    async def test_update_tenant_settings_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test updating settings for non-existent tenant."""
        response = await client.patch(
            "/api/tenants/99999/settings",
            headers=auth_headers,
            json={"company_name": "Updated"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_tenant_settings_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test updating tenant settings without auth fails."""
        response = await client.patch(
            f"/api/tenants/{test_tenant.id}/settings",
            json={"company_name": "Hacked"},
        )

        assert response.status_code == 401


# --- Tenant Users Tests ---


class TestTenantUsers:
    """Tests for tenant user management endpoints."""

    @pytest.mark.asyncio
    async def test_list_tenant_users_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
    ):
        """Test listing tenant users when none exist."""
        response = await client.get(
            f"/api/tenants/{test_tenant.id}/users",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_list_tenant_users_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
        test_tenant_user: TenantUser,
    ):
        """Test listing tenant users with existing data."""
        response = await client.get(
            f"/api/tenants/{test_tenant.id}/users",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(u["id"] == test_tenant_user.id for u in data)
        assert any(u["user_id"] == test_tenant_user.user_id for u in data)

    @pytest.mark.asyncio
    async def test_list_tenant_users_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test listing tenant users without auth fails."""
        response = await client.get(f"/api/tenants/{test_tenant.id}/users")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_add_user_to_tenant_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test adding user to tenant."""
        response = await client.post(
            f"/api/tenants/{test_tenant.id}/users",
            headers=auth_headers,
            json={
                "tenant_id": test_tenant.id,
                "user_id": test_user.id,
                "role": "admin",
                "is_primary": True,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["tenant_id"] == test_tenant.id
        assert data["user_id"] == test_user.id
        assert data["role"] == "admin"
        assert data["is_primary"] is True
        assert "id" in data

    @pytest.mark.asyncio
    async def test_add_user_to_tenant_as_member(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test adding user to tenant with member role."""
        response = await client.post(
            f"/api/tenants/{test_tenant.id}/users",
            headers=auth_headers,
            json={
                "tenant_id": test_tenant.id,
                "user_id": test_user.id,
                "role": "member",
                "is_primary": False,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["role"] == "member"
        assert data["is_primary"] is False

    @pytest.mark.asyncio
    async def test_add_user_to_tenant_url_tenant_id_override(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test that URL tenant_id is used even if body has different tenant_id."""
        # Note: The router explicitly sets user_data.tenant_id = tenant_id (from URL)
        response = await client.post(
            f"/api/tenants/{test_tenant.id}/users",
            headers=auth_headers,
            json={
                "tenant_id": 99999,  # Different tenant_id in body
                "user_id": test_user.id,
                "role": "member",
            },
        )

        assert response.status_code == 201
        data = response.json()
        # Should use the URL tenant_id, not the body tenant_id
        assert data["tenant_id"] == test_tenant.id

    @pytest.mark.asyncio
    async def test_add_user_to_tenant_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test adding user to tenant without auth fails."""
        response = await client.post(
            f"/api/tenants/{test_tenant.id}/users",
            json={
                "tenant_id": test_tenant.id,
                "user_id": 1,
                "role": "member",
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_remove_user_from_tenant_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
        test_tenant_user: TenantUser,
    ):
        """Test removing user from tenant."""
        response = await client.delete(
            f"/api/tenants/{test_tenant.id}/users/{test_tenant_user.user_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify deletion
        result = await db_session.execute(
            select(TenantUser).where(TenantUser.id == test_tenant_user.id)
        )
        deleted_tenant_user = result.scalar_one_or_none()
        assert deleted_tenant_user is None

    @pytest.mark.asyncio
    async def test_remove_user_from_tenant_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
    ):
        """Test removing non-existent user from tenant."""
        response = await client.delete(
            f"/api/tenants/{test_tenant.id}/users/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_user_from_tenant_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_tenant: Tenant,
        test_tenant_user: TenantUser,
    ):
        """Test removing user from tenant without auth fails."""
        response = await client.delete(
            f"/api/tenants/{test_tenant.id}/users/{test_tenant_user.user_id}"
        )

        assert response.status_code == 401


# --- Additional Edge Case Tests ---


class TestTenantEdgeCases:
    """Tests for edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_tenant_with_no_settings_public_config(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Test public config for tenant without settings uses defaults."""
        # Create tenant without settings
        tenant = Tenant(
            name="No Settings Tenant",
            slug="no-settings",
            is_active=True,
        )
        db_session.add(tenant)
        await db_session.flush()

        # Add minimal settings (required by foreign key)
        settings = TenantSettings(
            tenant_id=tenant.id,
        )
        db_session.add(settings)
        await db_session.commit()

        response = await client.get(f"/api/tenants/config/{tenant.slug}")

        assert response.status_code == 200
        data = response.json()
        # Should use defaults
        assert data["primary_color"] == "#6366f1"
        assert data["secondary_color"] == "#8b5cf6"
        assert data["accent_color"] == "#22c55e"
        assert data["default_language"] == "en"

    @pytest.mark.asyncio
    async def test_tenant_settings_feature_flags(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
    ):
        """Test updating feature flags in tenant settings."""
        response = await client.patch(
            f"/api/tenants/{test_tenant.id}/settings",
            headers=auth_headers,
            json={
                "feature_flags": '{"ai_enabled": true, "campaigns": false}',
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["feature_flags"] == '{"ai_enabled": true, "campaigns": false}'

    @pytest.mark.asyncio
    async def test_multiple_tenants_sorted_by_name(
        self, client: AsyncClient, db_session: AsyncSession, superuser_headers: dict
    ):
        """Test that tenants list is sorted by name."""
        # Create tenants with specific names
        for name, slug in [("Zebra Co", "zebra"), ("Apple Inc", "apple"), ("Microsoft", "microsoft")]:
            tenant = Tenant(name=name, slug=slug, is_active=True)
            db_session.add(tenant)
            await db_session.flush()
            settings = TenantSettings(tenant_id=tenant.id, company_name=name)
            db_session.add(settings)

        await db_session.commit()

        response = await client.get("/api/tenants", headers=superuser_headers)

        assert response.status_code == 200
        data = response.json()
        names = [t["name"] for t in data]
        # Should be sorted alphabetically
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_create_tenant_with_all_plans(
        self, client: AsyncClient, db_session: AsyncSession, superuser_headers: dict
    ):
        """Test creating tenants with different plans."""
        for plan in ["starter", "professional", "enterprise"]:
            response = await client.post(
                "/api/tenants",
                headers=superuser_headers,
                json={
                    "name": f"{plan.capitalize()} Plan Tenant",
                    "slug": f"{plan}-plan-tenant",
                    "plan": plan,
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["plan"] == plan

    @pytest.mark.asyncio
    async def test_tenant_user_roles(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test creating tenant users with different roles."""
        for role in ["admin", "manager", "member"]:
            # Clean up previous tenant user if exists
            result = await db_session.execute(
                select(TenantUser).where(
                    TenantUser.tenant_id == test_tenant.id,
                    TenantUser.user_id == test_user.id,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                await db_session.delete(existing)
                await db_session.flush()

            response = await client.post(
                f"/api/tenants/{test_tenant.id}/users",
                headers=auth_headers,
                json={
                    "tenant_id": test_tenant.id,
                    "user_id": test_user.id,
                    "role": role,
                },
            )

            assert response.status_code == 201
            data = response.json()
            assert data["role"] == role


class TestDomainConfigLookup:
    """Tests for domain-based tenant configuration lookup."""

    @pytest.mark.asyncio
    async def test_domain_config_returns_full_settings(
        self, client: AsyncClient, db_session: AsyncSession, test_tenant: Tenant
    ):
        """Test domain config lookup returns all expected public config fields."""
        response = await client.get(
            f"/api/tenants/config/domain/{test_tenant.domain}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["tenant_slug"] == test_tenant.slug
        assert data["company_name"] == "Test Tenant Inc"
        assert data["logo_url"] == "https://example.com/logo.png"
        assert data["favicon_url"] == "https://example.com/favicon.ico"
        assert data["primary_color"] == "#6366f1"
        assert data["secondary_color"] == "#8b5cf6"
        assert data["accent_color"] == "#22c55e"
        assert data["footer_text"] == "Test Tenant Footer"
        assert data["privacy_policy_url"] == "https://example.com/privacy"
        assert data["terms_of_service_url"] == "https://example.com/terms"
        assert data["default_language"] == "en"
        assert data["date_format"] == "MM/DD/YYYY"


class TestTenantUserAddRemoveLifecycle:
    """Tests for tenant user add and remove lifecycle."""

    @pytest.mark.asyncio
    async def test_add_then_remove_user_lifecycle(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
        test_user: User,
    ):
        """Test adding a user to a tenant then removing them verifies full lifecycle."""
        # Add user to tenant
        add_response = await client.post(
            f"/api/tenants/{test_tenant.id}/users",
            headers=auth_headers,
            json={
                "tenant_id": test_tenant.id,
                "user_id": test_user.id,
                "role": "admin",
                "is_primary": True,
            },
        )

        assert add_response.status_code == 201
        added_user = add_response.json()
        assert added_user["tenant_id"] == test_tenant.id
        assert added_user["user_id"] == test_user.id
        assert added_user["role"] == "admin"
        assert added_user["is_primary"] is True

        # Verify user appears in tenant users list
        list_response = await client.get(
            f"/api/tenants/{test_tenant.id}/users",
            headers=auth_headers,
        )

        assert list_response.status_code == 200
        users = list_response.json()
        assert any(u["user_id"] == test_user.id for u in users)

        # Remove user from tenant
        remove_response = await client.delete(
            f"/api/tenants/{test_tenant.id}/users/{test_user.id}",
            headers=auth_headers,
        )

        assert remove_response.status_code == 204

        # Verify user no longer in tenant users list
        list_after = await client.get(
            f"/api/tenants/{test_tenant.id}/users",
            headers=auth_headers,
        )

        assert list_after.status_code == 200
        users_after = list_after.json()
        assert not any(u["user_id"] == test_user.id for u in users_after)

    @pytest.mark.asyncio
    async def test_remove_nonexistent_user_from_tenant(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_tenant: Tenant,
    ):
        """Test removing a user that is not in the tenant returns 404."""
        response = await client.delete(
            f"/api/tenants/{test_tenant.id}/users/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404
