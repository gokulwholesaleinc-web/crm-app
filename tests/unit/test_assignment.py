"""
Unit tests for lead auto-assignment endpoints.

Tests CRUD operations, round-robin assignment, load-balance assignment, and filter matching.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.leads.models import Lead, LeadSource
from src.assignment.models import AssignmentRule
from src.assignment.service import AssignmentService


@pytest.fixture
async def second_user(db_session: AsyncSession) -> User:
    """Create a second test user for assignment."""
    from src.auth.security import get_password_hash
    user = User(
        email="seconduser@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Second User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def third_user(db_session: AsyncSession) -> User:
    """Create a third test user for assignment."""
    from src.auth.security import get_password_hash
    user = User(
        email="thirduser@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Third User",
        is_active=True,
        is_superuser=False,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def test_assignment_rule(
    db_session: AsyncSession, test_user: User, second_user: User
) -> AssignmentRule:
    """Create a test round-robin assignment rule."""
    rule = AssignmentRule(
        name="Round Robin Rule",
        assignment_type="round_robin",
        user_ids=[test_user.id, second_user.id],
        filters=None,
        last_assigned_index=-1,
        is_active=True,
        created_by_id=test_user.id,
    )
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)
    return rule


class TestAssignmentRuleCRUD:
    """Tests for assignment rule CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_create_rule(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict, test_user: User
    ):
        """Test creating a new assignment rule."""
        response = await client.post(
            "/api/assignment-rules",
            headers=auth_headers,
            json={
                "name": "New Rule",
                "assignment_type": "round_robin",
                "user_ids": [test_user.id],
                "is_active": True,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Rule"
        assert data["assignment_type"] == "round_robin"
        assert data["is_active"] is True
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_rule_with_filters(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict, test_user: User
    ):
        """Test creating rule with filters."""
        response = await client.post(
            "/api/assignment-rules",
            headers=auth_headers,
            json={
                "name": "Filtered Rule",
                "assignment_type": "load_balance",
                "user_ids": [test_user.id],
                "filters": {"source_id": 1, "industry": "Technology"},
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["filters"]["source_id"] == 1

    @pytest.mark.asyncio
    async def test_list_rules(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_assignment_rule: AssignmentRule,
    ):
        """Test listing assignment rules."""
        response = await client.get(
            "/api/assignment-rules",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_get_rule(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_assignment_rule: AssignmentRule,
    ):
        """Test getting a rule by ID."""
        response = await client.get(
            f"/api/assignment-rules/{test_assignment_rule.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Round Robin Rule"

    @pytest.mark.asyncio
    async def test_get_rule_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting non-existent rule."""
        response = await client.get(
            "/api/assignment-rules/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_rule(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_assignment_rule: AssignmentRule,
    ):
        """Test updating an assignment rule."""
        response = await client.put(
            f"/api/assignment-rules/{test_assignment_rule.id}",
            headers=auth_headers,
            json={"name": "Updated Rule", "is_active": False},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Rule"
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_delete_rule(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test deleting an assignment rule."""
        rule = AssignmentRule(
            name="To Delete",
            assignment_type="round_robin",
            user_ids=[test_user.id],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.delete(
            f"/api/assignment-rules/{rule.id}",
            headers=auth_headers,
        )
        assert response.status_code == 204


class TestRoundRobinAssignment:
    """Tests for round-robin lead assignment logic."""

    @pytest.mark.asyncio
    async def test_round_robin_cycles_through_users(
        self,
        db_session: AsyncSession,
        test_user: User,
        second_user: User,
        test_assignment_rule: AssignmentRule,
    ):
        """Test that round-robin correctly cycles through users."""
        service = AssignmentService(db_session)

        # First assignment should go to first user (index 0)
        user1 = await service.assign_lead({})
        assert user1 == test_user.id

        # Second assignment should go to second user (index 1)
        user2 = await service.assign_lead({})
        assert user2 == second_user.id

        # Third assignment should cycle back to first user (index 0)
        user3 = await service.assign_lead({})
        assert user3 == test_user.id

    @pytest.mark.asyncio
    async def test_round_robin_updates_index(
        self,
        db_session: AsyncSession,
        test_user: User,
        second_user: User,
        test_assignment_rule: AssignmentRule,
    ):
        """Test that last_assigned_index is updated correctly."""
        service = AssignmentService(db_session)

        await service.assign_lead({})
        await db_session.refresh(test_assignment_rule)
        assert test_assignment_rule.last_assigned_index == 0

        await service.assign_lead({})
        await db_session.refresh(test_assignment_rule)
        assert test_assignment_rule.last_assigned_index == 1


class TestLoadBalanceAssignment:
    """Tests for load-balance lead assignment logic."""

    @pytest.mark.asyncio
    async def test_load_balance_assigns_to_user_with_fewest_leads(
        self,
        db_session: AsyncSession,
        test_user: User,
        second_user: User,
    ):
        """Test that load balance assigns to user with fewest active leads."""
        # Create a load balance rule
        rule = AssignmentRule(
            name="Load Balance Rule",
            assignment_type="load_balance",
            user_ids=[test_user.id, second_user.id],
            is_active=True,
            created_by_id=test_user.id,
        )
        db_session.add(rule)

        # Give test_user 3 active leads
        for i in range(3):
            lead = Lead(
                first_name=f"Lead{i}",
                last_name="Test",
                status="new",
                owner_id=test_user.id,
                created_by_id=test_user.id,
            )
            db_session.add(lead)

        # Give second_user 1 active lead
        lead = Lead(
            first_name="Lead0",
            last_name="Second",
            status="new",
            owner_id=second_user.id,
            created_by_id=second_user.id,
        )
        db_session.add(lead)

        await db_session.commit()

        service = AssignmentService(db_session)
        assigned = await service.assign_lead({})

        # Should assign to second_user who has fewer leads
        assert assigned == second_user.id


class TestAssignmentFilterMatching:
    """Tests for assignment rule filter matching."""

    @pytest.mark.asyncio
    async def test_filter_by_source_id_matches(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test that source_id filter matches correctly."""
        rule = AssignmentRule(
            name="Source Filter Rule",
            assignment_type="round_robin",
            user_ids=[test_user.id],
            filters={"source_id": 5},
            is_active=True,
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()

        service = AssignmentService(db_session)

        # Matching lead
        result = await service.assign_lead({"source_id": 5})
        assert result == test_user.id

    @pytest.mark.asyncio
    async def test_filter_by_source_id_no_match(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test that non-matching source_id returns None."""
        rule = AssignmentRule(
            name="Source Filter Rule",
            assignment_type="round_robin",
            user_ids=[test_user.id],
            filters={"source_id": 5},
            is_active=True,
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()

        service = AssignmentService(db_session)

        # Non-matching lead
        result = await service.assign_lead({"source_id": 99})
        assert result is None

    @pytest.mark.asyncio
    async def test_filter_by_industry(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test filtering by industry."""
        rule = AssignmentRule(
            name="Industry Filter",
            assignment_type="round_robin",
            user_ids=[test_user.id],
            filters={"industry": "Technology"},
            is_active=True,
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()

        service = AssignmentService(db_session)

        assert await service.assign_lead({"industry": "Technology"}) == test_user.id
        assert await service.assign_lead({"industry": "Finance"}) is None

    @pytest.mark.asyncio
    async def test_no_filters_matches_all(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test that a rule with no filters matches any lead."""
        rule = AssignmentRule(
            name="No Filter Rule",
            assignment_type="round_robin",
            user_ids=[test_user.id],
            filters=None,
            is_active=True,
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()

        service = AssignmentService(db_session)
        result = await service.assign_lead({"anything": "goes"})
        assert result == test_user.id

    @pytest.mark.asyncio
    async def test_no_active_rules_returns_none(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Test that if no active rules exist, returns None."""
        # Create an inactive rule
        rule = AssignmentRule(
            name="Inactive Rule",
            assignment_type="round_robin",
            user_ids=[test_user.id],
            is_active=False,
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()

        service = AssignmentService(db_session)
        result = await service.assign_lead({})
        assert result is None


class TestAssignmentStats:
    """Tests for assignment statistics endpoint."""

    @pytest.mark.asyncio
    async def test_get_stats(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_assignment_rule: AssignmentRule,
    ):
        """Test getting assignment stats."""
        response = await client.get(
            f"/api/assignment-rules/{test_assignment_rule.id}/stats",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2  # Two users in the rule
        assert all("user_id" in s and "active_leads_count" in s for s in data)


class TestAssignmentUnauthorized:
    """Tests for unauthorized access."""

    @pytest.mark.asyncio
    async def test_create_rule_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.post(
            "/api/assignment-rules",
            json={"name": "Test", "assignment_type": "round_robin", "user_ids": [1]},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_rules_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.get("/api/assignment-rules")
        assert response.status_code == 401
