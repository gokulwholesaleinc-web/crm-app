"""Report execution and saved report service."""

import json
import io
import csv
from typing import Optional, List

from sqlalchemy import select, func, extract, literal, desc, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from src.reports.models import SavedReport
from src.reports.schemas import (
    ReportDefinition,
    ReportDataPoint,
    ReportResult,
    ReportTemplate,
    SavedReportCreate,
    SavedReportUpdate,
)
from src.core.filtering import apply_filters_to_query
from src.leads.models import Lead
from src.contacts.models import Contact
from src.companies.models import Company
from src.opportunities.models import Opportunity
from src.activities.models import Activity


ENTITY_MODEL_MAP = {
    "leads": Lead,
    "contacts": Contact,
    "companies": Company,
    "opportunities": Opportunity,
    "activities": Activity,
}

REPORT_TEMPLATES = [
    ReportTemplate(
        id="leads_by_status",
        name="Leads by Status",
        description="Count of leads grouped by status",
        entity_type="leads",
        group_by="status",
        metric="count",
        chart_type="pie",
    ),
    ReportTemplate(
        id="leads_by_source",
        name="Leads by Source",
        description="Count of leads grouped by source",
        entity_type="leads",
        group_by="source_id",
        metric="count",
        chart_type="bar",
    ),
    ReportTemplate(
        id="opportunities_by_stage",
        name="Opportunities by Stage",
        description="Count of opportunities grouped by pipeline stage",
        entity_type="opportunities",
        group_by="pipeline_stage_id",
        metric="count",
        chart_type="funnel",
    ),
    ReportTemplate(
        id="revenue_by_stage",
        name="Revenue by Stage",
        description="Total revenue grouped by pipeline stage",
        entity_type="opportunities",
        group_by="pipeline_stage_id",
        metric="sum",
        metric_field="amount",
        chart_type="bar",
    ),
    ReportTemplate(
        id="activities_by_type",
        name="Activities by Type",
        description="Count of activities grouped by type",
        entity_type="activities",
        group_by="activity_type",
        metric="count",
        chart_type="pie",
    ),
    ReportTemplate(
        id="companies_by_industry",
        name="Companies by Industry",
        description="Count of companies grouped by industry",
        entity_type="companies",
        group_by="industry",
        metric="count",
        chart_type="bar",
    ),
]


class ReportExecutor:
    """Executes report definitions against the database."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def execute(self, definition: ReportDefinition) -> ReportResult:
        model = ENTITY_MODEL_MAP.get(definition.entity_type)
        if model is None:
            return ReportResult(
                data=[], total=0,
                entity_type=definition.entity_type, metric=definition.metric,
            )

        metric_col = self._get_metric_column(model, definition)
        if metric_col is None:
            return ReportResult(
                data=[], total=0,
                entity_type=definition.entity_type, metric=definition.metric,
            )

        if definition.group_by:
            group_col = getattr(model, definition.group_by, None)
            if group_col is None:
                return ReportResult(
                    data=[], total=0,
                    entity_type=definition.entity_type, metric=definition.metric,
                )

            if definition.date_group and definition.date_group in ("month", "year", "day"):
                label_col = extract(definition.date_group, group_col)
            else:
                label_col = cast(group_col, String)

            query = (
                select(label_col.label("group_label"), metric_col.label("metric_value"))
                .group_by(label_col)
                .order_by(desc("metric_value"))
            )
        else:
            query = select(metric_col.label("metric_value"))

        if definition.filters:
            query = apply_filters_to_query(query, model, definition.filters)

        result = await self.session.execute(query)
        rows = result.all()

        if definition.group_by:
            data = [
                ReportDataPoint(label=str(row.group_label or "Unknown"), value=float(row.metric_value or 0))
                for row in rows
            ]
            total = sum(dp.value for dp in data)
        else:
            val = float(rows[0].metric_value or 0) if rows else 0
            data = [ReportDataPoint(label="Total", value=val)]
            total = val

        return ReportResult(
            data=data,
            total=total,
            entity_type=definition.entity_type,
            metric=definition.metric,
            group_by=definition.group_by,
        )

    async def export_csv(self, definition: ReportDefinition) -> str:
        result = await self.execute(definition)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Label", "Value"])
        for dp in result.data:
            writer.writerow([dp.label, dp.value])
        writer.writerow(["Total", result.total])
        return output.getvalue()

    def _get_metric_column(self, model, definition: ReportDefinition):
        if definition.metric == "count":
            return func.count(model.id)

        field = getattr(model, definition.metric_field, None) if definition.metric_field else None
        if field is None:
            return None

        metric_funcs = {
            "sum": func.sum,
            "avg": func.avg,
            "min": func.min,
            "max": func.max,
        }
        metric_func = metric_funcs.get(definition.metric)
        if metric_func is None:
            return None
        return metric_func(field)


class SavedReportService:
    """CRUD service for saved reports."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, data: SavedReportCreate, user_id: int) -> SavedReport:
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
            created_by_id=user_id,
            is_public=data.is_public,
        )
        self.session.add(report)
        await self.session.flush()
        await self.session.refresh(report)
        return report

    async def list(self, user_id: int, entity_type: Optional[str] = None) -> List[SavedReport]:
        query = select(SavedReport).where(
            (SavedReport.created_by_id == user_id) | (SavedReport.is_public == True)
        )
        if entity_type:
            query = query.where(SavedReport.entity_type == entity_type)
        query = query.order_by(SavedReport.created_at.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get(self, report_id: int) -> Optional[SavedReport]:
        result = await self.session.execute(
            select(SavedReport).where(SavedReport.id == report_id)
        )
        return result.scalar_one_or_none()

    async def update(self, report: SavedReport, data: SavedReportUpdate) -> SavedReport:
        update_data = data.model_dump(exclude_unset=True)
        if "filters" in update_data and update_data["filters"] is not None:
            update_data["filters"] = json.dumps(update_data["filters"])
        for key, val in update_data.items():
            setattr(report, key, val)
        await self.session.flush()
        await self.session.refresh(report)
        return report

    async def delete(self, report: SavedReport):
        await self.session.delete(report)
        await self.session.flush()
