"""Custom Reports API routes."""

import json
import logging
import os
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, or_
from openai import AsyncOpenAI
import io

from src.config import settings
from src.core.router_utils import DBSession, CurrentUser
from src.core.constants import HTTPStatus
from src.core.data_scope import DataScope, get_data_scope
from src.reports.models import SavedReport
from src.reports.schemas import (
    ReportDefinition,
    ReportResult,
    ReportTemplate,
    SavedReportCreate,
    SavedReportUpdate,
    SavedReportResponse,
    AIReportGenerateRequest,
    AIReportGenerateResponse,
    ScheduleUpdateRequest,
)
from src.reports.service import ReportExecutor, REPORT_TEMPLATES, ENTITY_MODEL_MAP, NUMERIC_FIELDS

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
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=str(exc))

    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=report.csv"},
    )


@router.get("/templates", response_model=List[ReportTemplate])
async def list_report_templates(
    current_user: CurrentUser,
):
    """List pre-built report templates."""
    return [ReportTemplate(**t) for t in REPORT_TEMPLATES]


@router.post("/ai-generate", response_model=AIReportGenerateResponse)
async def ai_generate_report(
    request: AIReportGenerateRequest,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Use AI to parse a natural language prompt into a report definition, execute it, and return results."""
    api_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="AI features are not configured. Set OPENAI_API_KEY.")

    client = AsyncOpenAI(api_key=api_key)

    entity_types = list(ENTITY_MODEL_MAP.keys())
    numeric_fields_info = json.dumps(NUMERIC_FIELDS, indent=2)

    system_prompt = f"""You are a CRM report generator. Parse the user's request into a JSON report definition.

Available entity types: {entity_types}
Available metrics: count, sum, avg, min, max
Available date groupings: day, week, month, quarter, year
Available chart types: bar, line, pie, table

Numeric fields per entity (required for sum/avg/min/max):
{numeric_fields_info}

Respond ONLY with a JSON object matching this schema:
{{
    "entity_type": "<string>",
    "metric": "<string>",
    "metric_field": "<string or null>",
    "group_by": "<string or null>",
    "date_group": "<string or null>",
    "filters": null,
    "chart_type": "<string>"
}}

Choose the most appropriate entity_type, metric, grouping, and chart_type based on the user's request.
If the user mentions "revenue" or "money", use opportunities with sum of amount.
If the user mentions "payments", use payments with sum of amount.
If the user mentions "contracts", use contracts entity.
Default to count metric if no aggregation is implied.
Default to bar chart if no chart preference is stated."""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.prompt},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        parsed = json.loads(content)

        definition = ReportDefinition(
            entity_type=parsed.get("entity_type", "opportunities"),
            metric=parsed.get("metric", "count"),
            metric_field=parsed.get("metric_field"),
            group_by=parsed.get("group_by"),
            date_group=parsed.get("date_group"),
            filters=parsed.get("filters"),
            chart_type=parsed.get("chart_type", "bar"),
        )
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="AI returned invalid JSON. Please try rephrasing your request.")
    except Exception as exc:
        logger.error(f"AI report generation error: {exc}")
        raise HTTPException(status_code=400, detail=f"Failed to generate report: {str(exc)}")

    # Gate on entity scope before executing — avoids unnecessary DB work for a guaranteed 403.
    entity_model = ENTITY_MODEL_MAP.get(definition.entity_type)
    if entity_model and not hasattr(entity_model, "owner_id") and not data_scope.can_see_all():
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Reports on this entity require admin role")

    executor = ReportExecutor(db, user_id=current_user.id, is_admin=data_scope.can_see_all())
    try:
        result = await executor.execute(definition)
    except PermissionError as exc:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return AIReportGenerateResponse(definition=definition, result=result)


# Saved report CRUD
@router.get("", response_model=List[SavedReportResponse])
async def list_saved_reports(
    current_user: CurrentUser,
    db: DBSession,
    entity_type: Optional[str] = None,
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
