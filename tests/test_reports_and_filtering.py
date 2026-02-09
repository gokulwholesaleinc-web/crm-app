"""
Tests for Custom Reports and Advanced Filtering features.

Tests cover:
- Report execution (count, sum, avg, min, max metrics)
- Report grouping (by field, by date)
- CSV export
- Pre-built report templates
- Saved report CRUD
- Saved filter CRUD
- Filter operators (eq, neq, contains, gt, lt, gte, lte, in, between, is_empty, is_not_empty)
- AND/OR filter groups
- Advanced filter query param on list endpoints
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
from src.reports.service import ReportExecutor, SavedReportService, REPORT_TEMPLATES
from src.reports.schemas import ReportDefinition, SavedReportCreate
from src.core.filtering import apply_filter_condition, parse_filter_group, apply_filters_to_query
from src.filters.schemas import SavedFilterCreate
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

    def test_invalid_field_returns_none(self):
        cond = apply_filter_condition(Lead, "nonexistent_field", "eq", "test")
        assert cond is None

    def test_invalid_operator_returns_none(self):
        cond = apply_filter_condition(Lead, "status", "invalid_op", "test")
        assert cond is None


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

    def test_apply_empty_filter(self):
        query = select(Lead)
        filters = {"operator": "and", "conditions": []}
        result_query = apply_filters_to_query(query, Lead, filters)
        # Should return unchanged query
        assert result_query is not None


# ============================================================
# Report template tests
# ============================================================

class TestReportTemplates:
    """Test pre-built report templates."""

    def test_templates_exist(self):
        assert len(REPORT_TEMPLATES) == 6

    def test_leads_by_status_template(self):
        tmpl = next(t for t in REPORT_TEMPLATES if t.id == "leads_by_status")
        assert tmpl.entity_type == "leads"
        assert tmpl.group_by == "status"
        assert tmpl.metric == "count"

    def test_leads_by_source_template(self):
        tmpl = next(t for t in REPORT_TEMPLATES if t.id == "leads_by_source")
        assert tmpl.entity_type == "leads"
        assert tmpl.group_by == "source_id"

    def test_opportunities_by_stage_template(self):
        tmpl = next(t for t in REPORT_TEMPLATES if t.id == "opportunities_by_stage")
        assert tmpl.entity_type == "opportunities"
        assert tmpl.group_by == "pipeline_stage_id"

    def test_revenue_by_stage_template(self):
        tmpl = next(t for t in REPORT_TEMPLATES if t.id == "revenue_by_stage")
        assert tmpl.entity_type == "opportunities"
        assert tmpl.metric == "sum"
        assert tmpl.metric_field == "amount"

    def test_activities_by_type_template(self):
        tmpl = next(t for t in REPORT_TEMPLATES if t.id == "activities_by_type")
        assert tmpl.entity_type == "activities"

    def test_companies_by_industry_template(self):
        tmpl = next(t for t in REPORT_TEMPLATES if t.id == "companies_by_industry")
        assert tmpl.entity_type == "companies"


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
        assert result.data[0].label == "Total"

    async def test_sum_opportunity_amount(self, db_session, test_opportunity):
        """Test summing opportunity amounts by stage."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="opportunities",
            metric="sum",
            metric_field="amount",
            group_by="pipeline_stage_id",
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

    async def test_min_max_metrics(self, db_session, test_lead):
        """Test min and max metrics."""
        executor = ReportExecutor(db_session)

        # Min
        definition = ReportDefinition(
            entity_type="leads",
            metric="min",
            metric_field="score",
        )
        result = await executor.execute(definition)
        assert result.total > 0

        # Max
        definition = ReportDefinition(
            entity_type="leads",
            metric="max",
            metric_field="score",
        )
        result = await executor.execute(definition)
        assert result.total > 0

    async def test_invalid_entity_returns_empty(self, db_session):
        """Test that invalid entity type returns empty results."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="nonexistent",
            metric="count",
        )
        result = await executor.execute(definition)
        assert result.total == 0
        assert len(result.data) == 0

    async def test_invalid_metric_field_returns_empty(self, db_session, test_lead):
        """Test that invalid metric field returns empty results."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="leads",
            metric="sum",
            metric_field="nonexistent_field",
        )
        result = await executor.execute(definition)
        assert result.total == 0

    async def test_csv_export(self, db_session, test_lead):
        """Test CSV export of report results."""
        executor = ReportExecutor(db_session)
        definition = ReportDefinition(
            entity_type="leads",
            metric="count",
            group_by="status",
        )
        csv_content = await executor.export_csv(definition)
        assert "Label,Value" in csv_content
        assert "Total" in csv_content
        assert "new" in csv_content


# ============================================================
# Saved report CRUD integration tests
# ============================================================

@pytest.mark.asyncio
class TestSavedReportCRUD:
    """Integration tests for saved report CRUD."""

    async def test_create_saved_report(self, db_session, test_user):
        """Test creating a saved report."""
        service = SavedReportService(db_session)
        data = SavedReportCreate(
            name="Test Report",
            description="A test saved report",
            entity_type="leads",
            group_by="status",
            metric="count",
            chart_type="bar",
            is_public=False,
        )
        report = await service.create(data, test_user.id)
        assert report.id > 0
        assert report.name == "Test Report"
        assert report.entity_type == "leads"
        assert report.created_by_id == test_user.id

    async def test_list_saved_reports(self, db_session, test_user):
        """Test listing saved reports."""
        service = SavedReportService(db_session)
        # Create two reports
        for i in range(2):
            data = SavedReportCreate(
                name=f"Report {i}",
                entity_type="leads",
                metric="count",
                chart_type="bar",
            )
            await service.create(data, test_user.id)

        reports = await service.list(test_user.id)
        assert len(reports) >= 2

    async def test_list_saved_reports_by_entity_type(self, db_session, test_user):
        """Test filtering saved reports by entity type."""
        service = SavedReportService(db_session)
        await service.create(SavedReportCreate(
            name="Lead Report", entity_type="leads", metric="count", chart_type="bar",
        ), test_user.id)
        await service.create(SavedReportCreate(
            name="Company Report", entity_type="companies", metric="count", chart_type="bar",
        ), test_user.id)

        lead_reports = await service.list(test_user.id, entity_type="leads")
        company_reports = await service.list(test_user.id, entity_type="companies")
        assert all(r.entity_type == "leads" for r in lead_reports)
        assert all(r.entity_type == "companies" for r in company_reports)

    async def test_get_saved_report(self, db_session, test_user):
        """Test getting a saved report by ID."""
        service = SavedReportService(db_session)
        data = SavedReportCreate(
            name="Get Test", entity_type="leads", metric="count", chart_type="pie",
        )
        created = await service.create(data, test_user.id)

        fetched = await service.get(created.id)
        assert fetched is not None
        assert fetched.name == "Get Test"
        assert fetched.chart_type == "pie"

    async def test_delete_saved_report(self, db_session, test_user):
        """Test deleting a saved report."""
        service = SavedReportService(db_session)
        data = SavedReportCreate(
            name="Delete Me", entity_type="leads", metric="count", chart_type="bar",
        )
        report = await service.create(data, test_user.id)
        report_id = report.id

        await service.delete(report)
        await db_session.flush()

        fetched = await service.get(report_id)
        assert fetched is None


# ============================================================
# Saved filter CRUD integration tests
# ============================================================

@pytest.mark.asyncio
class TestSavedFilterCRUD:
    """Integration tests for saved filter CRUD."""

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
        # Create two filters
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
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert "Label,Value" in response.text

    async def test_list_templates_endpoint(self, client, auth_headers):
        """Test GET /api/reports/templates."""
        response = await client.get(
            "/api/reports/templates",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 6

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

        # Delete
        response = await client.delete(f"/api/reports/{report_id}", headers=auth_headers)
        assert response.status_code == 204

    async def test_unauthenticated_report_access(self, client):
        """Test that report endpoints require authentication."""
        response = await client.get("/api/reports/templates")
        assert response.status_code in (401, 403)


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

        # Delete
        response = await client.delete(f"/api/filters/{sf_id}", headers=auth_headers)
        assert response.status_code == 204


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
            f"/api/leads?filters={filters}",
            headers=auth_headers,
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
            f"/api/contacts?filters={filters}",
            headers=auth_headers,
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
            f"/api/companies?filters={filters}",
            headers=auth_headers,
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
            f"/api/opportunities?filters={filters}",
            headers=auth_headers,
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
            f"/api/activities?filters={filters}",
            headers=auth_headers,
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
