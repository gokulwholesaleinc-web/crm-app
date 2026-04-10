"""Integration tests for infrastructure buildout:
- Campaign multi-step execution
- Google Calendar integration endpoints
- Meta OAuth + lead capture webhook
- Mapped import
- Scheduled report delivery
- Campaign analytics
"""

import json
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.campaigns.models import Campaign, CampaignMember, EmailTemplate, EmailCampaignStep
from src.campaigns.service import CampaignService
from src.reports.models import SavedReport
from src.reports.delivery import ReportDeliveryService
from src.dashboard.models import DashboardReportWidget
from src.meta.models import MetaLeadCapture
from src.meta.service import MetaService
from src.integrations.google_calendar.models import GoogleCalendarCredential
from src.integrations.google_calendar.service import GoogleCalendarService
from src.auth.models import User
from src.leads.models import Lead
from src.email.models import EmailQueue


# =============================================================================
# Campaign Multi-Step Execution
# =============================================================================


class TestCampaignExecution:
    """Tests for the fixed campaign execute endpoint."""

    @pytest_asyncio.fixture
    async def campaign_setup(self, db_session: AsyncSession, test_user: User, test_lead):
        """Set up a campaign with steps and members."""
        template = EmailTemplate(
            name="Welcome Email",
            subject_template="Hello {{first_name}}",
            body_template="Welcome to our service, {{first_name}}!",
            created_by_id=test_user.id,
        )
        db_session.add(template)
        await db_session.flush()

        template2 = EmailTemplate(
            name="Follow Up",
            subject_template="Checking in {{first_name}}",
            body_template="Just following up, {{first_name}}.",
            created_by_id=test_user.id,
        )
        db_session.add(template2)
        await db_session.flush()

        campaign = Campaign(
            name="Test Multi-Step Campaign",
            campaign_type="email",
            status="planned",
            owner_id=test_user.id,
        )
        db_session.add(campaign)
        await db_session.flush()

        step1 = EmailCampaignStep(
            campaign_id=campaign.id,
            template_id=template.id,
            delay_days=0,
            step_order=0,
        )
        step2 = EmailCampaignStep(
            campaign_id=campaign.id,
            template_id=template2.id,
            delay_days=3,
            step_order=1,
        )
        db_session.add_all([step1, step2])
        await db_session.flush()

        member = CampaignMember(
            campaign_id=campaign.id,
            member_type="lead",
            member_id=test_lead.id,
        )
        db_session.add(member)
        await db_session.commit()
        return campaign, template, template2

    async def test_execute_campaign_returns_step_info(
        self, client: AsyncClient, auth_headers: dict, campaign_setup
    ):
        """Should return multi-step execution info."""
        campaign, _, _ = campaign_setup
        response = await client.post(
            f"/api/campaigns/{campaign.id}/execute",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_steps"] == 2
        assert data["status"] == "active"

    async def test_execute_campaign_no_steps(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: User
    ):
        """Should return message when no steps are configured."""
        campaign = Campaign(
            name="Empty Campaign",
            campaign_type="email",
            status="planned",
            owner_id=test_user.id,
        )
        db_session.add(campaign)
        await db_session.commit()

        response = await client.post(
            f"/api/campaigns/{campaign.id}/execute",
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert "No steps" in response.json()["message"]

    async def test_campaign_response_includes_new_fields(
        self, client: AsyncClient, auth_headers: dict, campaign_setup
    ):
        """Should include current_step, next_step_at, is_executing in response."""
        campaign, _, _ = campaign_setup
        response = await client.get(
            f"/api/campaigns/{campaign.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "current_step" in data
        assert "is_executing" in data
        assert "next_step_at" in data


# =============================================================================
# Campaign Step Processing (Service layer)
# =============================================================================


class TestCampaignStepProcessing:
    """Tests for process_due_campaign_steps in the service layer."""

    async def test_process_no_due_campaigns(self, db_session: AsyncSession):
        """Should return empty when no campaigns are due."""
        service = CampaignService(db_session)
        results = await service.process_due_campaign_steps()
        assert results == []


# =============================================================================
# Google Calendar Integration
# =============================================================================


class TestGoogleCalendarEndpoints:
    """Tests for Google Calendar integration endpoints."""

    async def test_get_sync_status_not_connected(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return not connected when no credentials stored."""
        response = await client.get(
            "/api/integrations/google-calendar/status",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False
        assert data["synced_events_count"] == 0

    async def test_connect_without_config(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return error when Google Calendar not configured."""
        response = await client.post(
            "/api/integrations/google-calendar/connect",
            headers=auth_headers,
            json={"redirect_uri": "http://localhost:3000/callback"},
        )
        assert response.status_code == 400

    async def test_disconnect_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return 404 when no connection exists."""
        response = await client.delete(
            "/api/integrations/google-calendar/disconnect",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_sync_status_with_credential(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: User
    ):
        """Should return connected when credential exists."""
        cred = GoogleCalendarCredential(
            user_id=test_user.id,
            access_token="test_token",
            refresh_token="test_refresh",
            calendar_id="primary",
            is_active=True,
        )
        db_session.add(cred)
        await db_session.commit()

        response = await client.get(
            "/api/integrations/google-calendar/status",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is True
        assert data["calendar_id"] == "primary"


# =============================================================================
# Meta Integration
# =============================================================================


class TestMetaEndpoints:
    """Tests for Meta (Facebook/Instagram) integration endpoints."""

    async def test_get_connection_status(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return not connected by default."""
        response = await client.get(
            "/api/meta/status",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["connected"] is False

    async def test_connect_without_config(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return error when Meta not configured."""
        response = await client.post(
            "/api/meta/connect",
            headers=auth_headers,
            json={"redirect_uri": "http://localhost:3000/callback"},
        )
        assert response.status_code == 400

    async def test_disconnect_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return 404 when no Meta connection exists."""
        response = await client.delete(
            "/api/meta/disconnect",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_webhook_verification_fails(
        self, client: AsyncClient
    ):
        """Should reject webhook verification with wrong token."""
        response = await client.get(
            "/api/meta/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "wrong_token",
                "hub.challenge": "test_challenge",
            },
        )
        assert response.status_code == 403

    async def test_webhook_verification_succeeds(
        self, client: AsyncClient
    ):
        """Should return challenge on correct verification."""
        response = await client.get(
            "/api/meta/webhook",
            params={
                "hub.mode": "subscribe",
                "hub.verify_token": "crm_meta_webhook",
                "hub.challenge": "test_challenge_123",
            },
        )
        assert response.status_code == 200
        assert response.text == "test_challenge_123"

    async def test_webhook_ignores_non_page(
        self, client: AsyncClient
    ):
        """Should ignore webhook events for non-page objects."""
        response = await client.post(
            "/api/meta/webhook",
            json={"object": "user", "entry": []},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"

    async def test_lead_capture_webhook(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should capture leads from webhook payload."""
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "123456789",
                    "changes": [
                        {
                            "field": "leadgen",
                            "value": {
                                "leadgen_id": "lead_001",
                                "form_id": "form_001",
                                "ad_id": "ad_001",
                            },
                        }
                    ],
                }
            ],
        }
        response = await client.post("/api/meta/webhook", json=payload)
        assert response.status_code == 200
        assert response.json()["leads_captured"] == 1

    async def test_lead_capture_dedup(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Should skip duplicate leads on repeated webhook delivery."""
        payload = {
            "object": "page",
            "entry": [
                {
                    "id": "123456789",
                    "changes": [
                        {
                            "field": "leadgen",
                            "value": {
                                "leadgen_id": "lead_dedup_test",
                                "form_id": "form_002",
                            },
                        }
                    ],
                }
            ],
        }
        # First call should capture
        r1 = await client.post("/api/meta/webhook", json=payload)
        assert r1.json()["leads_captured"] == 1

        # Second call should skip duplicate
        r2 = await client.post("/api/meta/webhook", json=payload)
        assert r2.json()["leads_captured"] == 0


# =============================================================================
# Mapped Import
# =============================================================================


class TestMappedImport:
    """Tests for the mapped import endpoint."""

    async def test_mapped_import_leads(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should import leads using custom column mapping."""
        csv_content = "First,Last,E-Mail,Company\nAlice,Wonder,alice@example.com,Wonderland Inc\nBob,Builder,bob@example.com,FixIt Corp\n"

        mapping = json.dumps({"First": "first_name", "Last": "last_name", "E-Mail": "email", "Company": "company_name"})

        response = await client.post(
            "/api/import-export/import/leads/mapped",
            headers=auth_headers,
            files={"file": ("leads.csv", csv_content, "text/csv")},
            data={"column_mapping": mapping, "skip_errors": "true"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["imported_count"] == 2

    async def test_mapped_import_invalid_field(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should reject mapping with invalid target field."""
        csv_content = "Name,Email\nAlice,alice@example.com\n"
        mapping = json.dumps({"Name": "nonexistent_field", "Email": "email"})

        response = await client.post(
            "/api/import-export/import/leads/mapped",
            headers=auth_headers,
            files={"file": ("leads.csv", csv_content, "text/csv")},
            data={"column_mapping": mapping},
        )
        assert response.status_code == 400

    async def test_mapped_import_skip_column(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should skip columns mapped to 'skip'."""
        csv_content = "First,Last,Email,Notes\nAlice,Wonder,alice2@example.com,Some notes\n"
        mapping = json.dumps({"First": "first_name", "Last": "last_name", "Email": "email", "Notes": "skip"})

        response = await client.post(
            "/api/import-export/import/leads/mapped",
            headers=auth_headers,
            files={"file": ("leads.csv", csv_content, "text/csv")},
            data={"column_mapping": mapping, "skip_errors": "true"},
        )
        assert response.status_code == 200
        assert response.json()["imported_count"] == 1

    async def test_preview_includes_new_fields(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should include csv_headers and available_fields in preview."""
        csv_content = "First Name,Last Name,Email\nJohn,Doe,jd@example.com\n"
        response = await client.post(
            "/api/import-export/preview/leads",
            headers=auth_headers,
            files={"file": ("leads.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "csv_headers" in data
        assert "available_fields" in data
        assert "First Name" in data["csv_headers"]


# =============================================================================
# Scheduled Report Delivery
# =============================================================================


class TestScheduledReportDelivery:
    """Tests for the report delivery service."""

    async def test_no_reports_due(self, db_session: AsyncSession):
        """Should return 0 when no reports are scheduled."""
        service = ReportDeliveryService(db_session)
        delivered = await service.deliver_due_reports()
        assert delivered == 0

    async def test_report_not_due_yet(self, db_session: AsyncSession, test_user: User):
        """Should skip report that was just sent."""
        from datetime import datetime, timezone

        report = SavedReport(
            name="Daily Report",
            entity_type="leads",
            metric="count",
            chart_type="bar",
            created_by_id=test_user.id,
            schedule="daily",
            recipients=json.dumps(["test@example.com"]),
            last_sent_at=datetime.now(timezone.utc),
        )
        db_session.add(report)
        await db_session.commit()

        service = ReportDeliveryService(db_session)
        delivered = await service.deliver_due_reports()
        assert delivered == 0

    async def test_is_due_no_last_sent(self, db_session: AsyncSession):
        """Should be due if never sent before."""
        from datetime import datetime, timezone

        report = SavedReport(
            name="New Report",
            entity_type="leads",
            metric="count",
            chart_type="bar",
            created_by_id=1,
            schedule="daily",
            recipients=json.dumps(["test@example.com"]),
        )
        service = ReportDeliveryService(db_session)
        assert service._is_due(report, datetime.now(timezone.utc)) is True

    async def test_parse_recipients(self, db_session: AsyncSession):
        """Should parse valid email addresses from JSON."""
        service = ReportDeliveryService(db_session)
        assert service._parse_recipients(json.dumps(["a@b.com", "c@d.com"])) == ["a@b.com", "c@d.com"]
        assert service._parse_recipients(json.dumps(["not_an_email"])) == []
        assert service._parse_recipients(None) == []
        assert service._parse_recipients("invalid json") == []

    async def test_build_report_email_escapes_cells_and_metadata(
        self, db_session: AsyncSession
    ):
        """Cells, report name, and description must be HTML-escaped."""
        service = ReportDeliveryService(db_session)
        csv_content = (
            "Name,Note\r\n"
            "<script>alert('x')</script>,<img src=x onerror=alert(1)>\r\n"
        )
        body = service._build_report_email(
            name="<b>Weekly</b>",
            description="<script>evil()</script>",
            csv_content=csv_content,
        )
        # No active tags should survive from attacker-controlled inputs.
        assert "<script>" not in body
        assert "<img src=x" not in body
        assert "<b>Weekly</b>" not in body
        # Their escaped forms should be present.
        assert "&lt;script&gt;" in body
        assert "&lt;b&gt;Weekly" in body

    async def test_schedule_field_in_report_response(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: User
    ):
        """Should include schedule and recipients in saved report response."""
        response = await client.post(
            "/api/reports",
            headers=auth_headers,
            json={
                "name": "Scheduled Test",
                "entity_type": "leads",
                "metric": "count",
                "chart_type": "bar",
                "schedule": "weekly",
                "recipients": ["report@example.com"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["schedule"] == "weekly"
        assert data["recipients"] == ["report@example.com"]


# =============================================================================
# Notification Event Wiring
# =============================================================================


class TestNotificationEventWiring:
    """Tests that key CRM events auto-create notifications."""

    @pytest.mark.skip(reason="Notification handler opens a second session; SQLite StaticPool shares one connection so nested commits fail")
    async def test_lead_creation_triggers_notification(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_lead_source
    ):
        """Creating a lead via API should auto-create a notification for the owner."""
        response = await client.post(
            "/api/leads",
            headers=auth_headers,
            json={
                "first_name": "Notification",
                "last_name": "Test",
                "email": "notif-test@example.com",
                "source_id": test_lead_source.id,
                "status": "new",
            },
        )
        assert response.status_code == 201

        # Check that a notification was created
        notif_response = await client.get(
            "/api/notifications",
            headers=auth_headers,
        )
        assert notif_response.status_code == 200
        items = notif_response.json()["items"]
        lead_notifs = [n for n in items if n["type"] == "lead_created"]
        assert len(lead_notifs) >= 1
        assert "Notification Test" in lead_notifs[0]["message"]

# =============================================================================
# Dashboard Report Widgets
# =============================================================================


class TestDashboardReportWidgets:
    """Tests for dashboard report widget CRUD and data endpoint."""

    @pytest_asyncio.fixture
    async def widget_report(self, db_session: AsyncSession, test_user: User):
        """Create a saved report for widget tests."""
        report = SavedReport(
            name="Leads by Status Widget",
            entity_type="leads",
            metric="count",
            group_by="status",
            chart_type="bar",
            created_by_id=test_user.id,
        )
        db_session.add(report)
        await db_session.commit()
        await db_session.refresh(report)
        return report

    async def test_create_widget(
        self, client: AsyncClient, auth_headers: dict, widget_report
    ):
        """Should create a dashboard report widget."""
        response = await client.post(
            "/api/dashboard/widgets",
            headers=auth_headers,
            json={
                "report_id": widget_report.id,
                "position": 0,
                "width": "half",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["report_id"] == widget_report.id
        assert data["report_name"] == "Leads by Status Widget"
        assert data["report_chart_type"] == "bar"
        assert data["width"] == "half"
        assert data["is_visible"] is True

    async def test_create_widget_report_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return 404 when report does not exist."""
        response = await client.post(
            "/api/dashboard/widgets",
            headers=auth_headers,
            json={"report_id": 99999, "position": 0, "width": "half"},
        )
        assert response.status_code == 404

    async def test_list_widgets(
        self, client: AsyncClient, auth_headers: dict, widget_report, db_session: AsyncSession, test_user: User
    ):
        """Should list all widgets for the current user."""
        widget = DashboardReportWidget(
            user_id=test_user.id,
            report_id=widget_report.id,
            position=0,
            width="full",
        )
        db_session.add(widget)
        await db_session.commit()

        response = await client.get(
            "/api/dashboard/widgets",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["report_name"] == "Leads by Status Widget"

    async def test_update_widget(
        self, client: AsyncClient, auth_headers: dict, widget_report, db_session: AsyncSession, test_user: User
    ):
        """Should update widget position, width, and visibility."""
        widget = DashboardReportWidget(
            user_id=test_user.id,
            report_id=widget_report.id,
            position=0,
            width="half",
        )
        db_session.add(widget)
        await db_session.commit()
        await db_session.refresh(widget)

        response = await client.patch(
            f"/api/dashboard/widgets/{widget.id}",
            headers=auth_headers,
            json={"position": 2, "width": "full", "is_visible": False},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["position"] == 2
        assert data["width"] == "full"
        assert data["is_visible"] is False

    async def test_update_widget_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return 404 when widget does not exist."""
        response = await client.patch(
            "/api/dashboard/widgets/99999",
            headers=auth_headers,
            json={"position": 1},
        )
        assert response.status_code == 404

    async def test_delete_widget(
        self, client: AsyncClient, auth_headers: dict, widget_report, db_session: AsyncSession, test_user: User
    ):
        """Should delete a dashboard report widget."""
        widget = DashboardReportWidget(
            user_id=test_user.id,
            report_id=widget_report.id,
            position=0,
            width="half",
        )
        db_session.add(widget)
        await db_session.commit()
        await db_session.refresh(widget)

        response = await client.delete(
            f"/api/dashboard/widgets/{widget.id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Verify widget is gone
        list_response = await client.get(
            "/api/dashboard/widgets",
            headers=auth_headers,
        )
        widget_ids = [w["id"] for w in list_response.json()]
        assert widget.id not in widget_ids

    async def test_delete_widget_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return 404 when deleting nonexistent widget."""
        response = await client.delete(
            "/api/dashboard/widgets/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_widget_data_endpoint(
        self, client: AsyncClient, auth_headers: dict, widget_report, db_session: AsyncSession, test_user: User
    ):
        """Should execute the widget's report and return chart data."""
        widget = DashboardReportWidget(
            user_id=test_user.id,
            report_id=widget_report.id,
            position=0,
            width="half",
        )
        db_session.add(widget)
        await db_session.commit()
        await db_session.refresh(widget)

        response = await client.get(
            f"/api/dashboard/widgets/{widget.id}/data",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["widget_id"] == widget.id
        assert data["report_name"] == "Leads by Status Widget"
        assert data["chart_type"] == "bar"
        assert "result" in data
        assert data["result"]["entity_type"] == "leads"

    async def test_widget_data_not_found(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should return 404 when widget does not exist."""
        response = await client.get(
            "/api/dashboard/widgets/99999/data",
            headers=auth_headers,
        )
        assert response.status_code == 404


# =============================================================================
# Monday.com CSV Import
# =============================================================================


class TestMondayCsvImport:
    """Tests for Monday.com CSV format detection, import, and status mapping."""

    async def test_detect_monday_csv_format(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should detect Monday.com CSV format from signature headers."""
        csv_content = (
            "Name,Email,Status,Subitems,Last Updated,Creation Log,Item ID\n"
            "Alice,alice@example.com,Working on it,,,2024-01-01,12345\n"
        )
        response = await client.post(
            "/api/import-export/preview/leads",
            headers=auth_headers,
            files={"file": ("monday.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["source_detected"] == "monday.com"

    async def test_no_monday_detection_for_normal_csv(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should not flag a normal CSV as Monday.com."""
        csv_content = "First Name,Last Name,Email\nJohn,Doe,jd@example.com\n"
        response = await client.post(
            "/api/import-export/preview/leads",
            headers=auth_headers,
            files={"file": ("normal.csv", csv_content, "text/csv")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["source_detected"] is None

    async def test_import_monday_csv_with_typical_columns(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Should import a Monday.com-style CSV with typical column names."""
        csv_content = (
            "Name,Email,Phone,Status,Text,Numbers,Subitems,Last Updated,Creation Log,Item ID\n"
            "Jane Monday,jane@monday.test,555-0100,Working on it,Interested in services,5000,,,2024-01-01,99001\n"
            "Bob Monday,bob@monday.test,555-0200,Done,Signed contract,12000,,,2024-01-02,99002\n"
        )
        response = await client.post(
            "/api/import-export/import/leads",
            headers=auth_headers,
            files={"file": ("monday_leads.csv", csv_content, "text/csv")},
            data={"skip_errors": "true"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["imported_count"] == 2

    async def test_monday_status_mapping(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession
    ):
        """Should map Monday.com status labels to CRM lead statuses."""
        csv_content = (
            "Name,Email,Status,Subitems,Last Updated,Creation Log,Item ID\n"
            "Status Test 1,st1@monday.test,Working on it,,,2024-01-01,88001\n"
            "Status Test 2,st2@monday.test,Done,,,2024-01-01,88002\n"
            "Status Test 3,st3@monday.test,Stuck,,,2024-01-01,88003\n"
            "Status Test 4,st4@monday.test,Not Started,,,2024-01-01,88004\n"
        )
        response = await client.post(
            "/api/import-export/import/leads",
            headers=auth_headers,
            files={"file": ("monday_status.csv", csv_content, "text/csv")},
            data={"skip_errors": "true"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["imported_count"] == 4

        # Verify statuses were mapped correctly
        from sqlalchemy import select
        result = await db_session.execute(
            select(Lead).where(Lead.email.in_([
                "st1@monday.test", "st2@monday.test",
                "st3@monday.test", "st4@monday.test",
            ]))
        )
        leads = {lead.email: lead.status for lead in result.scalars().all()}
        assert leads["st1@monday.test"] == "contacted"
        assert leads["st2@monday.test"] == "converted"
        assert leads["st3@monday.test"] == "unqualified"
        assert leads["st4@monday.test"] == "new"


# =============================================================================
# Campaign Analytics
# =============================================================================


class TestCampaignAnalytics:
    """Tests for the campaign analytics endpoint."""

    @pytest_asyncio.fixture
    async def analytics_campaign(self, db_session: AsyncSession, test_user: User, test_lead):
        """Set up a campaign with steps, members, and email queue entries."""
        template1 = EmailTemplate(
            name="Welcome",
            subject_template="Welcome {{first_name}}",
            body_template="Welcome!",
            created_by_id=test_user.id,
        )
        template2 = EmailTemplate(
            name="Follow Up",
            subject_template="Follow up {{first_name}}",
            body_template="Following up.",
            created_by_id=test_user.id,
        )
        db_session.add_all([template1, template2])
        await db_session.flush()

        campaign = Campaign(
            name="Analytics Test Campaign",
            campaign_type="email",
            status="active",
            owner_id=test_user.id,
        )
        db_session.add(campaign)
        await db_session.flush()

        step1 = EmailCampaignStep(
            campaign_id=campaign.id, template_id=template1.id,
            delay_days=0, step_order=0,
        )
        step2 = EmailCampaignStep(
            campaign_id=campaign.id, template_id=template2.id,
            delay_days=3, step_order=1,
        )
        db_session.add_all([step1, step2])
        await db_session.flush()

        member = CampaignMember(
            campaign_id=campaign.id, member_type="lead", member_id=test_lead.id,
        )
        db_session.add(member)
        await db_session.flush()

        # Create email queue entries for step 1
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        eq1 = EmailQueue(
            to_email="jane.smith@example.com",
            subject="Welcome Jane",
            body="Welcome!",
            status="sent",
            campaign_id=campaign.id,
            template_id=template1.id,
            sent_by_id=test_user.id,
            sent_at=now,
            opened_at=now,
            open_count=1,
        )
        eq2 = EmailQueue(
            to_email="other@example.com",
            subject="Welcome Other",
            body="Welcome!",
            status="sent",
            campaign_id=campaign.id,
            template_id=template1.id,
            sent_by_id=test_user.id,
            sent_at=now,
        )
        eq3 = EmailQueue(
            to_email="fail@example.com",
            subject="Welcome Fail",
            body="Welcome!",
            status="failed",
            campaign_id=campaign.id,
            template_id=template1.id,
            sent_by_id=test_user.id,
            error="Bounce",
        )
        db_session.add_all([eq1, eq2, eq3])
        await db_session.commit()
        return campaign

    async def test_analytics_returns_correct_structure(
        self, client: AsyncClient, auth_headers: dict, analytics_campaign
    ):
        """Should return analytics with overall totals and per-step breakdown."""
        campaign = analytics_campaign
        response = await client.get(
            f"/api/campaigns/{campaign.id}/analytics",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        assert data["campaign_id"] == campaign.id
        assert data["total_sent"] == 3
        assert data["total_opened"] == 1
        assert data["total_clicked"] == 0
        assert data["total_failed"] == 1
        assert data["open_rate"] == 33.3
        assert data["click_rate"] == 0.0

        assert len(data["steps"]) == 2

        step1 = data["steps"][0]
        assert step1["step_order"] == 0
        assert step1["template_name"] == "Welcome"
        assert step1["sent"] == 3
        assert step1["opened"] == 1
        assert step1["failed"] == 1

        step2 = data["steps"][1]
        assert step2["step_order"] == 1
        assert step2["template_name"] == "Follow Up"
        assert step2["sent"] == 0
        assert step2["opened"] == 0
        assert step2["open_rate"] == 0.0

    async def test_analytics_no_emails_returns_zeros(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession, test_user: User
    ):
        """Should return all zeros when campaign has no email data."""
        template = EmailTemplate(
            name="Empty Template",
            subject_template="Hello",
            body_template="Body",
            created_by_id=test_user.id,
        )
        db_session.add(template)
        await db_session.flush()

        campaign = Campaign(
            name="Empty Analytics Campaign",
            campaign_type="email",
            status="planned",
            owner_id=test_user.id,
        )
        db_session.add(campaign)
        await db_session.flush()

        step = EmailCampaignStep(
            campaign_id=campaign.id, template_id=template.id,
            delay_days=0, step_order=0,
        )
        db_session.add(step)
        await db_session.commit()

        response = await client.get(
            f"/api/campaigns/{campaign.id}/analytics",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()

        assert data["total_sent"] == 0
        assert data["total_opened"] == 0
        assert data["total_clicked"] == 0
        assert data["total_failed"] == 0
        assert data["open_rate"] == 0.0
        assert data["click_rate"] == 0.0
        assert len(data["steps"]) == 1
        assert data["steps"][0]["sent"] == 0
        assert data["steps"][0]["open_rate"] == 0.0


# =============================================================================
# Unified Activity Timeline
# =============================================================================


class TestUnifiedTimeline:
    """Tests for the unified activity timeline endpoint."""

    async def test_unified_timeline_empty(
        self, client: AsyncClient, auth_headers: dict, test_contact
    ):
        """Should return empty items for entity with no events."""
        response = await client.get(
            f"/api/activities/timeline/unified/contacts/{test_contact.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert isinstance(data["items"], list)

    async def test_unified_timeline_includes_activities(
        self, client: AsyncClient, auth_headers: dict, test_contact, test_activity
    ):
        """Should include activities in the unified timeline."""
        response = await client.get(
            f"/api/activities/timeline/unified/contacts/{test_contact.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        activity_events = [e for e in data["items"] if e["event_type"] == "activity"]
        assert len(activity_events) >= 1

    async def test_unified_timeline_event_structure(
        self, client: AsyncClient, auth_headers: dict, test_contact, test_activity
    ):
        """Should return events with correct structure."""
        response = await client.get(
            f"/api/activities/timeline/unified/contacts/{test_contact.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        if data["items"]:
            event = data["items"][0]
            assert "id" in event
            assert "event_type" in event
            assert "subject" in event
            assert "timestamp" in event
