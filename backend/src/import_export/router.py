"""Import/Export API routes."""

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import StreamingResponse
import io
from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, raise_bad_request
from src.import_export.csv_handler import CSVHandler

router = APIRouter(prefix="/api/import-export", tags=["import-export"])


# Export endpoints
@router.get("/export/contacts")
async def export_contacts(
    current_user: CurrentUser,
    db: DBSession,
):
    """Export all contacts as CSV."""
    handler = CSVHandler(db)
    csv_content = await handler.export_contacts()

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
    """Export all companies as CSV."""
    handler = CSVHandler(db)
    csv_content = await handler.export_companies()

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
    """Export all leads as CSV."""
    handler = CSVHandler(db)
    csv_content = await handler.export_leads()

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
    if not file.filename.endswith(".csv"):
        raise_bad_request("File must be a CSV")

    content = await file.read()
    csv_content = content.decode("utf-8")

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
    if not file.filename.endswith(".csv"):
        raise_bad_request("File must be a CSV")

    content = await file.read()
    csv_content = content.decode("utf-8")

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
    if not file.filename.endswith(".csv"):
        raise_bad_request("File must be a CSV")

    content = await file.read()
    csv_content = content.decode("utf-8")

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
