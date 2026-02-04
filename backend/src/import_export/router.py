"""Import/Export API routes."""

from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import io
from src.database import get_db
from src.auth.models import User
from src.auth.dependencies import get_current_active_user
from src.import_export.csv_handler import CSVHandler

router = APIRouter(prefix="/api/import-export", tags=["import-export"])


# Export endpoints
@router.get("/export/contacts")
async def export_contacts(
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
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
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
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
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
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
    file: UploadFile = File(...),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    skip_errors: bool = True,
):
    """Import contacts from CSV file."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV",
        )

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
    file: UploadFile = File(...),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    skip_errors: bool = True,
):
    """Import companies from CSV file."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV",
        )

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
    file: UploadFile = File(...),
    current_user: Annotated[User, Depends(get_current_active_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
    skip_errors: bool = True,
):
    """Import leads from CSV file."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a CSV",
        )

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
    current_user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get CSV template for importing an entity type."""
    if entity_type not in ["contacts", "companies", "leads"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid entity type. Must be: contacts, companies, or leads",
        )

    handler = CSVHandler(db)
    template = handler.get_template(entity_type)

    return StreamingResponse(
        io.StringIO(template),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={entity_type}_template.csv"
        },
    )
