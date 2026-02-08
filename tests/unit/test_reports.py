"""
Unit tests for custom reports endpoints.

Tests for report execution (count, sum), group_by, saved report CRUD,
and pre-built report templates.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.contacts.models import Contact
from src.leads.models import Lead
from src.companies.models import Company
from src.reports.models import SavedReport


class TestReportExecute:
    """Tests for report execution endpoint."""

    @pytest.mark.asyncio
    async def test_execute_count_report(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test executing a basic count report."""
        response = await client.post(
            "/api/reports/execute",
            headers=auth_headers,
            json={
                "entity_type": "contacts",
                "metric": "count",
                "chart_type": "bar",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entity_type"] == "contacts"
        assert data["metric"] == "count"
        assert data["chart_type"] == "bar"
        assert data["total"] >= 1

    @pytest.mark.asyncio
    async def test_execute_count_report_with_group_by(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test executing a count report grouped by a field."""
        response = await client.post(
            "/api/reports/execute",
            headers=auth_headers,
            json={
                "entity_type": "leads",
                "metric": "count",
                "group_by": "status",
                "chart_type": "bar",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["group_by"] == "status"
        assert len(data["data"]) >= 1
        # Each data point should have label and value
        for point in data["data"]:
            assert "label" in point
            assert "value" in point

    @pytest.mark.asyncio
    async def test_execute_sum_report(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test executing a sum metric report on a numeric field."""
        response = await client.post(
            "/api/reports/execute",
            headers=auth_headers,
            json={
                "entity_type": "leads",
                "metric": "sum",
                "metric_field": "score",
                "chart_type": "bar",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["metric"] == "sum"
        assert data["metric_field"] == "score"
        assert data["total"] is not None

    @pytest.mark.asyncio
    async def test_execute_report_invalid_entity_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test executing report with invalid entity type raises error."""
        response = await client.post(
            "/api/reports/execute",
            headers=auth_headers,
            json={
                "entity_type": "invalid_type",
                "metric": "count",
                "chart_type": "bar",
            },
        )

        # Should fail with a 500 or 422 since the entity type is unknown
        assert response.status_code in (400, 422, 500)

    @pytest.mark.asyncio
    async def test_execute_report_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test executing report without auth returns 401."""
        response = await client.post(
            "/api/reports/execute",
            json={
                "entity_type": "contacts",
                "metric": "count",
                "chart_type": "bar",
            },
        )

        assert response.status_code == 401


class TestReportTemplates:
    """Tests for pre-built report templates."""

    @pytest.mark.asyncio
    async def test_list_report_templates(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test listing pre-built report templates."""
        response = await client.get(
            "/api/reports/templates",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # Each template should have required fields
        for template in data:
            assert "id" in template
            assert "name" in template
            assert "entity_type" in template
            assert "metric" in template
            assert "chart_type" in template

    @pytest.mark.asyncio
    async def test_templates_include_pipeline_by_stage(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test that pipeline_by_stage template is present."""
        response = await client.get(
            "/api/reports/templates",
            headers=auth_headers,
        )

        data = response.json()
        ids = [t["id"] for t in data]
        assert "pipeline_by_stage" in ids


class TestSavedReportCRUD:
    """Tests for saved report CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_create_saved_report(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating a saved report."""
        response = await client.post(
            "/api/reports",
            headers=auth_headers,
            json={
                "name": "My Lead Report",
                "description": "Leads by status",
                "entity_type": "leads",
                "metric": "count",
                "group_by": "status",
                "chart_type": "bar",
                "is_public": False,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "My Lead Report"
        assert data["entity_type"] == "leads"
        assert data["metric"] == "count"
        assert data["group_by"] == "status"
        assert data["is_public"] is False
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_saved_report_with_filters(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test creating saved report with filter definition."""
        response = await client.post(
            "/api/reports",
            headers=auth_headers,
            json={
                "name": "Filtered Report",
                "entity_type": "contacts",
                "metric": "count",
                "chart_type": "pie",
                "filters": {"status": {"operator": "eq", "value": "active"}},
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["filters"] is not None
        assert data["filters"]["status"]["operator"] == "eq"

    @pytest.mark.asyncio
    async def test_list_saved_reports(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test listing saved reports (own + public)."""
        # Create a report first
        await client.post(
            "/api/reports",
            headers=auth_headers,
            json={
                "name": "List Test Report",
                "entity_type": "contacts",
                "metric": "count",
                "chart_type": "bar",
            },
        )

        response = await client.get(
            "/api/reports",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_list_saved_reports_filter_by_entity_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test listing reports filtered by entity_type."""
        await client.post(
            "/api/reports",
            headers=auth_headers,
            json={
                "name": "Contact Report",
                "entity_type": "contacts",
                "metric": "count",
                "chart_type": "bar",
            },
        )
        await client.post(
            "/api/reports",
            headers=auth_headers,
            json={
                "name": "Lead Report",
                "entity_type": "leads",
                "metric": "count",
                "chart_type": "bar",
            },
        )

        response = await client.get(
            "/api/reports",
            headers=auth_headers,
            params={"entity_type": "contacts"},
        )

        assert response.status_code == 200
        data = response.json()
        assert all(r["entity_type"] == "contacts" for r in data)

    @pytest.mark.asyncio
    async def test_get_saved_report(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test getting a saved report by ID."""
        create_response = await client.post(
            "/api/reports",
            headers=auth_headers,
            json={
                "name": "Get By ID Report",
                "entity_type": "contacts",
                "metric": "count",
                "chart_type": "bar",
            },
        )
        report_id = create_response.json()["id"]

        response = await client.get(
            f"/api/reports/{report_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == report_id
        assert data["name"] == "Get By ID Report"

    @pytest.mark.asyncio
    async def test_get_saved_report_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test getting non-existent report returns 404."""
        response = await client.get(
            "/api/reports/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_saved_report(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test updating a saved report."""
        create_response = await client.post(
            "/api/reports",
            headers=auth_headers,
            json={
                "name": "Old Report Name",
                "entity_type": "leads",
                "metric": "count",
                "chart_type": "bar",
            },
        )
        report_id = create_response.json()["id"]

        response = await client.patch(
            f"/api/reports/{report_id}",
            headers=auth_headers,
            json={
                "name": "New Report Name",
                "chart_type": "line",
                "is_public": True,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Report Name"
        assert data["chart_type"] == "line"
        assert data["is_public"] is True

    @pytest.mark.asyncio
    async def test_update_saved_report_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test updating non-existent report returns 404."""
        response = await client.patch(
            "/api/reports/99999",
            headers=auth_headers,
            json={"name": "Test"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_saved_report(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test deleting a saved report."""
        create_response = await client.post(
            "/api/reports",
            headers=auth_headers,
            json={
                "name": "To Delete Report",
                "entity_type": "contacts",
                "metric": "count",
                "chart_type": "bar",
            },
        )
        report_id = create_response.json()["id"]

        response = await client.delete(
            f"/api/reports/{report_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify deletion
        get_response = await client.get(
            f"/api/reports/{report_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_saved_report_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test deleting non-existent report returns 404."""
        response = await client.delete(
            "/api/reports/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestReportExportCSV:
    """Tests for CSV export endpoint."""

    @pytest.mark.asyncio
    async def test_export_csv(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test exporting a report as CSV."""
        response = await client.post(
            "/api/reports/export-csv",
            headers=auth_headers,
            json={
                "entity_type": "contacts",
                "metric": "count",
                "group_by": "status",
                "chart_type": "bar",
            },
        )

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment" in response.headers.get("content-disposition", "")
        # CSV content should not be empty
        assert len(response.text) > 0


class TestReportsUnauthorized:
    """Tests for unauthorized access to reports endpoints."""

    @pytest.mark.asyncio
    async def test_list_reports_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test listing reports without auth returns 401."""
        response = await client.get("/api/reports")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_report_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test creating report without auth returns 401."""
        response = await client.post(
            "/api/reports",
            json={
                "name": "Test",
                "entity_type": "contacts",
                "metric": "count",
                "chart_type": "bar",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_templates_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test listing templates without auth returns 401."""
        response = await client.get("/api/reports/templates")
        assert response.status_code == 401
