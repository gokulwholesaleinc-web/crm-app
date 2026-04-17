"""Dashboard widgets sub-router."""

import json

from fastapi import APIRouter, HTTPException
from sqlalchemy import or_, select

from src.core.constants import HTTPStatus
from src.core.router_utils import CurrentUser, DBSession
from src.dashboard.models import DashboardReportWidget
from src.dashboard.schemas import (
    ReportWidgetCreate,
    ReportWidgetResponse,
    ReportWidgetUpdate,
)
from src.reports.models import SavedReport
from src.reports.schemas import ReportDefinition
from src.reports.service import ReportExecutor

widgets_router = APIRouter(tags=["dashboard"])


@widgets_router.get("", response_model=list[ReportWidgetResponse])
async def list_report_widgets(
    current_user: CurrentUser,
    db: DBSession,
):
    """List the current user's dashboard report widgets."""
    result = await db.execute(
        select(DashboardReportWidget, SavedReport)
        .join(SavedReport, DashboardReportWidget.report_id == SavedReport.id)
        .where(DashboardReportWidget.user_id == current_user.id)
        .order_by(DashboardReportWidget.position)
    )
    rows = result.all()
    return [
        ReportWidgetResponse(
            id=widget.id,
            user_id=widget.user_id,
            report_id=widget.report_id,
            report_name=report.name,
            report_chart_type=report.chart_type,
            position=widget.position,
            width=widget.width,
            is_visible=widget.is_visible,
            created_at=widget.created_at,
        )
        for widget, report in rows
    ]


@widgets_router.post("", response_model=ReportWidgetResponse, status_code=HTTPStatus.CREATED)
async def create_report_widget(
    data: ReportWidgetCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Pin a saved report to the dashboard as a widget."""
    # Verify report exists and user has access
    report_result = await db.execute(
        select(SavedReport).where(
            SavedReport.id == data.report_id,
            or_(
                SavedReport.created_by_id == current_user.id,
                SavedReport.is_public == True,
            ),
        )
    )
    report = report_result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Report not found")

    widget = DashboardReportWidget(
        user_id=current_user.id,
        report_id=data.report_id,
        position=data.position,
        width=data.width,
    )
    db.add(widget)
    await db.flush()
    await db.refresh(widget)

    return ReportWidgetResponse(
        id=widget.id,
        user_id=widget.user_id,
        report_id=widget.report_id,
        report_name=report.name,
        report_chart_type=report.chart_type,
        position=widget.position,
        width=widget.width,
        is_visible=widget.is_visible,
        created_at=widget.created_at,
    )


@widgets_router.patch("/{widget_id}", response_model=ReportWidgetResponse)
async def update_report_widget(
    widget_id: int,
    data: ReportWidgetUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update a dashboard report widget's position, width, or visibility."""
    result = await db.execute(
        select(DashboardReportWidget).where(
            DashboardReportWidget.id == widget_id,
            DashboardReportWidget.user_id == current_user.id,
        )
    )
    widget = result.scalar_one_or_none()
    if not widget:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Widget not found")

    if data.position is not None:
        widget.position = data.position
    if data.width is not None:
        widget.width = data.width
    if data.is_visible is not None:
        widget.is_visible = data.is_visible

    await db.flush()
    await db.refresh(widget)

    # Fetch report for response
    report_result = await db.execute(
        select(SavedReport).where(SavedReport.id == widget.report_id)
    )
    report = report_result.scalar_one()

    return ReportWidgetResponse(
        id=widget.id,
        user_id=widget.user_id,
        report_id=widget.report_id,
        report_name=report.name,
        report_chart_type=report.chart_type,
        position=widget.position,
        width=widget.width,
        is_visible=widget.is_visible,
        created_at=widget.created_at,
    )


@widgets_router.delete("/{widget_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_report_widget(
    widget_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Remove a report widget from the dashboard."""
    result = await db.execute(
        select(DashboardReportWidget).where(
            DashboardReportWidget.id == widget_id,
            DashboardReportWidget.user_id == current_user.id,
        )
    )
    widget = result.scalar_one_or_none()
    if not widget:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Widget not found")

    await db.delete(widget)
    await db.flush()


@widgets_router.get("/{widget_id}/data")
async def get_report_widget_data(
    widget_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Execute the widget's underlying report and return chart data."""
    result = await db.execute(
        select(DashboardReportWidget, SavedReport)
        .join(SavedReport, DashboardReportWidget.report_id == SavedReport.id)
        .where(
            DashboardReportWidget.id == widget_id,
            DashboardReportWidget.user_id == current_user.id,
        )
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Widget not found")

    widget, report = row

    definition = ReportDefinition(
        entity_type=report.entity_type,
        metric=report.metric,
        metric_field=report.metric_field,
        group_by=report.group_by,
        date_group=report.date_group,
        filters=json.loads(report.filters) if report.filters else None,
        chart_type=report.chart_type,
    )

    executor = ReportExecutor(db, user_id=current_user.id)
    report_result = await executor.execute(definition)

    return {
        "widget_id": widget.id,
        "report_name": report.name,
        "chart_type": report.chart_type,
        "result": report_result,
    }
