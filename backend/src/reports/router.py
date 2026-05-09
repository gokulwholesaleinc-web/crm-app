"""Custom Reports API routes."""

import io
import json
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select

from src.core.constants import HTTPStatus
from src.core.data_scope import DataScope, get_data_scope
from src.core.router_utils import CurrentUser, DBSession
from src.reports.models import SavedReport
from src.reports.schemas import (
    ReportDefinition,
    ReportResult,
    ReportTemplate,
    SavedReportCreate,
    SavedReportResponse,
    SavedReportUpdate,
    ScheduleUpdateRequest,
)
from src.reports.service import REPORT_TEMPLATES, ReportExecutor

logger = logging.getLogger(__name__)


def _report_to_response_dict(report: SavedReport) -> dict:
    """Convert a SavedReport model to a dict suitable for SavedReportResponse.

    Handles JSON string fields (filters, recipients) that need to be
    deserialized before Pydantic validation.
    """
    resp = {
        "id": report.id,
        "name": report.name,
        "description": report.description,
        "entity_type": report.entity_type,
        "filters": json.loads(report.filters) if report.filters and isinstance(report.filters, str) else report.filters,
        "group_by": report.group_by,
        "date_group": report.date_group,
        "metric": report.metric,
        "metric_field": report.metric_field,
        "chart_type": report.chart_type,
        "created_by_id": report.created_by_id,
        "is_public": report.is_public,
        "schedule": report.schedule,
        "recipients": json.loads(report.recipients) if report.recipients and isinstance(report.recipients, str) else report.recipients,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
    }
    return resp

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("/execute", response_model=ReportResult)
async def execute_report(
    definition: ReportDefinition,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Execute a report definition and return results (scoped to current user)."""
    executor = ReportExecutor(db, user_id=current_user.id, is_admin=data_scope.can_see_all())
    try:
        return await executor.execute(definition)
    except PermissionError as exc:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/export-csv")
async def export_report_csv(
    definition: ReportDefinition,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Execute a report and return results as CSV download."""
    executor = ReportExecutor(db, user_id=current_user.id, is_admin=data_scope.can_see_all())
    try:
        csv_content = await executor.export_csv(definition)
    except PermissionError as exc:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=str(exc)) from exc

    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=report.csv"},
    )


@router.get("/templates", response_model=list[ReportTemplate])
async def list_report_templates(
    current_user: CurrentUser,
):
    """List pre-built report templates."""
    return [ReportTemplate(**t) for t in REPORT_TEMPLATES]


# Saved report CRUD
@router.get("", response_model=list[SavedReportResponse])
async def list_saved_reports(
    current_user: CurrentUser,
    db: DBSession,
    entity_type: str | None = None,
):
    """List saved reports (own + public)."""
    query = select(SavedReport).where(
        or_(
            SavedReport.created_by_id == current_user.id,
            SavedReport.is_public == True,
        )
    )
    if entity_type:
        query = query.where(SavedReport.entity_type == entity_type)
    query = query.order_by(SavedReport.name)

    result = await db.execute(query)
    reports = result.scalars().all()

    responses = []
    for r in reports:
        data = SavedReportResponse.model_validate(r).model_dump()
        data["filters"] = json.loads(r.filters) if r.filters and isinstance(r.filters, str) else r.filters
        data["recipients"] = json.loads(r.recipients) if r.recipients and isinstance(r.recipients, str) else r.recipients
        responses.append(SavedReportResponse(**data))
    return responses


@router.post("", response_model=SavedReportResponse, status_code=HTTPStatus.CREATED)
async def create_saved_report(
    data: SavedReportCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new saved report."""
    report = SavedReport(
        name=data.name,
        description=data.description,
        entity_type=data.entity_type,
        filters=json.dumps(data.filters) if data.filters else None,
        group_by=data.group_by,
        date_group=data.date_group,
        metric=data.metric,
        metric_field=data.metric_field,
        chart_type=data.chart_type,
        created_by_id=current_user.id,
        is_public=data.is_public,
        schedule=data.schedule,
        recipients=json.dumps(data.recipients) if data.recipients else None,
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)

    resp = {
        "id": report.id,
        "name": report.name,
        "description": report.description,
        "entity_type": report.entity_type,
        "filters": data.filters,
        "group_by": report.group_by,
        "date_group": report.date_group,
        "metric": report.metric,
        "metric_field": report.metric_field,
        "chart_type": report.chart_type,
        "created_by_id": report.created_by_id,
        "is_public": report.is_public,
        "schedule": report.schedule,
        "recipients": data.recipients,
        "created_at": report.created_at,
        "updated_at": report.updated_at,
    }
    return SavedReportResponse(**resp)


@router.get("/{report_id}", response_model=SavedReportResponse)
async def get_saved_report(
    report_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get a saved report by ID."""
    result = await db.execute(
        select(SavedReport).where(
            SavedReport.id == report_id,
            or_(
                SavedReport.created_by_id == current_user.id,
                SavedReport.is_public == True,
            ),
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        from src.core.router_utils import raise_not_found
        raise_not_found("Report", report_id)

    resp = _report_to_response_dict(report)
    return SavedReportResponse(**resp)


@router.patch("/{report_id}", response_model=SavedReportResponse)
async def update_saved_report(
    report_id: int,
    data: SavedReportUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a saved report."""
    result = await db.execute(
        select(SavedReport).where(
            SavedReport.id == report_id,
            SavedReport.created_by_id == current_user.id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        from src.core.router_utils import raise_not_found
        raise_not_found("Report", report_id)

    if data.name is not None:
        report.name = data.name
    if data.description is not None:
        report.description = data.description
    if data.filters is not None:
        report.filters = json.dumps(data.filters)
    if data.group_by is not None:
        report.group_by = data.group_by
    if data.date_group is not None:
        report.date_group = data.date_group
    if data.metric is not None:
        report.metric = data.metric
    if data.metric_field is not None:
        report.metric_field = data.metric_field
    if data.chart_type is not None:
        report.chart_type = data.chart_type
    if data.is_public is not None:
        report.is_public = data.is_public
    if data.schedule is not None:
        report.schedule = data.schedule
    if data.recipients is not None:
        report.recipients = json.dumps(data.recipients)

    await db.flush()
    await db.refresh(report)

    resp = _report_to_response_dict(report)
    return SavedReportResponse(**resp)


@router.patch("/{report_id}/schedule", response_model=SavedReportResponse)
async def update_report_schedule(
    report_id: int,
    data: ScheduleUpdateRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Set schedule and recipients on a saved report."""
    result = await db.execute(
        select(SavedReport).where(
            SavedReport.id == report_id,
            SavedReport.created_by_id == current_user.id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        from src.core.router_utils import raise_not_found
        raise_not_found("Report", report_id)

    report.schedule = data.schedule
    report.recipients = json.dumps(data.recipients) if data.recipients else None

    await db.flush()
    await db.refresh(report)

    resp = _report_to_response_dict(report)
    return SavedReportResponse(**resp)


@router.delete("/{report_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_saved_report(
    report_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete a saved report."""
    result = await db.execute(
        select(SavedReport).where(
            SavedReport.id == report_id,
            SavedReport.created_by_id == current_user.id,
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        from src.core.router_utils import raise_not_found
        raise_not_found("Report", report_id)

    await db.delete(report)
    await db.flush()
