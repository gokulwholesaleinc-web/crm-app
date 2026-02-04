"""
Unit tests for authentication endpoints.

Tests for register, login, and get_me endpoints.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.auth.security import verify_password, get_password_hash


class TestAuthRegister:
    """Tests for user registration endpoint."""

    @pytest.mark.asyncio
    async def test_register_user_success(self, client: AsyncClient, db_session: AsyncSession):
        """Test successful user registration."""
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "securepassword123",
                "full_name": "New User",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["full_name"] == "New User"
        assert "id" in data
        assert "password" not in data
        assert "hashed_password" not in data

    @pytest.mark.asyncio
    async def test_register_duplicate_email(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test registration with existing email fails."""
        response = await client.post(
            "/api/auth/register",
            json={
                "email": test_user.email,
                "password": "anotherpassword123",
                "full_name": "Another User",
            },
        )

        assert response.status_code == 400
        assert "already registered" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client: AsyncClient, db_session: AsyncSession):
        """Test registration with invalid email format."""
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "invalid-email",
                "password": "securepassword123",
                "full_name": "Test User",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_required_fields(self, client: AsyncClient, db_session: AsyncSession):
        """Test registration with missing required fields."""
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_register_with_optional_fields(self, client: AsyncClient, db_session: AsyncSession):
        """Test registration with optional fields."""
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "withphone@example.com",
                "password": "securepassword123",
                "full_name": "User With Phone",
                "phone": "+1-555-0199",
                "job_title": "Developer",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["phone"] == "+1-555-0199"
        assert data["job_title"] == "Developer"


class TestAuthLogin:
    """Tests for login endpoints."""

    @pytest.mark.asyncio
    async def test_login_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test successful login with form data."""
        response = await client.post(
            "/api/auth/login",
            data={
                "username": test_user.email,
                "password": "testpassword123",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_json_success(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test successful login with JSON body."""
        response = await client.post(
            "/api/auth/login/json",
            json={
                "email": test_user.email,
                "password": "testpassword123",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test login with wrong password fails."""
        response = await client.post(
            "/api/auth/login",
            data={
                "username": test_user.email,
                "password": "wrongpassword",
            },
        )

        assert response.status_code == 401
        assert "incorrect" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient, db_session: AsyncSession):
        """Test login with non-existent email fails."""
        response = await client.post(
            "/api/auth/login",
            data={
                "username": "nonexistent@example.com",
                "password": "anypassword",
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_json_wrong_password(
        self, client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Test JSON login with wrong password fails."""
        response = await client.post(
            "/api/auth/login/json",
            json={
                "email": test_user.email,
                "password": "wrongpassword",
            },
        )

        assert response.status_code == 401


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
