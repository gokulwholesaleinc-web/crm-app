"""Tests for Meta API integration.

Tests cover:
- Get company meta (404 when none exists)
- Sync company meta creates/updates record
- Export CSV
- Tests do NOT mock anything.
"""

import pytest


class TestGetCompanyMeta:
    """Test GET /api/meta/companies/{company_id}."""

    @pytest.mark.asyncio
    async def test_get_meta_returns_404_when_none(self, client, auth_headers, test_company):
        """Should return 404 when no Meta data exists for a company."""
        response = await client.get(
            f"/api/meta/companies/{test_company.id}",
            headers=auth_headers,
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "No Meta data found for this company"

    @pytest.mark.asyncio
    async def test_get_meta_returns_data_after_sync(self, client, auth_headers, test_company):
        """Should return Meta data after syncing."""
        # First sync
        await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={"page_id": "123456789"},
            headers=auth_headers,
        )

        # Then get
        response = await client.get(
            f"/api/meta/companies/{test_company.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["company_id"] == test_company.id
        assert data["page_id"] == "123456789"


class TestSyncCompanyMeta:
    """Test POST /api/meta/companies/{company_id}/sync."""

    @pytest.mark.asyncio
    async def test_sync_creates_meta_record(self, client, auth_headers, test_company):
        """Should create a new Meta data record for a company."""
        response = await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={"page_id": "test_page_001"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["company_id"] == test_company.id
        assert data["page_id"] == "test_page_001"
        assert data["last_synced_at"] is not None
        assert data["id"] is not None

    @pytest.mark.asyncio
    async def test_sync_updates_existing_record(self, client, auth_headers, test_company):
        """Should update an existing Meta data record on re-sync."""
        # First sync
        resp1 = await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={"page_id": "page_v1"},
            headers=auth_headers,
        )
        assert resp1.status_code == 200
        first_id = resp1.json()["id"]

        # Second sync with different page_id
        resp2 = await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={"page_id": "page_v2"},
            headers=auth_headers,
        )
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["id"] == first_id  # Same record updated
        assert data["page_id"] == "page_v2"

    @pytest.mark.asyncio
    async def test_sync_requires_page_id(self, client, auth_headers, test_company):
        """Should return 422 if page_id is missing."""
        response = await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 422


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
    async def test_export_csv_returns_csv_content(self, client, auth_headers, test_company):
        """Should return CSV content after syncing."""
        # First sync some data
        await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={"page_id": "csv_test_page"},
            headers=auth_headers,
        )

        # Then export
        response = await client.get(
            f"/api/meta/companies/{test_company.id}/export-csv",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        content = response.text
        assert "Field,Value" in content
        assert "csv_test_page" in content
        assert "Page ID" in content

    @pytest.mark.asyncio
    async def test_export_csv_content_disposition(self, client, auth_headers, test_company):
        """Should have correct Content-Disposition header."""
        await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={"page_id": "header_test"},
            headers=auth_headers,
        )

        response = await client.get(
            f"/api/meta/companies/{test_company.id}/export-csv",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert f"meta-company-{test_company.id}.csv" in response.headers.get("content-disposition", "")


class TestMetaAuth:
    """Test authentication on Meta endpoints."""

    @pytest.mark.asyncio
    async def test_get_meta_requires_auth(self, client, test_company):
        """Should return 401 without auth headers."""
        response = await client.get(f"/api/meta/companies/{test_company.id}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_sync_requires_auth(self, client, test_company):
        """Should return 401 without auth headers."""
        response = await client.post(
            f"/api/meta/companies/{test_company.id}/sync",
            json={"page_id": "test"},
        )
        assert response.status_code == 401
