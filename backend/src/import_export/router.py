"""Import/Export API routes."""

from typing import List, Dict, Any
from pydantic import BaseModel
from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse
import io
from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, raise_bad_request
from src.import_export.csv_handler import CSVHandler
from src.import_export.bulk_operations import BulkOperationsHandler

MAX_CSV_FILE_SIZE = 10 * 1024 * 1024  # 10MB


async def _read_csv_upload(file: UploadFile) -> str:
    """Validate and read a CSV upload file, returning the decoded content string."""
    if not file.filename.endswith(".csv"):
        raise_bad_request("File must be a CSV")

    content = await file.read()

    if len(content) > MAX_CSV_FILE_SIZE:
        raise_bad_request("File size exceeds 10MB limit")

    return content.decode("utf-8")

router = APIRouter(prefix="/api/import-export", tags=["import-export"])


# Bulk operation schemas
class BulkUpdateRequest(BaseModel):
    entity_type: str
    entity_ids: List[int]
    updates: Dict[str, Any]


class BulkAssignRequest(BaseModel):
    entity_type: str
    entity_ids: List[int]
    owner_id: int


class BulkDeleteRequest(BaseModel):
    entity_type: str
    entity_ids: List[int]


# Export endpoints
@router.get("/export/contacts")
async def export_contacts(
    current_user: CurrentUser,
    db: DBSession,
):
    """Export contacts as CSV (scoped to current user)."""
    handler = CSVHandler(db)
    csv_content = await handler.export_contacts(user_id=current_user.id)

    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=contacts_export.csv"
        },
    )


@router.get("/export/companies")
async def export_companies(
    current_user: CurrentUser,
    db: DBSession,
):
    """Export companies as CSV (scoped to current user)."""
    handler = CSVHandler(db)
    csv_content = await handler.export_companies(user_id=current_user.id)

    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=companies_export.csv"
        },
    )


@router.get("/export/leads")
async def export_leads(
    current_user: CurrentUser,
    db: DBSession,
):
    """Export leads as CSV (scoped to current user)."""
    handler = CSVHandler(db)
    csv_content = await handler.export_leads(user_id=current_user.id)

    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=leads_export.csv"
        },
    )


# Import endpoints
@router.post("/import/contacts")
async def import_contacts(
    current_user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
    skip_errors: bool = True,
):
    """Import contacts from CSV file."""
    csv_content = await _read_csv_upload(file)

    handler = CSVHandler(db)
    result = await handler.import_contacts(
        csv_content=csv_content,
        user_id=current_user.id,
        skip_errors=skip_errors,
    )

    return result


@router.post("/import/companies")
async def import_companies(
    current_user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
    skip_errors: bool = True,
):
    """Import companies from CSV file."""
    csv_content = await _read_csv_upload(file)

    handler = CSVHandler(db)
    result = await handler.import_companies(
        csv_content=csv_content,
        user_id=current_user.id,
        skip_errors=skip_errors,
    )

    return result


@router.post("/import/leads")
async def import_leads(
    current_user: CurrentUser,
    db: DBSession,
    file: UploadFile = File(...),
    skip_errors: bool = True,
):
    """Import leads from CSV file."""
    csv_content = await _read_csv_upload(file)

    handler = CSVHandler(db)
    result = await handler.import_leads(
        csv_content=csv_content,
        user_id=current_user.id,
        skip_errors=skip_errors,
    )

    return result


# Template endpoints
@router.get("/template/{entity_type}")
async def get_import_template(
    entity_type: str,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get CSV template for importing an entity type."""
    if entity_type not in ["contacts", "companies", "leads"]:
        raise_bad_request("Invalid entity type. Must be: contacts, companies, or leads")

    handler = CSVHandler(db)
    template = handler.get_template(entity_type)

    return StreamingResponse(
        io.StringIO(template),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={entity_type}_template.csv"
        },
    )


# =========================================================================
# Bulk Operations endpoints
# =========================================================================

@router.post("/bulk/update")
async def bulk_update(
    request: BulkUpdateRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Mass update entities of a given type."""
    handler = BulkOperationsHandler(db)
    result = await handler.bulk_update(
        entity_type=request.entity_type,
        entity_ids=request.entity_ids,
        updates=request.updates,
    )
    if not result["success"]:
        raise_bad_request(result["error"])
    return result


@router.post("/bulk/assign")
async def bulk_assign(
    request: BulkAssignRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Mass assign owner to entities."""
    handler = BulkOperationsHandler(db)
    result = await handler.bulk_assign(
        entity_type=request.entity_type,
        entity_ids=request.entity_ids,
        owner_id=request.owner_id,
    )
    if not result["success"]:
        raise_bad_request(result["error"])
    return result


@router.post("/bulk/delete")
async def bulk_delete(
    request: BulkDeleteRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Mass delete entities of a given type."""
    handler = BulkOperationsHandler(db)
    result = await handler.bulk_delete(
        entity_type=request.entity_type,
        entity_ids=request.entity_ids,
    )
    if not result["success"]:
        raise_bad_request(result["error"])
    return result
