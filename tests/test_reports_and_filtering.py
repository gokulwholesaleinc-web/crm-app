"""Tests for Custom Reports and Advanced Filtering features.

Tests cover:
- Core filtering engine (apply_filter_condition, parse_filter_group, apply_filters_to_query)
- Report execution (count, sum, avg, min, max metrics with group_by)
- Report CSV export
- Report templates listing
- Saved report CRUD via API
- Saved filter CRUD via API
- Advanced filters on entity list endpoints (leads, contacts, companies, opportunities, activities)
"""

import sys
import json
import pytest

sys.path.insert(0, "/Users/harshvarma/crm-app/backend")

from src.leads.models import Lead, LeadSource
from src.companies.models import Company
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.contacts.models import Contact
from src.reports.models import SavedReport
from src.filters.models import SavedFilter
from src.reports.service import ReportExecutor, REPORT_TEMPLATES
from src.reports.schemas import ReportDefinition
from src.core.filtering import apply_filter_condition, parse_filter_group, apply_filters_to_query
from sqlalchemy import select


# ============================================================
# Filtering unit tests
# ============================================================

class TestFilterConditions:
    """Test individual filter condition operators."""

    def test_eq_operator(self):
        cond = apply_filter_condition(Lead, "status", "eq", "new")
        assert cond is not None

    def test_neq_operator(self):
        cond = apply_filter_condition(Lead, "status", "neq", "lost")
        assert cond is not None

    def test_contains_operator(self):
        cond = apply_filter_condition(Lead, "first_name", "contains", "john")
        assert cond is not None

    def test_not_contains_operator(self):
        cond = apply_filter_condition(Lead, "first_name", "not_contains", "john")
        assert cond is not None

    def test_gt_operator(self):
        cond = apply_filter_condition(Lead, "score", "gt", 50)
        assert cond is not None

    def test_lt_operator(self):
        cond = apply_filter_condition(Lead, "score", "lt", 50)
        assert cond is not None

    def test_gte_operator(self):
        cond = apply_filter_condition(Lead, "score", "gte", 50)
        assert cond is not None

    def test_lte_operator(self):
        cond = apply_filter_condition(Lead, "score", "lte", 50)
        assert cond is not None

    def test_in_operator(self):
        cond = apply_filter_condition(Lead, "status", "in", ["new", "contacted"])
        assert cond is not None

    def test_not_in_operator(self):
        cond = apply_filter_condition(Lead, "status", "not_in", ["lost", "converted"])
        assert cond is not None

    def test_is_empty_operator(self):
        cond = apply_filter_condition(Lead, "email", "is_empty", None)
        assert cond is not None

    def test_is_not_empty_operator(self):
        cond = apply_filter_condition(Lead, "email", "is_not_empty", None)
        assert cond is not None

    def test_between_operator(self):
        cond = apply_filter_condition(Lead, "score", "between", [20, 80])
        assert cond is not None

    def test_unknown_field_raises_error(self):
        with pytest.raises(ValueError, match="Unknown field"):
            apply_filter_condition(Lead, "nonexistent_field", "eq", "test")

    def test_unknown_operator_raises_error(self):
        with pytest.raises(ValueError, match="Unknown operator"):
            apply_filter_condition(Lead, "status", "invalid_op", "test")


class TestFilterGroups:
    """Test AND/OR filter group parsing."""

    def test_and_group(self):
        filter_def = {
            "operator": "and",
            "conditions": [
                {"field": "status", "op": "eq", "value": "new"},
                {"field": "score", "op": "gte", "value": 50},
            ],
        }
        result = parse_filter_group(Lead, filter_def)
        assert result is not None

    def test_or_group(self):
        filter_def = {
            "operator": "or",
            "conditions": [
                {"field": "status", "op": "eq", "value": "new"},
                {"field": "status", "op": "eq", "value": "contacted"},
            ],
        }
        result = parse_filter_group(Lead, filter_def)
        assert result is not None

    def test_nested_group(self):
        filter_def = {
            "operator": "and",
            "conditions": [
                {"field": "score", "op": "gte", "value": 50},
                {
                    "operator": "or",
                    "conditions": [
                        {"field": "status", "op": "eq", "value": "new"},
                        {"field": "status", "op": "eq", "value": "contacted"},
                    ],
                },
            ],
        }
        result = parse_filter_group(Lead, filter_def)
        assert result is not None

    def test_empty_conditions_returns_none(self):
        filter_def = {"operator": "and", "conditions": []}
        result = parse_filter_group(Lead, filter_def)
        assert result is None

    def test_default_operator_is_and(self):
        filter_def = {
            "conditions": [
                {"field": "status", "op": "eq", "value": "new"},
            ],
        }
        result = parse_filter_group(Lead, filter_def)
        assert result is not None

    def test_single_condition_shorthand(self):
        filter_def = {"field": "status", "op": "eq", "value": "new"}
        result = parse_filter_group(Lead, filter_def)
        assert result is not None


class TestApplyFiltersToQuery:
    """Test applying filters to a SQLAlchemy query."""

    def test_apply_valid_filter(self):
        query = select(Lead)
        filters = {
            "operator": "and",
            "conditions": [
                {"field": "status", "op": "eq", "value": "new"},
            ],
        }
        result_query = apply_filters_to_query(query, Lead, filters)
        assert result_query is not None

    def test_apply_none_filter_returns_same_query(self):
        query = select(Lead)
        result_query = apply_filters_to_query(query, Lead, None)
        assert result_query is query

    def test_apply_empty_filter_returns_same_query(self):
        query = select(Lead)
        result_query = apply_filters_to_query(query, Lead, {})
        assert result_query is query


# ============================================================
# Report template tests
# ============================================================

class TestReportTemplates:
    """Test pre-built report templates."""

    def test_templates_exist(self):
        assert len(REPORT_TEMPLATES) == 10

    def test_pipeline_by_stage_template(self):
        tmpl = next(t for t in REPORT_TEMPLATES if t["id"] == "pipeline_by_stage")
        assert tmpl["entity_type"] == "opportunities"
        assert tmpl["group_by"] == "pipeline_stage_id"
        assert tmpl["metric"] == "count"

    def test_revenue_by_month_template(self):
        tmpl = next(t for t in REPORT_TEMPLATES if t["id"] == "revenue_by_month")
        assert tmpl["entity_type"] == "opportunities"
        assert tmpl["metric"] == "sum"
        assert tmpl["metric_field"] == "amount"

    def test_lead_conversion_template(self):
        tmpl = next(t for t in REPORT_TEMPLATES if t["id"] == "lead_conversion")
        assert tmpl["entity_type"] == "leads"
        assert tmpl["group_by"] == "status"

    def test_activity_by_rep_template(self):
        tmpl = next(t for t in REPORT_TEMPLATES if t["id"] == "activity_by_rep")
        assert tmpl["entity_type"] == "activities"
        assert tmpl["group_by"] == "owner_id"

    def test_campaign_performance_template(self):
        tmpl = next(t for t in REPORT_TEMPLATES if t["id"] == "campaign_performance")
        assert tmpl["entity_type"] == "campaigns"

    def test_deals_won_lost_template(self):
        tmpl = next(t for t in REPORT_TEMPLATES if t["id"] == "deals_won_lost")
        assert tmpl["entity_type"] == "opportunities"

    def test_payment_summary_by_month_template(self):
        tmpl = next(t for t in REPORT_TEMPLATES if t["id"] == "payment_summary_by_month")
        assert tmpl["entity_type"] == "payments"
        assert tmpl["metric"] == "sum"
        assert tmpl["metric_field"] == "amount"
        assert tmpl["date_group"] == "month"

    def test_contracts_by_status_template(self):
        tmpl = next(t for t in REPORT_TEMPLATES if t["id"] == "contracts_by_status")
        assert tmpl["entity_type"] == "contracts"
        assert tmpl["metric"] == "count"
        assert tmpl["group_by"] == "status"

    def test_revenue_by_source_template(self):
        tmpl = next(t for t in REPORT_TEMPLATES if t["id"] == "revenue_by_source")
        assert tmpl["entity_type"] == "opportunities"
        assert tmpl["metric"] == "sum"
        assert tmpl["metric_field"] == "amount"

    def test_pipeline_value_by_owner_template(self):
        tmpl = next(t for t in REPORT_TEMPLATES if t["id"] == "pipeline_value_by_owner")
        assert tmpl["entity_type"] == "opportunities"
        assert tmpl["group_by"] == "owner_id"


# ============================================================
# Report execution integration tests
# ============================================================

@pytest.mark.asyncio
class TestReportExecution:
    """Integration tests for report execution."""

    async def test_count_leads_by_status(self, db_session, test_lead):
        """Test counting leads grouped by status."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="leads",
            metric="count",
            group_by="status",
        )
        result = await executor.execute(definition)
        assert result.total >= 1
        assert len(result.data) >= 1
        # The test_lead has status "new"
        new_dp = next((dp for dp in result.data if dp.label == "new"), None)
        assert new_dp is not None
        assert new_dp.value >= 1

    async def test_count_all_leads_no_grouping(self, db_session, test_lead):
        """Test counting all leads without grouping."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="leads",
            metric="count",
        )
        result = await executor.execute(definition)
        assert result.total >= 1
        assert len(result.data) == 1

    async def test_sum_opportunity_amount(self, db_session, test_opportunity):
        """Test summing opportunity amounts."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="opportunities",
            metric="sum",
            metric_field="amount",
        )
        result = await executor.execute(definition)
        assert result.total >= 50000.0

    async def test_avg_lead_score(self, db_session, test_lead):
        """Test averaging lead scores."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="leads",
            metric="avg",
            metric_field="score",
            group_by="status",
        )
        result = await executor.execute(definition)
        assert result.total > 0

    async def test_min_metric(self, db_session, test_lead):
        """Test min metric on lead scores."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="leads",
            metric="min",
            metric_field="score",
        )
        result = await executor.execute(definition)
        assert len(result.data) == 1

    async def test_max_metric(self, db_session, test_lead):
        """Test max metric on lead scores."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="leads",
            metric="max",
            metric_field="score",
        )
        result = await executor.execute(definition)
        assert len(result.data) == 1

    async def test_invalid_entity_raises_error(self, db_session):
        """Test that invalid entity type raises ValueError."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="nonexistent",
            metric="count",
        )
        with pytest.raises(ValueError, match="Unknown entity type"):
            await executor.execute(definition)

    async def test_metric_requires_field(self, db_session, test_lead):
        """Test that sum metric requires metric_field."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="leads",
            metric="sum",
        )
        with pytest.raises(ValueError, match="metric_field is required"):
            await executor.execute(definition)

    async def test_csv_export(self, db_session, test_lead):
        """Test CSV export of report results."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="leads",
            metric="count",
            group_by="status",
        )
        csv_content = await executor.export_csv(definition)
        assert isinstance(csv_content, str)
        assert "Total" in csv_content
        assert "new" in csv_content

    async def test_count_payments(self, db_session, test_payment):
        """Test counting payments entity type."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="payments",
            metric="count",
        )
        result = await executor.execute(definition)
        assert result.total >= 1

    async def test_sum_payment_amount(self, db_session, test_payment):
        """Test summing payment amounts."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="payments",
            metric="sum",
            metric_field="amount",
        )
        result = await executor.execute(definition)
        assert result.total >= 5000.0

    async def test_count_payments_by_status(self, db_session, test_payment):
        """Test counting payments grouped by status."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="payments",
            metric="count",
            group_by="status",
        )
        result = await executor.execute(definition)
        assert result.total >= 1
        assert len(result.data) >= 1

    async def test_count_contracts(self, db_session, test_contract):
        """Test counting contracts entity type."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="contracts",
            metric="count",
        )
        result = await executor.execute(definition)
        assert result.total >= 1

    async def test_sum_contract_value(self, db_session, test_contract):
        """Test summing contract values."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="contracts",
            metric="sum",
            metric_field="value",
        )
        result = await executor.execute(definition)
        assert result.total >= 25000.0

    async def test_count_contracts_by_status(self, db_session, test_contract):
        """Test counting contracts grouped by status."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="contracts",
            metric="count",
            group_by="status",
        )
        result = await executor.execute(definition)
        assert result.total >= 1
        assert len(result.data) >= 1
        draft_dp = next((dp for dp in result.data if dp.label == "draft"), None)
        assert draft_dp is not None
        assert draft_dp.value >= 1


# ============================================================
# Saved report with schedule and recipients tests
# ============================================================

@pytest.mark.asyncio
class TestSavedReportSchedule:
    """Integration tests for saved report schedule and recipients."""

    async def test_create_saved_report_with_schedule(self, db_session, test_user):
        """Test creating a saved report with schedule and recipients."""
        report = SavedReport(
            name="Scheduled Report",
            entity_type="leads",
            metric="count",
            chart_type="bar",
            created_by_id=test_user.id,
            schedule="weekly",
            recipients=json.dumps(["test@example.com", "admin@example.com"]),
        )
        db_session.add(report)
        await db_session.flush()
        await db_session.refresh(report)

        assert report.id > 0
        assert report.schedule == "weekly"
        parsed_recipients = json.loads(report.recipients)
        assert len(parsed_recipients) == 2
        assert "test@example.com" in parsed_recipients

    async def test_saved_report_schedule_nullable(self, db_session, test_user):
        """Test that schedule and recipients are nullable."""
        report = SavedReport(
            name="No Schedule Report",
            entity_type="leads",
            metric="count",
            chart_type="bar",
            created_by_id=test_user.id,
        )
        db_session.add(report)
        await db_session.flush()
        await db_session.refresh(report)

        assert report.schedule is None
        assert report.recipients is None


# ============================================================
# Saved report CRUD integration tests (via direct DB)
# ============================================================

@pytest.mark.asyncio
class TestSavedReportCRUD:
    """Integration tests for saved report CRUD via direct DB."""

    async def test_create_saved_report(self, db_session, test_user):
        """Test creating a saved report directly in DB."""
        report = SavedReport(
            name="Test Report",
            description="A test saved report",
            entity_type="leads",
            group_by="status",
            metric="count",
            chart_type="bar",
            is_public=False,
            created_by_id=test_user.id,
        )
        db_session.add(report)
        await db_session.flush()
        await db_session.refresh(report)

        assert report.id > 0
        assert report.name == "Test Report"
        assert report.entity_type == "leads"
        assert report.created_by_id == test_user.id

    async def test_list_saved_reports(self, db_session, test_user):
        """Test listing saved reports from DB."""
        for i in range(2):
            report = SavedReport(
                name=f"Report {i}",
                entity_type="leads",
                metric="count",
                chart_type="bar",
                created_by_id=test_user.id,
            )
            db_session.add(report)
        await db_session.flush()

        result = await db_session.execute(
            select(SavedReport).where(SavedReport.created_by_id == test_user.id)
        )
        reports = list(result.scalars().all())
        assert len(reports) >= 2

    async def test_delete_saved_report(self, db_session, test_user):
        """Test deleting a saved report."""
        report = SavedReport(
            name="Delete Me",
            entity_type="leads",
            metric="count",
            chart_type="bar",
            created_by_id=test_user.id,
        )
        db_session.add(report)
        await db_session.flush()
        await db_session.refresh(report)
        report_id = report.id

        await db_session.delete(report)
        await db_session.flush()

        result = await db_session.execute(
            select(SavedReport).where(SavedReport.id == report_id)
        )
        assert result.scalar_one_or_none() is None


# ============================================================
# Saved filter CRUD integration tests (via direct DB)
# ============================================================

@pytest.mark.asyncio
class TestSavedFilterCRUD:
    """Integration tests for saved filter CRUD via direct DB."""

    async def test_create_saved_filter(self, db_session, test_user):
        """Test creating a saved filter directly in the database."""
        saved_filter = SavedFilter(
            name="High Score Leads",
            entity_type="leads",
            filters=json.dumps({
                "operator": "and",
                "conditions": [{"field": "score", "op": "gte", "value": 50}],
            }),
            user_id=test_user.id,
            is_default=False,
        )
        db_session.add(saved_filter)
        await db_session.flush()
        await db_session.refresh(saved_filter)

        assert saved_filter.id > 0
        assert saved_filter.name == "High Score Leads"
        assert saved_filter.entity_type == "leads"

    async def test_list_saved_filters(self, db_session, test_user):
        """Test listing saved filters."""
        for i in range(2):
            sf = SavedFilter(
                name=f"Filter {i}",
                entity_type="leads",
                filters=json.dumps({"operator": "and", "conditions": []}),
                user_id=test_user.id,
            )
            db_session.add(sf)
        await db_session.flush()

        result = await db_session.execute(
            select(SavedFilter).where(SavedFilter.user_id == test_user.id)
        )
        filters = list(result.scalars().all())
        assert len(filters) >= 2

    async def test_delete_saved_filter(self, db_session, test_user):
        """Test deleting a saved filter."""
        sf = SavedFilter(
            name="Delete Me",
            entity_type="leads",
            filters=json.dumps({"operator": "and", "conditions": []}),
            user_id=test_user.id,
        )
        db_session.add(sf)
        await db_session.flush()
        await db_session.refresh(sf)
        sf_id = sf.id

        await db_session.delete(sf)
        await db_session.flush()

        result = await db_session.execute(
            select(SavedFilter).where(SavedFilter.id == sf_id)
        )
        assert result.scalar_one_or_none() is None


# ============================================================
# API endpoint integration tests
# ============================================================

@pytest.mark.asyncio
class TestReportsAPI:
    """Integration tests for report API endpoints."""

    async def test_execute_report_endpoint(self, client, auth_headers, test_lead):
        """Test POST /api/reports/execute."""
        response = await client.post(
            "/api/reports/execute",
            json={
                "entity_type": "leads",
                "metric": "count",
                "group_by": "status",
                "chart_type": "bar",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "total" in data
        assert data["total"] >= 1

    async def test_export_csv_endpoint(self, client, auth_headers, test_lead):
        """Test POST /api/reports/export-csv."""
        response = await client.post(
            "/api/reports/export-csv",
            json={
                "entity_type": "leads",
                "metric": "count",
                "group_by": "status",
                "chart_type": "bar",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")

    async def test_list_templates_endpoint(self, client, auth_headers):
        """Test GET /api/reports/templates."""
        response = await client.get(
            "/api/reports/templates",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 10

    async def test_saved_report_crud_endpoints(self, client, auth_headers):
        """Test full CRUD lifecycle for saved reports via API."""
        # Create
        response = await client.post(
            "/api/reports",
            json={
                "name": "API Test Report",
                "entity_type": "leads",
                "metric": "count",
                "group_by": "status",
                "chart_type": "bar",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        report = response.json()
        report_id = report["id"]
        assert report["name"] == "API Test Report"

        # List
        response = await client.get("/api/reports", headers=auth_headers)
        assert response.status_code == 200
        reports = response.json()
        assert any(r["id"] == report_id for r in reports)

        # Get by ID
        response = await client.get(f"/api/reports/{report_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["id"] == report_id

        # Update
        response = await client.patch(
            f"/api/reports/{report_id}",
            json={"name": "Updated Report Name"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Report Name"

        # Delete
        response = await client.delete(f"/api/reports/{report_id}", headers=auth_headers)
        assert response.status_code == 204

        # Verify deleted
        response = await client.get(f"/api/reports/{report_id}", headers=auth_headers)
        assert response.status_code == 404

    async def test_unauthenticated_report_access(self, client):
        """Test that report endpoints require authentication."""
        response = await client.get("/api/reports/templates")
        assert response.status_code in (401, 403)

    async def test_execute_payments_report_endpoint(self, client, auth_headers, test_payment):
        """Test executing a report on payments entity type."""
        response = await client.post(
            "/api/reports/execute",
            json={
                "entity_type": "payments",
                "metric": "sum",
                "metric_field": "amount",
                "chart_type": "bar",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 5000.0

    async def test_execute_contracts_report_endpoint(self, client, auth_headers, test_contract):
        """Test executing a report on contracts entity type."""
        response = await client.post(
            "/api/reports/execute",
            json={
                "entity_type": "contracts",
                "metric": "count",
                "group_by": "status",
                "chart_type": "pie",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        assert len(data["data"]) >= 1

    async def test_create_report_with_schedule(self, client, auth_headers):
        """Test creating a saved report with schedule and recipients."""
        response = await client.post(
            "/api/reports",
            json={
                "name": "Scheduled Payments Report",
                "entity_type": "payments",
                "metric": "sum",
                "metric_field": "amount",
                "chart_type": "bar",
                "schedule": "weekly",
                "recipients": ["user@example.com"],
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["schedule"] == "weekly"
        assert data["recipients"] == ["user@example.com"]

    async def test_update_report_schedule_endpoint(self, client, auth_headers):
        """Test PATCH /api/reports/{id}/schedule."""
        # Create a report first
        create_response = await client.post(
            "/api/reports",
            json={
                "name": "To Schedule",
                "entity_type": "leads",
                "metric": "count",
                "chart_type": "bar",
            },
            headers=auth_headers,
        )
        report_id = create_response.json()["id"]

        # Update schedule
        response = await client.patch(
            f"/api/reports/{report_id}/schedule",
            json={
                "schedule": "monthly",
                "recipients": ["report@example.com", "admin@example.com"],
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["schedule"] == "monthly"
        assert len(data["recipients"]) == 2

    async def test_templates_include_new_entity_types(self, client, auth_headers):
        """Test that templates include payment and contract templates."""
        response = await client.get(
            "/api/reports/templates",
            headers=auth_headers,
        )
        data = response.json()
        ids = [t["id"] for t in data]
        assert "payment_summary_by_month" in ids
        assert "contracts_by_status" in ids


@pytest.mark.asyncio
class TestFiltersAPI:
    """Integration tests for filter API endpoints."""

    async def test_saved_filter_crud_endpoints(self, client, auth_headers):
        """Test full CRUD lifecycle for saved filters via API."""
        # Create
        response = await client.post(
            "/api/filters",
            json={
                "name": "High Score",
                "entity_type": "leads",
                "filters": {
                    "operator": "and",
                    "conditions": [{"field": "score", "op": "gte", "value": 50}],
                },
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        sf = response.json()
        sf_id = sf["id"]
        assert sf["name"] == "High Score"

        # List
        response = await client.get("/api/filters?entity_type=leads", headers=auth_headers)
        assert response.status_code == 200
        filters = response.json()
        assert any(f["id"] == sf_id for f in filters)

        # Get by ID
        response = await client.get(f"/api/filters/{sf_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["name"] == "High Score"

        # Update
        response = await client.patch(
            f"/api/filters/{sf_id}",
            json={"name": "Updated Filter", "is_default": True},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Filter"
        assert response.json()["is_default"] is True

        # Delete
        response = await client.delete(f"/api/filters/{sf_id}", headers=auth_headers)
        assert response.status_code == 204

        # Verify deleted
        response = await client.get(f"/api/filters/{sf_id}", headers=auth_headers)
        assert response.status_code == 404

    async def test_unauthenticated_filter_access(self, client):
        """Test that filter endpoints require authentication."""
        response = await client.get("/api/filters")
        assert response.status_code in (401, 403)


# ============================================================
# Advanced filtering on entity list endpoints
# ============================================================

@pytest.mark.asyncio
class TestAdvancedFilterOnListEndpoints:
    """Test that the filters query param works on list endpoints."""

    async def test_leads_list_with_filters(self, client, auth_headers, test_lead):
        """Test GET /api/leads with filters param."""
        filters = json.dumps({
            "operator": "and",
            "conditions": [{"field": "status", "op": "eq", "value": "new"}],
        })
        response = await client.get(
            "/api/leads",
            headers=auth_headers,
            params={"filters": filters},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_contacts_list_with_filters(self, client, auth_headers, test_contact):
        """Test GET /api/contacts with filters param."""
        filters = json.dumps({
            "operator": "and",
            "conditions": [{"field": "first_name", "op": "contains", "value": "John"}],
        })
        response = await client.get(
            "/api/contacts",
            headers=auth_headers,
            params={"filters": filters},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_companies_list_with_filters(self, client, auth_headers, test_company):
        """Test GET /api/companies with filters param."""
        filters = json.dumps({
            "operator": "and",
            "conditions": [{"field": "industry", "op": "eq", "value": "Technology"}],
        })
        response = await client.get(
            "/api/companies",
            headers=auth_headers,
            params={"filters": filters},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_opportunities_list_with_filters(self, client, auth_headers, test_opportunity):
        """Test GET /api/opportunities with filters param."""
        filters = json.dumps({
            "operator": "and",
            "conditions": [{"field": "amount", "op": "gte", "value": 10000}],
        })
        response = await client.get(
            "/api/opportunities",
            headers=auth_headers,
            params={"filters": filters},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_activities_list_with_filters(self, client, auth_headers, test_activity):
        """Test GET /api/activities with filters param."""
        filters = json.dumps({
            "operator": "and",
            "conditions": [{"field": "activity_type", "op": "eq", "value": "call"}],
        })
        response = await client.get(
            "/api/activities",
            headers=auth_headers,
            params={"filters": filters},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_list_without_filters_still_works(self, client, auth_headers, test_lead):
        """Test that list endpoints work without filters param."""
        response = await client.get("/api/leads", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1

    async def test_leads_or_filter(self, client, auth_headers, test_lead):
        """Test OR filter on leads."""
        filters = json.dumps({
            "operator": "or",
            "conditions": [
                {"field": "status", "op": "eq", "value": "new"},
                {"field": "status", "op": "eq", "value": "contacted"},
            ],
        })
        response = await client.get(
            "/api/leads",
            headers=auth_headers,
            params={"filters": filters},
        )
        assert response.status_code == 200
        assert response.json()["total"] >= 1

    async def test_contacts_not_contains_filter(self, client, auth_headers, test_contact):
        """Test not_contains filter on contacts."""
        filters = json.dumps({
            "field": "first_name", "op": "not_contains", "value": "ZZZZZ",
        })
        response = await client.get(
            "/api/contacts",
            headers=auth_headers,
            params={"filters": filters},
        )
        assert response.status_code == 200
        assert response.json()["total"] >= 1


# ============================================================
# Aggregate endpoint tests
# ============================================================

@pytest.mark.asyncio
class TestAggregateEndpoint:
    """Integration tests for the POST /api/filters/aggregate endpoint."""

    async def test_aggregate_count_contacts(self, client, auth_headers, test_contact):
        """Test aggregate endpoint returns correct count for contacts."""
        response = await client.post(
            "/api/filters/aggregate",
            headers=auth_headers,
            json={
                "entity_type": "contacts",
                "filters": {
                    "operator": "and",
                    "conditions": [{"field": "status", "op": "eq", "value": "active"}],
                },
                "metrics": ["count"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1
        assert data["metrics"]["count"] >= 1
        assert isinstance(data["sample_entities"], list)

    async def test_aggregate_sum_metric_leads(self, client, auth_headers, test_lead):
        """Test aggregate endpoint with sum metric on lead budget amounts."""
        response = await client.post(
            "/api/filters/aggregate",
            headers=auth_headers,
            json={
                "entity_type": "leads",
                "filters": {
                    "operator": "and",
                    "conditions": [{"field": "status", "op": "eq", "value": "new"}],
                },
                "metrics": ["count", "sum:score"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1
        assert "sum:score" in data["metrics"]
        assert data["metrics"]["sum:score"] >= 50  # test_lead has score=50

    async def test_aggregate_returns_sample_entities(self, client, auth_headers, test_contact):
        """Test that aggregate endpoint returns sample entities."""
        response = await client.post(
            "/api/filters/aggregate",
            headers=auth_headers,
            json={
                "entity_type": "contacts",
                "filters": {
                    "operator": "and",
                    "conditions": [{"field": "first_name", "op": "contains", "value": "John"}],
                },
                "metrics": ["count"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["sample_entities"]) >= 1
        sample = data["sample_entities"][0]
        assert "id" in sample
        assert "first_name" in sample

    async def test_aggregate_empty_results(self, client, auth_headers):
        """Test aggregate with filters that match nothing."""
        response = await client.post(
            "/api/filters/aggregate",
            headers=auth_headers,
            json={
                "entity_type": "contacts",
                "filters": {
                    "operator": "and",
                    "conditions": [{"field": "first_name", "op": "eq", "value": "NONEXISTENTXYZ"}],
                },
                "metrics": ["count"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["sample_entities"] == []

    async def test_aggregate_leads_count(self, client, auth_headers, test_lead):
        """Test aggregate endpoint works with leads entity type."""
        response = await client.post(
            "/api/filters/aggregate",
            headers=auth_headers,
            json={
                "entity_type": "leads",
                "filters": {
                    "operator": "and",
                    "conditions": [{"field": "status", "op": "eq", "value": "new"}],
                },
                "metrics": ["count"],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1

    async def test_aggregate_invalid_entity_type(self, client, auth_headers):
        """Test aggregate with invalid entity type returns 400."""
        response = await client.post(
            "/api/filters/aggregate",
            headers=auth_headers,
            json={
                "entity_type": "nonexistent",
                "filters": {"operator": "and", "conditions": []},
                "metrics": ["count"],
            },
        )
        assert response.status_code == 400

    async def test_aggregate_unauthenticated(self, client):
        """Test aggregate endpoint requires authentication."""
        response = await client.post(
            "/api/filters/aggregate",
            json={
                "entity_type": "contacts",
                "filters": {"operator": "and", "conditions": []},
                "metrics": ["count"],
            },
        )
        assert response.status_code in (401, 403)


# ============================================================
# Saved filter is_public tests
# ============================================================

@pytest.mark.asyncio
class TestSavedFilterIsPublic:
    """Tests for the is_public field on saved filters."""

    async def test_create_filter_with_is_public(self, client, auth_headers):
        """Test creating a saved filter with is_public=True."""
        response = await client.post(
            "/api/filters",
            headers=auth_headers,
            json={
                "name": "Public Smart List",
                "entity_type": "contacts",
                "filters": {
                    "operator": "and",
                    "conditions": [{"field": "status", "op": "eq", "value": "active"}],
                },
                "is_public": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["is_public"] is True
        assert data["name"] == "Public Smart List"

    async def test_create_filter_default_is_public_false(self, client, auth_headers):
        """Test that is_public defaults to False."""
        response = await client.post(
            "/api/filters",
            headers=auth_headers,
            json={
                "name": "Private Filter",
                "entity_type": "contacts",
                "filters": {
                    "operator": "and",
                    "conditions": [{"field": "status", "op": "eq", "value": "active"}],
                },
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["is_public"] is False

    async def test_update_filter_is_public(self, client, auth_headers):
        """Test updating the is_public flag on a saved filter."""
        create_response = await client.post(
            "/api/filters",
            headers=auth_headers,
            json={
                "name": "Toggle Public",
                "entity_type": "contacts",
                "filters": {
                    "operator": "and",
                    "conditions": [{"field": "status", "op": "eq", "value": "active"}],
                },
                "is_public": False,
            },
        )
        filter_id = create_response.json()["id"]

        response = await client.patch(
            f"/api/filters/{filter_id}",
            headers=auth_headers,
            json={"is_public": True},
        )
        assert response.status_code == 200
        assert response.json()["is_public"] is True

    async def test_saved_filter_is_public_in_db(self, db_session, test_user):
        """Test is_public field persists correctly in the database."""
        sf = SavedFilter(
            name="DB Public Filter",
            entity_type="contacts",
            filters=json.dumps({"operator": "and", "conditions": []}),
            user_id=test_user.id,
            is_public=True,
        )
        db_session.add(sf)
        await db_session.flush()
        await db_session.refresh(sf)

        assert sf.is_public is True

        result = await db_session.execute(
            select(SavedFilter).where(SavedFilter.id == sf.id)
        )
        fetched = result.scalar_one()
        assert fetched.is_public is True
