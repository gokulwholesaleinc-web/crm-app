"""
Unit tests for workflow automation endpoints.

Tests for CRUD operations on workflow rules, execution history, and dry-run testing.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.leads.models import Lead, LeadSource
from src.workflows.models import WorkflowRule, WorkflowExecution


@pytest.fixture
async def test_workflow_rule(db_session: AsyncSession, test_user: User) -> WorkflowRule:
    """Create a test workflow rule."""
    rule = WorkflowRule(
        name="High Score Lead Alert",
        description="Trigger when lead score is >= 80",
        is_active=True,
        trigger_entity="lead",
        trigger_event="score_changed",
        conditions={"field": "score", "operator": ">=", "value": 80},
        actions=[
            {"type": "assign_owner", "value": 1},
            {"type": "create_activity", "activity_type": "call", "subject": "Follow up high-score lead"},
        ],
        created_by_id=test_user.id,
    )
    db_session.add(rule)
    await db_session.commit()
    await db_session.refresh(rule)
    return rule


class TestWorkflowRulesCRUD:
    """Tests for workflow rule CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_create_workflow_rule(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating a new workflow rule."""
        response = await client.post(
            "/api/workflows",
            headers=auth_headers,
            json={
                "name": "New Lead Notification",
                "description": "Notify when a new lead is created",
                "is_active": True,
                "trigger_entity": "lead",
                "trigger_event": "created",
                "conditions": {"field": "status", "operator": "==", "value": "new"},
                "actions": [{"type": "send_notification", "message": "New lead created"}],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Lead Notification"
        assert data["trigger_entity"] == "lead"
        assert data["trigger_event"] == "created"
        assert data["is_active"] is True
        assert data["conditions"]["field"] == "status"
        assert len(data["actions"]) == 1
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_workflow_rule_minimal(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating rule with minimal fields."""
        response = await client.post(
            "/api/workflows",
            headers=auth_headers,
            json={
                "name": "Simple Rule",
                "trigger_entity": "contact",
                "trigger_event": "updated",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Simple Rule"
        assert data["conditions"] is None
        assert data["actions"] is None

    @pytest.mark.asyncio
    async def test_list_workflow_rules(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_workflow_rule: WorkflowRule,
    ):
        """Test listing workflow rules."""
        response = await client.get(
            "/api/workflows",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert any(r["id"] == test_workflow_rule.id for r in data)

    @pytest.mark.asyncio
    async def test_list_workflow_rules_filter_active(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_workflow_rule: WorkflowRule,
    ):
        """Test filtering rules by active status."""
        response = await client.get(
            "/api/workflows",
            headers=auth_headers,
            params={"is_active": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(r["is_active"] for r in data)

    @pytest.mark.asyncio
    async def test_list_workflow_rules_filter_entity(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_workflow_rule: WorkflowRule,
    ):
        """Test filtering rules by trigger entity."""
        response = await client.get(
            "/api/workflows",
            headers=auth_headers,
            params={"trigger_entity": "lead"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(r["trigger_entity"] == "lead" for r in data)

    @pytest.mark.asyncio
    async def test_get_workflow_rule(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_workflow_rule: WorkflowRule,
    ):
        """Test getting a workflow rule by ID."""
        response = await client.get(
            f"/api/workflows/{test_workflow_rule.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_workflow_rule.id
        assert data["name"] == "High Score Lead Alert"

    @pytest.mark.asyncio
    async def test_get_workflow_rule_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting non-existent rule returns 404."""
        response = await client.get(
            "/api/workflows/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_workflow_rule(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_workflow_rule: WorkflowRule,
    ):
        """Test updating a workflow rule."""
        response = await client.put(
            f"/api/workflows/{test_workflow_rule.id}",
            headers=auth_headers,
            json={
                "name": "Updated Rule Name",
                "is_active": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Rule Name"
        assert data["is_active"] is False
        # Unchanged fields
        assert data["trigger_entity"] == "lead"

    @pytest.mark.asyncio
    async def test_update_workflow_rule_conditions(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_workflow_rule: WorkflowRule,
    ):
        """Test updating rule conditions."""
        response = await client.put(
            f"/api/workflows/{test_workflow_rule.id}",
            headers=auth_headers,
            json={
                "conditions": {"field": "score", "operator": ">=", "value": 90},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["conditions"]["value"] == 90

    @pytest.mark.asyncio
    async def test_delete_workflow_rule(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test deleting a workflow rule."""
        rule = WorkflowRule(
            name="To Delete",
            trigger_entity="lead",
            trigger_event="created",
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)
        rule_id = rule.id

        response = await client.delete(
            f"/api/workflows/{rule_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        result = await db_session.execute(
            select(WorkflowRule).where(WorkflowRule.id == rule_id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_delete_rule_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test deleting non-existent rule returns 404."""
        response = await client.delete(
            "/api/workflows/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestWorkflowExecutions:
    """Tests for workflow execution history."""

    @pytest.mark.asyncio
    async def test_get_executions_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_workflow_rule: WorkflowRule,
    ):
        """Test getting executions when none exist."""
        response = await client.get(
            f"/api/workflows/{test_workflow_rule.id}/executions",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data == []

    @pytest.mark.asyncio
    async def test_get_executions_with_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_workflow_rule: WorkflowRule,
    ):
        """Test getting executions with data."""
        execution = WorkflowExecution(
            rule_id=test_workflow_rule.id,
            entity_type="lead",
            entity_id=1,
            status="success",
            result={"matched_actions": []},
        )
        db_session.add(execution)
        await db_session.commit()

        response = await client.get(
            f"/api/workflows/{test_workflow_rule.id}/executions",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "success"
        assert data[0]["entity_type"] == "lead"

    @pytest.mark.asyncio
    async def test_get_executions_rule_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting executions for non-existent rule."""
        response = await client.get(
            "/api/workflows/99999/executions",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestWorkflowTest:
    """Tests for workflow dry-run/test endpoint."""

    @pytest.mark.asyncio
    async def test_dry_run_matching_rule(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_workflow_rule: WorkflowRule,
        test_lead: Lead,
    ):
        """Test dry-run with a lead that matches the rule conditions."""
        # Set lead score to match the >= 80 condition
        test_lead.score = 85
        await db_session.commit()

        response = await client.post(
            f"/api/workflows/{test_workflow_rule.id}/test",
            headers=auth_headers,
            json={
                "entity_type": "lead",
                "entity_id": test_lead.id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True
        assert data["rule_id"] == test_workflow_rule.id

    @pytest.mark.asyncio
    async def test_dry_run_non_matching_rule(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_workflow_rule: WorkflowRule,
        test_lead: Lead,
    ):
        """Test dry-run with a lead that does not match conditions."""
        # Lead score = 50 from fixture, condition requires >= 80
        response = await client.post(
            f"/api/workflows/{test_workflow_rule.id}/test",
            headers=auth_headers,
            json={
                "entity_type": "lead",
                "entity_id": test_lead.id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True

    @pytest.mark.asyncio
    async def test_dry_run_entity_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_workflow_rule: WorkflowRule,
    ):
        """Test dry-run with non-existent entity."""
        response = await client.post(
            f"/api/workflows/{test_workflow_rule.id}/test",
            headers=auth_headers,
            json={
                "entity_type": "lead",
                "entity_id": 99999,
            },
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_dry_run_rule_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test dry-run with non-existent rule."""
        response = await client.post(
            "/api/workflows/99999/test",
            headers=auth_headers,
            json={
                "entity_type": "lead",
                "entity_id": 1,
            },
        )

        assert response.status_code == 404


class TestWorkflowsUnauthorized:
    """Tests for unauthorized access to workflow endpoints."""

    @pytest.mark.asyncio
    async def test_create_rule_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.post(
            "/api/workflows",
            json={"name": "Test", "trigger_entity": "lead", "trigger_event": "created"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_rules_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.get("/api/workflows")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_rule_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_workflow_rule: WorkflowRule,
    ):
        response = await client.get(f"/api/workflows/{test_workflow_rule.id}")
        assert response.status_code == 401
