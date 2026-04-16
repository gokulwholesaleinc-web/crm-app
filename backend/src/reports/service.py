"""Report execution service - builds dynamic SQLAlchemy queries from report definitions."""

import csv
import io
from typing import List, Optional, Dict, Type
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.leads.models import Lead
from src.contacts.models import Contact
from src.opportunities.models import Opportunity, PipelineStage
from src.activities.models import Activity
from src.campaigns.models import Campaign
from src.companies.models import Company
from src.payments.models import Payment
from src.contracts.models import Contract
from src.core.filtering import apply_filters_to_query
from src.reports.schemas import ReportDataPoint, ReportResult, ReportDefinition

# Mapping from entity_type string to SQLAlchemy model
ENTITY_MODEL_MAP: Dict[str, Type] = {
    "leads": Lead,
    "contacts": Contact,
    "opportunities": Opportunity,
    "activities": Activity,
    "campaigns": Campaign,
    "companies": Company,
    "payments": Payment,
    "contracts": Contract,
}

# Numeric fields per entity type (for sum/avg/min/max metrics)
NUMERIC_FIELDS: Dict[str, List[str]] = {
    "leads": ["score", "budget_amount"],
    "contacts": [],
    "opportunities": ["amount", "probability"],
    "activities": ["call_duration_minutes"],
    "campaigns": ["budget_amount", "actual_cost", "expected_revenue", "actual_revenue",
                   "num_sent", "num_responses", "num_converted"],
    "companies": ["annual_revenue", "employee_count"],
    "payments": ["amount"],
    "contracts": ["value"],
}


def _get_date_trunc_col(model, date_group: str):
    """Get the appropriate date truncation for grouping."""
    date_col = model.created_at
    if date_group == "day":
        return func.date_trunc("day", date_col)
    elif date_group == "week":
        return func.date_trunc("week", date_col)
    elif date_group == "month":
        return func.date_trunc("month", date_col)
    elif date_group == "quarter":
        return func.date_trunc("quarter", date_col)
    elif date_group == "year":
        return func.date_trunc("year", date_col)
    return func.date_trunc("month", date_col)


def _format_date_label(dt, date_group: str) -> str:
    """Format a date value into a human-readable label."""
    if dt is None:
        return "Unknown"
    if date_group == "day":
        return dt.strftime("%Y-%m-%d")
    elif date_group == "week":
        return f"Week of {dt.strftime('%b %d, %Y')}"
    elif date_group == "month":
        return dt.strftime("%b %Y")
    elif date_group == "quarter":
        quarter = (dt.month - 1) // 3 + 1
        return f"Q{quarter} {dt.year}"
    elif date_group == "year":
        return str(dt.year)
    return dt.strftime("%b %Y")


class ReportExecutor:
    """Executes custom report definitions against the database."""

    def __init__(self, db: AsyncSession, user_id: int = None, is_admin: bool = False):
        self.db = db
        self.user_id = user_id
        self.is_admin = is_admin

    def _apply_owner_filter(self, query, model):
        """Apply owner_id filter if user_id is set and model has owner_id.

        If the model lacks owner_id and the caller is not an admin, raises 403 —
        without an ownership column there is no safe way to scope the results to
        a single user, so the data would leak across tenants/reps.
        """
        if not hasattr(model, "owner_id"):
            if not self.is_admin:
                raise PermissionError("Reports on this entity require admin role")
            return query
        if self.user_id:
            query = query.where(model.owner_id == self.user_id)
        return query

    async def execute(self, definition: ReportDefinition) -> ReportResult:
        """Execute a report definition and return results."""
        model = ENTITY_MODEL_MAP.get(definition.entity_type)
        if not model:
            raise ValueError(f"Unknown entity type: {definition.entity_type}")

        metric_col = self._get_metric_expression(model, definition.metric, definition.metric_field)

        # Determine grouping
        if definition.date_group:
            group_col = _get_date_trunc_col(model, definition.date_group).label("group_label")
        elif definition.group_by:
            col = getattr(model, definition.group_by, None)
            if col is None:
                raise ValueError(f"Unknown field for group_by: {definition.group_by}")
            group_col = col.label("group_label")
        else:
            group_col = None

        if group_col is not None:
            query = select(group_col, metric_col.label("metric_value"))
            query = self._apply_owner_filter(query, model)
            query = apply_filters_to_query(query, model, definition.filters)

            # Handle special join for opportunities grouped by stage
            if definition.entity_type == "opportunities" and definition.group_by == "pipeline_stage_id":
                query = select(
                    PipelineStage.name.label("group_label"),
                    metric_col.label("metric_value"),
                ).select_from(Opportunity).join(PipelineStage)
                query = self._apply_owner_filter(query, Opportunity)
                query = apply_filters_to_query(query, Opportunity, definition.filters)
                query = query.group_by(PipelineStage.name).order_by(metric_col.label("metric_value").desc())
            else:
                query = query.group_by(group_col).order_by(metric_col.label("metric_value").desc())
        else:
            # No grouping - return single aggregate value
            query = select(metric_col.label("metric_value"))
            query = self._apply_owner_filter(query, model)
            query = apply_filters_to_query(query, model, definition.filters)

        result = await self.db.execute(query)
        rows = result.all()

        data = []
        total = 0.0
        for row in rows:
            if group_col is not None:
                label_val = row.group_label
                metric_val = float(row.metric_value or 0)

                if definition.date_group and label_val is not None:
                    label = _format_date_label(label_val, definition.date_group)
                else:
                    label = str(label_val) if label_val is not None else "Unknown"

                data.append(ReportDataPoint(label=label, value=round(metric_val, 2)))
                total += metric_val
            else:
                val = float(row.metric_value or 0)
                data.append(ReportDataPoint(label=definition.metric, value=round(val, 2)))
                total = val

        return ReportResult(
            entity_type=definition.entity_type,
            metric=definition.metric,
            metric_field=definition.metric_field,
            group_by=definition.group_by,
            chart_type=definition.chart_type,
            data=data,
            total=round(total, 2),
        )

    def _get_metric_expression(self, model, metric: str, metric_field: Optional[str]):
        """Build the SQLAlchemy aggregate expression."""
        if metric == "count":
            return func.count(model.id)

        if not metric_field:
            raise ValueError(f"metric_field is required for metric: {metric}")

        col = getattr(model, metric_field, None)
        if col is None:
            raise ValueError(f"Unknown metric field: {metric_field}")

        if metric == "sum":
            return func.sum(col)
        elif metric == "avg":
            return func.avg(col)
        elif metric == "min":
            return func.min(col)
        elif metric == "max":
            return func.max(col)
        else:
            raise ValueError(f"Unknown metric: {metric}")

    async def export_csv(self, definition: ReportDefinition) -> str:
        """Execute a report and export results as CSV."""
        result = await self.execute(definition)

        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        group_label = definition.group_by or definition.date_group or "Category"
        metric_label = f"{definition.metric}"
        if definition.metric_field:
            metric_label += f"({definition.metric_field})"
        writer.writerow([group_label, metric_label])

        # Data rows
        for point in result.data:
            writer.writerow([point.label, point.value])

        # Total
        if result.total is not None:
            writer.writerow(["Total", result.total])

        return output.getvalue()


# Pre-built report templates
REPORT_TEMPLATES = [
    {
        "id": "pipeline_by_stage",
        "name": "Sales Pipeline by Stage",
        "description": "Opportunities grouped by pipeline stage",
        "entity_type": "opportunities",
        "metric": "count",
        "group_by": "pipeline_stage_id",
        "chart_type": "funnel",
    },
    {
        "id": "revenue_by_month",
        "name": "Revenue by Month",
        "description": "Total opportunity revenue grouped by month",
        "entity_type": "opportunities",
        "metric": "sum",
        "metric_field": "amount",
        "date_group": "month",
        "chart_type": "line",
    },
    {
        "id": "lead_conversion",
        "name": "Lead Conversion Rate",
        "description": "Leads grouped by status to show conversion funnel",
        "entity_type": "leads",
        "metric": "count",
        "group_by": "status",
        "chart_type": "bar",
    },
    {
        "id": "activity_by_rep",
        "name": "Activity Summary by Rep",
        "description": "Activity counts grouped by owner",
        "entity_type": "activities",
        "metric": "count",
        "group_by": "owner_id",
        "chart_type": "table",
    },
    {
        "id": "campaign_performance",
        "name": "Campaign Performance",
        "description": "Campaign results by campaign type",
        "entity_type": "campaigns",
        "metric": "sum",
        "metric_field": "num_responses",
        "group_by": "campaign_type",
        "chart_type": "bar",
    },
    {
        "id": "deals_won_lost",
        "name": "Deals Won/Lost Over Time",
        "description": "Opportunity count over time",
        "entity_type": "opportunities",
        "metric": "count",
        "date_group": "month",
        "chart_type": "line",
    },
    {
        "id": "payment_summary_by_month",
        "name": "Payment Summary by Month",
        "description": "Total payment amounts grouped by month",
        "entity_type": "payments",
        "metric": "sum",
        "metric_field": "amount",
        "date_group": "month",
        "chart_type": "bar",
    },
    {
        "id": "contracts_by_status",
        "name": "Contracts by Status",
        "description": "Contract count grouped by status",
        "entity_type": "contracts",
        "metric": "count",
        "group_by": "status",
        "chart_type": "pie",
    },
    {
        "id": "revenue_by_source",
        "name": "Revenue by Sales Source",
        "description": "Total opportunity revenue grouped by source",
        "entity_type": "opportunities",
        "metric": "sum",
        "metric_field": "amount",
        "group_by": "source",
        "chart_type": "bar",
    },
    {
        "id": "pipeline_value_by_owner",
        "name": "Pipeline Value by Owner",
        "description": "Total opportunity value grouped by owner",
        "entity_type": "opportunities",
        "metric": "sum",
        "metric_field": "amount",
        "group_by": "owner_id",
        "chart_type": "bar",
    },
]
