"""Scheduled report delivery service.

Finds SavedReports with a schedule (daily/weekly/monthly), checks if they're
due based on last_sent_at, executes the report, and emails the CSV to recipients.
"""

import html
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.reports.models import SavedReport
from src.reports.schemas import ReportDefinition
from src.reports.service import ReportExecutor

logger = logging.getLogger(__name__)

SCHEDULE_INTERVALS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "monthly": timedelta(days=30),
}


class ReportDeliveryService:
    """Delivers scheduled reports via email."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def deliver_due_reports(self) -> int:
        """Find and deliver all reports that are due for scheduled delivery."""
        from src.email.service import EmailService

        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(SavedReport).where(
                SavedReport.schedule.isnot(None),
                SavedReport.recipients.isnot(None),
            )
        )
        scheduled_reports = list(result.scalars().all())

        delivered = 0
        for report in scheduled_reports:
            if not self._is_due(report, now):
                continue

            recipients = self._parse_recipients(report.recipients)
            if not recipients:
                continue

            try:
                csv_content = await self._execute_report_csv(report)
                email_service = EmailService(self.db)

                subject = f"Scheduled Report: {report.name}"
                body = self._build_report_email(report.name, report.description, csv_content)

                for recipient in recipients:
                    await email_service.queue_email(
                        to_email=recipient,
                        subject=subject,
                        body=body,
                        sent_by_id=report.created_by_id,
                        entity_type="reports",
                        entity_id=report.id,
                    )

                report.last_sent_at = now
                delivered += 1
                logger.info("Delivered scheduled report '%s' to %d recipients", report.name, len(recipients))

            except Exception as e:
                logger.error("Failed to deliver report '%s': %s", report.name, e)

        await self.db.flush()
        return delivered

    def _is_due(self, report: SavedReport, now: datetime) -> bool:
        """Check if a scheduled report is due for delivery."""
        interval = SCHEDULE_INTERVALS.get(report.schedule)
        if not interval:
            return False

        if report.last_sent_at is None:
            return True

        return now >= report.last_sent_at + interval

    def _parse_recipients(self, recipients_json: Optional[str]) -> list:
        """Parse recipients JSON string into a list of email addresses."""
        if not recipients_json:
            return []
        try:
            recipients = json.loads(recipients_json)
            return [r for r in recipients if isinstance(r, str) and "@" in r]
        except (json.JSONDecodeError, TypeError):
            return []

    async def _execute_report_csv(self, report: SavedReport) -> str:
        """Execute a saved report and return CSV content."""
        filters = None
        if report.filters:
            filters = json.loads(report.filters) if isinstance(report.filters, str) else report.filters

        definition = ReportDefinition(
            entity_type=report.entity_type,
            metric=report.metric,
            metric_field=report.metric_field,
            group_by=report.group_by,
            date_group=report.date_group,
            filters=filters,
            chart_type=report.chart_type,
        )

        executor = ReportExecutor(self.db, user_id=report.created_by_id)
        return await executor.export_csv(definition)

    def _build_report_email(self, name: str, description: Optional[str], csv_content: str) -> str:
        """Build HTML email body with report data as an inline table.

        Every value that originates from report data or user-supplied fields
        (report name, description, cell contents) is HTML-escaped before being
        interpolated into the template to prevent stored XSS via crafted
        record values or report metadata.
        """
        import csv
        import io

        reader = csv.reader(io.StringIO(csv_content))
        rows = list(reader)

        table_html = "<table style='border-collapse:collapse;width:100%;font-family:sans-serif;'>"
        for i, row in enumerate(rows[:50]):
            tag = "th" if i == 0 else "td"
            style = "border:1px solid #ddd;padding:8px;text-align:left;"
            if i == 0:
                style += "background-color:#f8f9fa;font-weight:bold;"
            cells = "".join(
                f"<{tag} style='{style}'>{html.escape(str(cell))}</{tag}>"
                for cell in row
            )
            table_html += f"<tr>{cells}</tr>"
        table_html += "</table>"

        truncated = ""
        if len(rows) > 50:
            truncated = f"<p style='color:#666;font-size:14px;'>Showing first 50 of {len(rows) - 1} rows.</p>"

        desc_html = (
            f"<p style='color:#666;'>{html.escape(description)}</p>" if description else ""
        )
        safe_name = html.escape(name or "")

        return f"""
        <div style="font-family:sans-serif;max-width:800px;margin:0 auto;">
            <h2 style="color:#1a1a1a;">{safe_name}</h2>
            {desc_html}
            <p style="color:#888;font-size:13px;">Generated on {datetime.now(timezone.utc).strftime('%B %d, %Y at %H:%M UTC')}</p>
            {table_html}
            {truncated}
        </div>
        """
