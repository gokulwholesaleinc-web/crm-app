"""
Unit tests for authentication endpoints.

Tests for auth endpoints — password login removed, Google OAuth is the sole flow.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import get_password_hash, verify_password
from src.whitelabel.models import Tenant, TenantUser



class TestPasswordLoginRemoved:
    """Password login endpoints must be gone — Google OAuth is the only flow."""

    @pytest.mark.asyncio
    async def test_login_form_rejected(self, client: AsyncClient, db_session: AsyncSession):
        """POST /api/auth/login must not accept password credentials."""
        response = await client.post(
            "/api/auth/login",
            data={"username": "any@example.com", "password": "any"},
        )
        assert response.status_code in (404, 405)

    @pytest.mark.asyncio
    async def test_login_json_rejected(self, client: AsyncClient, db_session: AsyncSession):
        """POST /api/auth/login/json must not accept password credentials."""
        response = await client.post(
            "/api/auth/login/json",
            json={"email": "any@example.com", "password": "any"},
        )
        assert response.status_code in (404, 405)


class TestAuthGetMe:
    """Tests for get current user endpoint."""

    @pytest.mark.asyncio
    async def test_get_me_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ):
        """Test getting current user profile."""
        response = await client.get("/api/auth/me", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_user.id
        assert data["email"] == test_user.email
        assert data["full_name"] == test_user.full_name
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_get_me_without_token(self, client: AsyncClient, db_session: AsyncSession):
        """Test getting current user without authentication fails."""
        response = await client.get("/api/auth/me")

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_invalid_token(self, client: AsyncClient, db_session: AsyncSession):
        """Test getting current user with invalid token fails."""
        response = await client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer invalid_token_here"},
        )

        assert response.status_code == 401


class TestAuthUpdateMe:
    """Tests for update current user endpoint."""

    @pytest.mark.asyncio
    async def test_update_me_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ):
        """Test updating current user profile."""
        response = await client.patch(
            "/api/auth/me",
            headers=auth_headers,
            json={
                "full_name": "Updated Name",
                "phone": "+1-555-9999",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == "Updated Name"
        assert data["phone"] == "+1-555-9999"
        assert data["email"] == test_user.email  # Email unchanged

    @pytest.mark.asyncio
    async def test_update_me_partial(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ):
        """Test partial update of user profile."""
        response = await client.patch(
            "/api/auth/me",
            headers=auth_headers,
            json={
                "job_title": "Senior Developer",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["job_title"] == "Senior Developer"
        assert data["full_name"] == test_user.full_name  # Other fields unchanged


class TestAuthListUsers:
    """Tests for list users endpoint."""

    @pytest.mark.asyncio
    async def test_list_users_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ):
        """Test listing users."""
        response = await client.get("/api/auth/users", headers=auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(u["id"] == test_user.id for u in data)

    @pytest.mark.asyncio
    async def test_list_users_pagination(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User, auth_headers: dict
    ):
        """Test listing users with pagination."""
        response = await client.get(
            "/api/auth/users",
            headers=auth_headers,
            params={"skip": 0, "limit": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10


class TestPasswordSecurity:
    """Tests for password hashing and verification."""

    def test_password_hash_is_different(self):
        """Test that password hash is different from plain password."""
        password = "mysecretpassword"
        hashed = get_password_hash(password)

        assert hashed != password
        assert len(hashed) > len(password)

    def test_password_verification_success(self):
        """Test password verification with correct password."""
        password = "mysecretpassword"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_password_verification_failure(self):
        """Test password verification with wrong password."""
        password = "mysecretpassword"
        hashed = get_password_hash(password)

        assert verify_password("wrongpassword", hashed) is False

    def test_same_password_different_hashes(self):
        """Test that same password produces different hashes (salt)."""
        password = "mysecretpassword"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        assert hash1 != hash2
        # But both should verify
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True
