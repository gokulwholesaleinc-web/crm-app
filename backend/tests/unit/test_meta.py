"""Unit tests for Meta API endpoints.

Tests cover:
- GET /api/meta/companies/{company_id} - get meta data
- POST /api/meta/companies/{company_id}/sync - sync meta page data
- GET /api/meta/companies/{company_id}/export-csv - export CSV
- Authentication requirements
- Tests do NOT mock anything.
"""

import pytest


class TestGetCompanyMeta:
    """Test GET /api/meta/companies/{company_id}."""

    @pytest.mark.asyncio
    async def test_get_meta_returns_404_when_none_exists(self, client, auth_headers, test_company):
        """Should return 404 when no Meta data exists for a company."""
        response = await client.get(
            f"/api/meta/companies/{test_company.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "No Meta data found for this company"

    @pytest.mark.asyncio
    async def test_get_meta_returns_data_after_sync(self, client, auth_headers, test_company):
        """Should return Meta data after it has been synced."""
        await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={"page_id": "unit_test_page"},
            headers=auth_headers,
        )

        response = await client.get(
            f"/api/meta/companies/{test_company.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["company_id"] == test_company.id
        assert data["page_id"] == "unit_test_page"
        assert data["id"] is not None
        assert data["created_at"] is not None
        assert data["updated_at"] is not None

    @pytest.mark.asyncio
    async def test_get_meta_returns_404_for_nonexistent_company(self, client, auth_headers):
        """Should return 404 for a company that has no meta data."""
        response = await client.get(
            "/api/meta/companies/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_meta_requires_auth(self, client, test_company):
        """Should return 401 without authentication."""
        response = await client.get(f"/api/meta/companies/{test_company.id}")
        assert response.status_code == 401


class TestSyncCompanyMeta:
    """Test POST /api/meta/companies/{company_id}/sync."""

    @pytest.mark.asyncio
    async def test_sync_creates_new_meta_record(self, client, auth_headers, test_company):
        """Should create a new Meta data record for a company."""
        response = await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={"page_id": "new_page_123"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["company_id"] == test_company.id
        assert data["page_id"] == "new_page_123"
        assert data["last_synced_at"] is not None
        assert data["id"] is not None

    @pytest.mark.asyncio
    async def test_sync_updates_existing_record(self, client, auth_headers, test_company):
        """Should update an existing Meta data record when syncing again."""
        resp1 = await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={"page_id": "original_page"},
            headers=auth_headers,
        )
        assert resp1.status_code == 200
        first_id = resp1.json()["id"]

        resp2 = await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={"page_id": "updated_page"},
            headers=auth_headers,
        )
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["id"] == first_id
        assert data["page_id"] == "updated_page"

    @pytest.mark.asyncio
    async def test_sync_requires_page_id(self, client, auth_headers, test_company):
        """Should return 422 when page_id is missing from request body."""
        response = await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_sync_requires_auth(self, client, test_company):
        """Should return 401 without authentication."""
        response = await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={"page_id": "test"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_sync_sets_last_synced_at(self, client, auth_headers, test_company):
        """Should set last_synced_at timestamp on sync."""
        response = await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={"page_id": "timestamp_test"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["last_synced_at"] is not None


class TestExportMetaCsv:
    """Test GET /api/meta/companies/{company_id}/export-csv."""

    @pytest.mark.asyncio
    async def test_export_csv_returns_404_when_no_data(self, client, auth_headers, test_company):
        """Should return 404 when no Meta data exists to export."""
        response = await client.get(
            f"/api/meta/companies/{test_company.id}/export-csv",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_export_csv_returns_csv_after_sync(self, client, auth_headers, test_company):
        """Should return CSV content with correct data after syncing."""
        await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={"page_id": "csv_export_page"},
            headers=auth_headers,
        )

        response = await client.get(
            f"/api/meta/companies/{test_company.id}/export-csv",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        content = response.text
        assert "Field,Value" in content
        assert "csv_export_page" in content
        assert "Page ID" in content
        assert "Page Name" in content
        assert "Followers" in content
        assert "Likes" in content

    @pytest.mark.asyncio
    async def test_export_csv_content_disposition_header(self, client, auth_headers, test_company):
        """Should include correct Content-Disposition header for file download."""
        await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={"page_id": "disposition_test"},
            headers=auth_headers,
        )

        response = await client.get(
            f"/api/meta/companies/{test_company.id}/export-csv",
            headers=auth_headers,
        )
        assert response.status_code == 200
        disposition = response.headers.get("content-disposition", "")
        assert f"meta-company-{test_company.id}.csv" in disposition

    @pytest.mark.asyncio
    async def test_export_csv_requires_auth(self, client, test_company):
        """Should return 401 without authentication."""
        response = await client.get(
            f"/api/meta/companies/{test_company.id}/export-csv",
        )
        assert response.status_code == 401
