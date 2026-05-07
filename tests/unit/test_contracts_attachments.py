"""
Tests for contract file attachment upload, list, download, and delete endpoints.
Also validates per-entity MIME type restrictions (PDF + images only for contracts).
"""

import io
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.models import User
from src.contracts.models import Contract


class TestContractAttachmentUpload:
    """Upload tests for contracts entity."""

    @pytest.mark.asyncio
    async def test_upload_pdf_happy_path(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
    ):
        """PDF upload succeeds and row persists with correct entity_type/entity_id."""
        pdf_bytes = b"%PDF-1.4 fake pdf for contract"
        response = await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("agreement.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"entity_type": "contracts", "entity_id": str(test_contract.id), "category": "contract"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["original_filename"] == "agreement.pdf"
        assert data["entity_type"] == "contracts"
        assert data["entity_id"] == test_contract.id
        assert data["file_size"] == len(pdf_bytes)
        assert "id" in data

    @pytest.mark.asyncio
    async def test_upload_png_allowed(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
    ):
        """PNG is permitted by the contracts per-entity whitelist."""
        # Minimal 1x1 PNG header bytes
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
        response = await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("signature.png", io.BytesIO(png_bytes), "image/png")},
            data={"entity_type": "contracts", "entity_id": str(test_contract.id)},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["original_filename"] == "signature.png"

    @pytest.mark.asyncio
    async def test_upload_txt_rejected(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
    ):
        """txt file is blocked by the contracts per-entity restriction."""
        response = await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("notes.txt", io.BytesIO(b"plain text"), "text/plain")},
            data={"entity_type": "contracts", "entity_id": str(test_contract.id)},
        )

        assert response.status_code == 400
        assert "not allowed" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_upload_missing_contract_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Uploading against a non-existent contract id returns 404."""
        response = await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
            data={"entity_type": "contracts", "entity_id": "99999"},
        )

        assert response.status_code == 404


class TestContractAttachmentList:
    """List endpoint for contracts."""

    @pytest.mark.asyncio
    async def test_list_returns_all_uploaded(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
    ):
        """Two uploaded files both appear in the list response."""
        pdf_bytes = b"%PDF-1.4 first"
        png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20

        await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("first.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"entity_type": "contracts", "entity_id": str(test_contract.id)},
        )
        await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("second.png", io.BytesIO(png_bytes), "image/png")},
            data={"entity_type": "contracts", "entity_id": str(test_contract.id)},
        )

        response = await client.get(
            f"/api/attachments/contracts/{test_contract.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        filenames = {item["original_filename"] for item in data["items"]}
        assert "first.pdf" in filenames
        assert "second.png" in filenames


class TestContractAttachmentDownload:
    """Download endpoint for contracts."""

    @pytest.mark.asyncio
    async def test_download_returns_200_or_307(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
    ):
        """Download endpoint succeeds (FileResponse 200 in test; R2 redirect 307 in prod)."""
        pdf_bytes = b"%PDF-1.4 downloadable"
        upload = await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("dl.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
            data={"entity_type": "contracts", "entity_id": str(test_contract.id)},
        )
        attachment_id = upload.json()["id"]

        response = await client.get(
            f"/api/attachments/{attachment_id}/download",
            headers=auth_headers,
            follow_redirects=True,
        )

        assert response.status_code in (200, 307)


class TestContractAttachmentDelete:
    """Delete endpoint for contracts."""

    @pytest.mark.asyncio
    async def test_delete_removes_row(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
    ):
        """After DELETE the attachment no longer appears in the list."""
        upload = await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("to_delete.pdf", io.BytesIO(b"%PDF-1.4 bye"), "application/pdf")},
            data={"entity_type": "contracts", "entity_id": str(test_contract.id)},
        )
        attachment_id = upload.json()["id"]

        delete_response = await client.delete(
            f"/api/attachments/{attachment_id}",
            headers=auth_headers,
        )
        assert delete_response.status_code == 204

        list_response = await client.get(
            f"/api/attachments/contracts/{test_contract.id}",
            headers=auth_headers,
        )
        assert list_response.json()["total"] == 0


class TestContractAttachmentIsolation:
    """Cross-entity isolation: contract A's files must not appear under contract B."""

    @pytest.mark.asyncio
    async def test_cross_entity_isolation(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contract: Contract,
        test_user: User,
    ):
        """Attachment uploaded to contract A is invisible when listing contract B."""
        from datetime import date, timedelta

        contract_b = Contract(
            title="Contract B",
            status="draft",
            owner_id=test_user.id,
            created_by_id=test_user.id,
            start_date=date.today(),
            end_date=date.today() + timedelta(days=30),
        )
        db_session.add(contract_b)
        await db_session.commit()
        await db_session.refresh(contract_b)

        # Upload to contract A (test_contract)
        await client.post(
            "/api/attachments/upload",
            headers=auth_headers,
            files={"file": ("contract_a.pdf", io.BytesIO(b"%PDF-1.4 A"), "application/pdf")},
            data={"entity_type": "contracts", "entity_id": str(test_contract.id)},
        )

        # List for contract B — must be empty
        response = await client.get(
            f"/api/attachments/contracts/{contract_b.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["total"] == 0
