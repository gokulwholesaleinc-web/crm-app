"""Tests for Custom Reports and Advanced Filtering features.

Tests cover:
- Core filtering engine (apply_filter_condition error paths, parse_filter_group, apply_filters_to_query)
- Report execution (count, sum, avg, min, max metrics with group_by)
- Report CSV export
- Saved report API CRUD
- Saved filter API CRUD
- Advanced filters on entity list endpoints (leads, contacts, companies, opportunities, activities)
"""

import json
import pytest

from src.leads.models import Lead, LeadSource
from src.companies.models import Company
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.contacts.models import Contact
from src.reports.models import SavedReport
from src.filters.models import SavedFilter
from src.reports.service import ReportExecutor
from src.reports.schemas import ReportDefinition
from src.core.filtering import apply_filter_condition, parse_filter_group, apply_filters_to_query
from sqlalchemy import select


# ============================================================
# Filtering unit tests
# ============================================================

class TestFilterConditions:
    """Test individual filter condition operators.

    Per-operator "returns a non-None expression" tests (eq/neq/contains/
    gt/lt/in/between/etc.) were dropped — they verified that the function
    returned something without ever compiling or executing the resulting
    SQL. Full per-operator coverage with ``ClauseElement`` instance-of
    assertions (strictly stronger than the old ``is not None``) lives in
    ``tests/unit/test_core_filtering.py::TestApplyFilterCondition``;
    end-to-end SQL-executing coverage lives in
    ``TestApplyFiltersToQuery``, ``TestReportExecution``, and
    ``TestAdvancedFilterOnListEndpoints`` here.
    """

    def test_unknown_field_raises_error(self):
        """Should raise ValueError when filtering on an unknown field."""
        with pytest.raises(ValueError, match="Unknown field"):
            apply_filter_condition(Lead, "nonexistent_field", "eq", "test")

    def test_unknown_operator_raises_error(self):
        """Should raise ValueError when using an unknown filter operator."""
        with pytest.raises(ValueError, match="Unknown operator"):
            apply_filter_condition(Lead, "status", "invalid_op", "test")


class TestFilterGroups:
    """Test AND/OR filter group parsing."""

    def test_and_group(self):
        """Should parse an AND filter group with multiple conditions."""
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
        """Should parse an OR filter group with multiple conditions."""
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
        """Should parse nested AND/OR filter groups."""
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
        """Should return None when filter group has empty conditions list."""
        filter_def = {"operator": "and", "conditions": []}
        result = parse_filter_group(Lead, filter_def)
        assert result is None

    def test_default_operator_is_and(self):
        """Should default to AND operator when no operator is specified."""
        filter_def = {
            "conditions": [
                {"field": "status", "op": "eq", "value": "new"},
            ],
        }
        result = parse_filter_group(Lead, filter_def)
        assert result is not None

    def test_single_condition_shorthand(self):
        """Should parse a single condition shorthand without wrapping in a group."""
        filter_def = {"field": "status", "op": "eq", "value": "new"}
        result = parse_filter_group(Lead, filter_def)
        assert result is not None


class TestApplyFiltersToQuery:
    """Test applying filters to a SQLAlchemy query."""

    def test_apply_valid_filter(self):
        """Should apply a valid filter group to a SQLAlchemy query."""
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
        """Should return the original query unchanged when filter is None."""
        query = select(Lead)
        result_query = apply_filters_to_query(query, Lead, None)
        assert result_query is query

    def test_apply_empty_filter_returns_same_query(self):
        """Should return the original query unchanged when filter is empty dict."""
        query = select(Lead)
        result_query = apply_filters_to_query(query, Lead, {})
        assert result_query is query


# ============================================================
# Report execution integration tests
# ============================================================

# Per-template shape tests (TestReportTemplatesServiceLayer) were dropped —
# they walked each entry in the REPORT_TEMPLATES static constant and asserted
# its hard-coded fields, which is just restating the constant. The
# user-facing surface is covered by TestReportTemplatesAPI in
# tests/unit/test_reports.py.

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

    # Contracts entity type retired from the reports engine 2026-05-14
    # alongside the Contracts module unmount.


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
# API endpoint integration tests
# ============================================================

# TestSavedReportCRUDDirectDB and TestSavedFilterCRUD were dropped — both
# only exercised SQLAlchemy (add/flush/select/delete) against an in-memory
# session, without touching the routers, services, or auth surface. Saved-
# report CRUD is covered by TestReportsAPI below and TestSavedReportCRUDAPI
# in tests/unit/test_reports.py; saved-filter CRUD is covered by
# TestFiltersAPI and TestSavedFilterIsPublic below.

@pytest.mark.asyncio
class TestReportsAPI:
    """Integration tests for report API endpoints."""

    async def test_execute_report_endpoint(self, client, admin_auth_headers, test_lead):
        """Test POST /api/reports/execute."""
        response = await client.post(
            "/api/reports/execute",
            json={
                "entity_type": "leads",
                "metric": "count",
                "group_by": "status",
                "chart_type": "bar",
            },
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "total" in data
        assert data["total"] >= 1

    async def test_export_csv_endpoint(self, client, admin_auth_headers, test_lead):
        """Test POST /api/reports/export-csv."""
        response = await client.post(
            "/api/reports/export-csv",
            json={
                "entity_type": "leads",
                "metric": "count",
                "group_by": "status",
                "chart_type": "bar",
            },
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")

    async def test_list_templates_endpoint(self, client, admin_auth_headers):
        """Test GET /api/reports/templates."""
        response = await client.get(
            "/api/reports/templates",
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        # `contracts_by_status` retired 2026-05-14 with the Contracts module.
        assert len(data) == 9

    async def test_saved_report_crud_endpoints(self, client, admin_auth_headers):
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
            headers=admin_auth_headers,
        )
        assert response.status_code == 201
        report = response.json()
        report_id = report["id"]
        assert report["name"] == "API Test Report"

        # List
        response = await client.get("/api/reports", headers=admin_auth_headers)
        assert response.status_code == 200
        reports = response.json()
        assert any(r["id"] == report_id for r in reports)

        # Get by ID
        response = await client.get(f"/api/reports/{report_id}", headers=admin_auth_headers)
        assert response.status_code == 200
        assert response.json()["id"] == report_id

        # Update
        response = await client.patch(
            f"/api/reports/{report_id}",
            json={"name": "Updated Report Name"},
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Report Name"

        # Delete
        response = await client.delete(f"/api/reports/{report_id}", headers=admin_auth_headers)
        assert response.status_code == 204

        # Verify deleted
        response = await client.get(f"/api/reports/{report_id}", headers=admin_auth_headers)
        assert response.status_code == 404

    async def test_unauthenticated_report_access(self, client):
        """Test that report endpoints require authentication."""
        response = await client.get("/api/reports/templates")
        assert response.status_code in (401, 403)

    async def test_execute_payments_report_endpoint(self, client, admin_auth_headers, test_payment):
        """Test executing a report on payments entity type."""
        response = await client.post(
            "/api/reports/execute",
            json={
                "entity_type": "payments",
                "metric": "sum",
                "metric_field": "amount",
                "chart_type": "bar",
            },
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 5000.0

    # `entity_type=contracts` retired 2026-05-14 — engine rejects the value now.

    async def test_create_report_with_schedule(self, client, admin_auth_headers):
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
            headers=admin_auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["schedule"] == "weekly"
        assert data["recipients"] == ["user@example.com"]

    async def test_update_report_schedule_endpoint(self, client, admin_auth_headers):
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
            headers=admin_auth_headers,
        )
        report_id = create_response.json()["id"]

        # Update schedule
        response = await client.patch(
            f"/api/reports/{report_id}/schedule",
            json={
                "schedule": "monthly",
                "recipients": ["report@example.com", "admin@example.com"],
            },
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["schedule"] == "monthly"
        assert len(data["recipients"]) == 2

    async def test_templates_include_payment_template(self, client, admin_auth_headers):
        """Payment template must remain on the templates endpoint."""
        response = await client.get(
            "/api/reports/templates",
            headers=admin_auth_headers,
        )
        data = response.json()
        ids = [t["id"] for t in data]
        assert "payment_summary_by_month" in ids
        # `contracts_by_status` retired 2026-05-14 with the Contracts module.


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
