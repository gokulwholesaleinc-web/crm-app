"""Report API routes."""

from typing import Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from src.core.router_utils import DBSession, CurrentUser
from src.reports.schemas import ReportDefinition, SavedReportCreate, SavedReportUpdate, SavedReportResponse
from src.reports.service import ReportExecutor, SavedReportService, REPORT_TEMPLATES

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("/execute")
async def execute_report(definition: ReportDefinition, current_user: CurrentUser, db: DBSession):
    """Execute a report definition and return results."""
    executor = ReportExecutor(db)
    return await executor.execute(definition)


@router.post("/export-csv")
async def export_csv(definition: ReportDefinition, current_user: CurrentUser, db: DBSession):
    """Export report results as CSV."""
    executor = ReportExecutor(db)
    csv_content = await executor.export_csv(definition)
    return PlainTextResponse(content=csv_content, media_type="text/csv")


@router.get("/templates")
async def list_templates(current_user: CurrentUser):
    """List pre-built report templates."""
    return [t.model_dump() for t in REPORT_TEMPLATES]


@router.get("")
async def list_saved_reports(
    current_user: CurrentUser,
    db: DBSession,
    entity_type: Optional[str] = None,
):
    """List saved reports for the current user."""
    service = SavedReportService(db)
    reports = await service.list(current_user.id, entity_type=entity_type)
    return [SavedReportResponse.model_validate(r) for r in reports]


@router.post("", status_code=201)
async def create_saved_report(data: SavedReportCreate, current_user: CurrentUser, db: DBSession):
    """Create a new saved report."""
    service = SavedReportService(db)
    report = await service.create(data, current_user.id)
    await db.commit()
    return SavedReportResponse.model_validate(report)


@router.get("/{report_id}")
async def get_saved_report(report_id: int, current_user: CurrentUser, db: DBSession):
    """Get a saved report by ID."""
    service = SavedReportService(db)
    report = await service.get(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return SavedReportResponse.model_validate(report)


@router.patch("/{report_id}")
async def update_saved_report(
    report_id: int, data: SavedReportUpdate, current_user: CurrentUser, db: DBSession,
):
    """Update a saved report."""
    service = SavedReportService(db)
    report = await service.get(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    updated = await service.update(report, data)
    await db.commit()
    return SavedReportResponse.model_validate(updated)


@router.delete("/{report_id}", status_code=204)
async def delete_saved_report(report_id: int, current_user: CurrentUser, db: DBSession):
    """Delete a saved report."""
    service = SavedReportService(db)
    report = await service.get(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    await service.delete(report)
    await db.commit()
