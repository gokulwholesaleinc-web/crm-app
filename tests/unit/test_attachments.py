"""
Tests for file attachment upload, download, list, and delete endpoints.
Also tests file size and type validation.
"""

import io
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.contacts.models import Contact
from src.companies.models import Company


class TestAttachmentUpload:
    """Tests for file attachment upload."""

    @pytest.mark.asyncio
    async def test_upload_text_file(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test uploading a valid text file."""
        file_content = b"Hello, this is a test file."
        response = await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
            data={"entity_type": "contacts", "entity_id": str(test_contact.id)},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["original_filename"] == "test.txt"
        assert data["mime_type"] == "text/plain"
        assert data["file_size"] == len(file_content)
        assert data["entity_type"] == "contacts"
        assert data["entity_id"] == test_contact.id
        assert "id" in data

    @pytest.mark.asyncio
    async def test_upload_pdf_file(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test uploading a PDF file."""
        file_content = b"%PDF-1.4 fake pdf content"
        response = await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("document.pdf", io.BytesIO(file_content), "application/pdf")},
            data={"entity_type": "contacts", "entity_id": str(test_contact.id)},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["original_filename"] == "document.pdf"

    @pytest.mark.asyncio
    async def test_upload_invalid_file_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test uploading a disallowed file type (e.g. .exe)."""
        file_content = b"malicious content"
        response = await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("virus.exe", io.BytesIO(file_content), "application/x-msdownload")},
            data={"entity_type": "contacts", "entity_id": str(test_contact.id)},
        )

        assert response.status_code == 400
        assert "not allowed" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_invalid_entity_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test uploading with invalid entity type."""
        file_content = b"test"
        response = await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
            data={"entity_type": "invalid", "entity_id": "1"},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_upload_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test uploading without authentication."""
        file_content = b"test"
        response = await client.post(
            "/api/attachments/upload",
            files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
            data={"entity_type": "contacts", "entity_id": "1"},
        )

        assert response.status_code == 401


class TestAttachmentList:
    """Tests for listing attachments."""

    @pytest.mark.asyncio
    async def test_list_attachments_empty(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test listing attachments when none exist."""
        response = await client.get(
            f"/api/attachments/contacts/{test_contact.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_attachments_after_upload(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test listing attachments after uploading files."""
        # Upload a file first
        file_content = b"file content here"
        await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("test.txt", io.BytesIO(file_content), "text/plain")},
            data={"entity_type": "contacts", "entity_id": str(test_contact.id)},
        )

        # List
        response = await client.get(
            f"/api/attachments/contacts/{test_contact.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["original_filename"] == "test.txt"


class TestAttachmentDelete:
    """Tests for deleting attachments."""

    @pytest.mark.asyncio
    async def test_delete_attachment(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test deleting an attachment."""
        # Upload first
        file_content = b"to be deleted"
        upload_response = await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("delete_me.txt", io.BytesIO(file_content), "text/plain")},
            data={"entity_type": "contacts", "entity_id": str(test_contact.id)},
        )
        attachment_id = upload_response.json()["id"]

        # Delete
        response = await client.delete(
            f"/api/attachments/{attachment_id}",
            headers=auth_headers,
        )

        assert response.status_code == 204

        # Verify it's gone
        list_response = await client.get(
            f"/api/attachments/contacts/{test_contact.id}",
            headers=auth_headers,
        )
        assert list_response.json()["total"] == 0

    @pytest.mark.asyncio
    async def test_delete_attachment_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test deleting non-existent attachment."""
        response = await client.delete(
            "/api/attachments/99999",
            headers=auth_headers,
        )

        assert response.status_code == 404


class TestAttachmentDownload:
    """Tests for downloading attachments."""

    @pytest.mark.asyncio
    async def test_download_attachment(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test downloading an uploaded attachment."""
        file_content = b"downloadable content"
        upload_response = await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("download_me.txt", io.BytesIO(file_content), "text/plain")},
            data={"entity_type": "contacts", "entity_id": str(test_contact.id)},
        )
        attachment_id = upload_response.json()["id"]

        # Download
        response = await client.get(
            f"/api/attachments/{attachment_id}/download",
            headers=auth_headers,
        )

        assert response.status_code == 200
        assert response.content == file_content

    @pytest.mark.asyncio
    async def test_download_attachment_not_found(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test downloading non-existent attachment."""
        response = await client.get(
            "/api/attachments/99999/download",
            headers=auth_headers,
        )

        assert response.status_code == 404
