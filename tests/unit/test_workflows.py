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


class TestWorkflowRuleEvaluation:
    """Integration tests for workflow rule condition evaluation and action firing."""

    @pytest.mark.asyncio
    async def test_score_gte_matching(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test >= operator: lead score 85 matches condition score >= 80, actions fire."""
        rule = WorkflowRule(
            name="High Score Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="score_changed",
            conditions={"field": "score", "operator": ">=", "value": 80},
            actions=[
                {"type": "create_activity", "activity_type": "call", "subject": "Follow up high-score lead"},
                {"type": "assign_owner", "value": 1},
            ],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        test_lead.score = 85
        await db_session.commit()

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["dry_run"] is True
        assert len(data["results"]) == 1
        result = data["results"][0]
        assert result["status"] == "success"
        assert result["result"]["conditions_met"] is True
        assert len(result["result"]["matched_actions"]) == 2
        action_types = [a["type"] for a in result["result"]["matched_actions"]]
        assert "create_activity" in action_types
        assert "assign_owner" in action_types

    @pytest.mark.asyncio
    async def test_score_gte_not_matching(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test >= operator: lead score 50 does NOT match condition score >= 80, result is skipped."""
        rule = WorkflowRule(
            name="High Score Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="score_changed",
            conditions={"field": "score", "operator": ">=", "value": 80},
            actions=[{"type": "create_activity", "subject": "Follow up"}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        # test_lead has score=50, which is < 80
        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        result = data["results"][0]
        assert result["status"] == "skipped"
        assert result["result"]["reason"] == "Conditions not met"

    @pytest.mark.asyncio
    async def test_score_gte_exact_boundary(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test >= operator at exact boundary: score 80 matches score >= 80."""
        rule = WorkflowRule(
            name="Boundary Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="score_changed",
            conditions={"field": "score", "operator": ">=", "value": 80},
            actions=[{"type": "send_notification", "message": "Boundary hit"}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        test_lead.score = 80
        await db_session.commit()

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_operator_eq(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test == operator: lead status 'new' matches condition status == 'new'."""
        rule = WorkflowRule(
            name="New Lead Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="created",
            conditions={"field": "status", "operator": "==", "value": "new"},
            actions=[{"type": "send_notification", "message": "New lead created"}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "success"
        assert result["result"]["conditions_met"] is True

    @pytest.mark.asyncio
    async def test_operator_eq_not_matching(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test == operator: lead status 'new' does NOT match condition status == 'qualified'."""
        rule = WorkflowRule(
            name="Qualified Lead Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="status_changed",
            conditions={"field": "status", "operator": "==", "value": "qualified"},
            actions=[{"type": "create_activity", "subject": "Qualify follow-up"}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_operator_gt(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test > operator: lead score 90 matches condition score > 80."""
        rule = WorkflowRule(
            name="Score GT Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="score_changed",
            conditions={"field": "score", "operator": ">", "value": 80},
            actions=[{"type": "assign_owner", "value": 1}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        test_lead.score = 90
        await db_session.commit()

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_operator_gt_not_matching_at_boundary(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test > operator: lead score 80 does NOT match condition score > 80 (strict gt)."""
        rule = WorkflowRule(
            name="Score GT Strict Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="score_changed",
            conditions={"field": "score", "operator": ">", "value": 80},
            actions=[{"type": "assign_owner", "value": 1}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        test_lead.score = 80
        await db_session.commit()

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_operator_lt(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test < operator: lead score 50 matches condition score < 60."""
        rule = WorkflowRule(
            name="Low Score Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="score_changed",
            conditions={"field": "score", "operator": "<", "value": 60},
            actions=[{"type": "update_status", "value": "unqualified"}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "success"
        assert result["result"]["matched_actions"][0]["type"] == "update_status"

    @pytest.mark.asyncio
    async def test_operator_lt_not_matching(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test < operator: lead score 50 does NOT match condition score < 30."""
        rule = WorkflowRule(
            name="Very Low Score Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="score_changed",
            conditions={"field": "score", "operator": "<", "value": 30},
            actions=[{"type": "update_status", "value": "lost"}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_operator_lte(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test <= operator: lead score 50 matches condition score <= 50."""
        rule = WorkflowRule(
            name="LTE Boundary Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="score_changed",
            conditions={"field": "score", "operator": "<=", "value": 50},
            actions=[{"type": "send_notification", "message": "Low-score lead"}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_operator_lte_not_matching(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test <= operator: lead score 50 does NOT match condition score <= 40."""
        rule = WorkflowRule(
            name="LTE Miss Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="score_changed",
            conditions={"field": "score", "operator": "<=", "value": 40},
            actions=[{"type": "send_notification", "message": "Should not fire"}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_operator_contains(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test contains operator: lead company_name 'Potential Client LLC' contains 'Client'."""
        rule = WorkflowRule(
            name="Company Contains Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="created",
            conditions={"field": "company_name", "operator": "contains", "value": "Client"},
            actions=[{"type": "create_activity", "subject": "Research company"}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_operator_contains_not_matching(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test contains operator: lead company_name does NOT contain 'Acme'."""
        rule = WorkflowRule(
            name="Company Contains Miss",
            is_active=True,
            trigger_entity="lead",
            trigger_event="created",
            conditions={"field": "company_name", "operator": "contains", "value": "Acme"},
            actions=[{"type": "create_activity", "subject": "Should not fire"}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_operator_neq(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test != operator: lead status 'new' matches condition status != 'converted'."""
        rule = WorkflowRule(
            name="Not Converted Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="updated",
            conditions={"field": "status", "operator": "!=", "value": "converted"},
            actions=[{"type": "send_notification", "message": "Lead not yet converted"}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_operator_neq_not_matching(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test != operator: lead status 'new' does NOT match condition status != 'new'."""
        rule = WorkflowRule(
            name="Not New Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="updated",
            conditions={"field": "status", "operator": "!=", "value": "new"},
            actions=[{"type": "send_notification", "message": "Should not fire"}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_no_conditions_always_matches(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test that a rule with no conditions always matches (fires for any entity)."""
        rule = WorkflowRule(
            name="Always Fire Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="created",
            conditions=None,
            actions=[{"type": "send_notification", "message": "Universal trigger"}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "success"
        assert result["result"]["conditions_met"] is True

    @pytest.mark.asyncio
    async def test_condition_on_nonexistent_field_skips(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test that a condition on a field not present on the entity results in skip."""
        rule = WorkflowRule(
            name="Bad Field Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="updated",
            conditions={"field": "nonexistent_field", "operator": "==", "value": "anything"},
            actions=[{"type": "send_notification", "message": "Should not fire"}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_dry_run_does_not_create_execution_record(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test that dry-run does NOT persist a WorkflowExecution record."""
        rule = WorkflowRule(
            name="Dry Run Check",
            is_active=True,
            trigger_entity="lead",
            trigger_event="score_changed",
            conditions={"field": "score", "operator": ">=", "value": 0},
            actions=[{"type": "create_activity", "subject": "test"}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )
        assert response.status_code == 200
        assert response.json()["results"][0]["status"] == "success"

        # Verify no execution was persisted
        exec_result = await db_session.execute(
            select(WorkflowExecution).where(WorkflowExecution.rule_id == rule.id)
        )
        assert exec_result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_actions_contain_full_payload(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test that matched_actions returns the complete action definitions from the rule."""
        rule = WorkflowRule(
            name="Full Action Payload Rule",
            is_active=True,
            trigger_entity="lead",
            trigger_event="score_changed",
            conditions={"field": "score", "operator": ">=", "value": 0},
            actions=[
                {"type": "create_activity", "activity_type": "call", "subject": "Follow up high-score lead"},
                {"type": "assign_owner", "value": 42},
                {"type": "update_status", "value": "qualified"},
            ],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        result = response.json()["results"][0]
        assert result["status"] == "success"
        actions = result["result"]["matched_actions"]
        assert len(actions) == 3

        # Verify each action's full payload is preserved
        create_action = next(a for a in actions if a["type"] == "create_activity")
        assert create_action["activity_type"] == "call"
        assert create_action["subject"] == "Follow up high-score lead"

        assign_action = next(a for a in actions if a["type"] == "assign_owner")
        assert assign_action["value"] == 42

        status_action = next(a for a in actions if a["type"] == "update_status")
        assert status_action["value"] == "qualified"

    @pytest.mark.asyncio
    async def test_inactive_rule_not_evaluated(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_lead: Lead,
    ):
        """Test that an inactive rule returns empty results (not evaluated)."""
        rule = WorkflowRule(
            name="Inactive Rule",
            is_active=False,
            trigger_entity="lead",
            trigger_event="score_changed",
            conditions={"field": "score", "operator": ">=", "value": 0},
            actions=[{"type": "send_notification", "message": "Should not fire"}],
            created_by_id=test_user.id,
        )
        db_session.add(rule)
        await db_session.commit()
        await db_session.refresh(rule)

        response = await client.post(
            f"/api/workflows/{rule.id}/test",
            headers=auth_headers,
            json={"entity_type": "lead", "entity_id": test_lead.id},
        )

        assert response.status_code == 200
        data = response.json()
        # evaluate_rules filters by is_active, so inactive rule produces no results
        assert data["results"] == []


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
