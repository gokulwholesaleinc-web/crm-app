"""
Unit tests for sales sequence endpoints.

Tests sequence CRUD, enrollment, step processing, pause/resume, and process-due.
"""

import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.contacts.models import Contact
from src.companies.models import Company
from src.sequences.models import Sequence, SequenceEnrollment
from src.sequences.service import SequenceService
from src.campaigns.models import EmailTemplate


@pytest.fixture
async def _seq_email_template(db_session: AsyncSession, test_user: User) -> EmailTemplate:
    """Create an email template for sequence test fixtures."""
    template = EmailTemplate(
        name="Sequence Test Template",
        subject_template="Hello {{first_name}}",
        body_template="<p>Welcome {{full_name}}</p>",
        category="sequence",
        created_by_id=test_user.id,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


@pytest.fixture
async def test_sequence(db_session: AsyncSession, test_user: User, _seq_email_template: EmailTemplate) -> Sequence:
    """Create a test sequence with steps."""
    seq = Sequence(
        name="Onboarding Sequence",
        description="Welcome new contacts",
        steps=[
            {"step_number": 0, "type": "email", "delay_days": 0, "template_id": _seq_email_template.id},
            {"step_number": 1, "type": "wait", "delay_days": 3},
            {"step_number": 2, "type": "task", "delay_days": 0, "task_description": "Follow up call"},
        ],
        is_active=True,
        created_by_id=test_user.id,
    )
    db_session.add(seq)
    await db_session.commit()
    await db_session.refresh(seq)
    return seq


@pytest.fixture
async def test_enrollment(
    db_session: AsyncSession,
    test_sequence: Sequence,
    test_contact: Contact,
) -> SequenceEnrollment:
    """Create a test enrollment."""
    enrollment = SequenceEnrollment(
        sequence_id=test_sequence.id,
        contact_id=test_contact.id,
        current_step=0,
        status="active",
        next_step_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Due now
    )
    db_session.add(enrollment)
    await db_session.commit()
    await db_session.refresh(enrollment)
    return enrollment


class TestSequenceCRUD:
    """Tests for sequence CRUD endpoints."""

    @pytest.mark.asyncio
    async def test_create_sequence(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating a new sequence."""
        response = await client.post(
            "/api/sequences",
            headers=auth_headers,
            json={
                "name": "Welcome Sequence",
                "description": "Welcome new customers",
                "steps": [
                    {"step_number": 0, "type": "email", "delay_days": 0, "template_id": 1},
                    {"step_number": 1, "type": "wait", "delay_days": 2},
                ],
                "is_active": True,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Welcome Sequence"
        assert len(data["steps"]) == 2
        assert data["is_active"] is True

    @pytest.mark.asyncio
    async def test_create_sequence_empty_steps(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test creating sequence with no steps."""
        response = await client.post(
            "/api/sequences",
            headers=auth_headers,
            json={
                "name": "Empty Sequence",
                "steps": [],
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["steps"] == []

    @pytest.mark.asyncio
    async def test_list_sequences(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_sequence: Sequence,
    ):
        """Test listing sequences."""
        response = await client.get(
            "/api/sequences",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_get_sequence(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_sequence: Sequence,
    ):
        """Test getting a sequence by ID."""
        response = await client.get(
            f"/api/sequences/{test_sequence.id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Onboarding Sequence"
        assert len(data["steps"]) == 3

    @pytest.mark.asyncio
    async def test_get_sequence_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test getting non-existent sequence."""
        response = await client.get(
            "/api/sequences/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_sequence(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_sequence: Sequence,
    ):
        """Test updating a sequence."""
        response = await client.put(
            f"/api/sequences/{test_sequence.id}",
            headers=auth_headers,
            json={
                "name": "Updated Sequence",
                "is_active": False,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Sequence"
        assert data["is_active"] is False

    @pytest.mark.asyncio
    async def test_delete_sequence(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
    ):
        """Test deleting a sequence."""
        seq = Sequence(
            name="To Delete",
            steps=[],
            created_by_id=test_user.id,
        )
        db_session.add(seq)
        await db_session.commit()
        await db_session.refresh(seq)

        response = await client.delete(
            f"/api/sequences/{seq.id}",
            headers=auth_headers,
        )
        assert response.status_code == 204


class TestSequenceEnrollment:
    """Tests for sequence enrollment."""

    @pytest.mark.asyncio
    async def test_enroll_contact(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_sequence: Sequence,
        test_contact: Contact,
    ):
        """Test enrolling a contact in a sequence."""
        response = await client.post(
            f"/api/sequences/{test_sequence.id}/enroll",
            headers=auth_headers,
            json={"contact_id": test_contact.id},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sequence_id"] == test_sequence.id
        assert data["contact_id"] == test_contact.id
        assert data["status"] == "active"
        assert data["current_step"] == 0

    @pytest.mark.asyncio
    async def test_enroll_contact_inactive_sequence(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_user: User,
        test_contact: Contact,
    ):
        """Test that enrolling in an inactive sequence returns error."""
        seq = Sequence(
            name="Inactive",
            steps=[],
            is_active=False,
            created_by_id=test_user.id,
        )
        db_session.add(seq)
        await db_session.commit()
        await db_session.refresh(seq)

        response = await client.post(
            f"/api/sequences/{seq.id}/enroll",
            headers=auth_headers,
            json={"contact_id": test_contact.id},
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_enroll_duplicate_returns_existing(
        self,
        db_session: AsyncSession,
        test_sequence: Sequence,
        test_contact: Contact,
    ):
        """Test that enrolling same contact twice returns existing enrollment."""
        service = SequenceService(db_session)

        enrollment1 = await service.enroll_contact(test_sequence.id, test_contact.id)
        enrollment2 = await service.enroll_contact(test_sequence.id, test_contact.id)

        assert enrollment1.id == enrollment2.id

    @pytest.mark.asyncio
    async def test_get_enrollments(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_sequence: Sequence,
        test_enrollment: SequenceEnrollment,
    ):
        """Test getting enrollments for a sequence."""
        response = await client.get(
            f"/api/sequences/{test_sequence.id}/enrollments",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["status"] == "active"


class TestSequenceStepAdvancement:
    """Tests for sequence step processing and advancement."""

    @pytest.mark.asyncio
    async def test_process_due_steps(
        self,
        db_session: AsyncSession,
        test_sequence: Sequence,
        test_enrollment: SequenceEnrollment,
    ):
        """Test processing due enrollment steps."""
        service = SequenceService(db_session)
        results = await service.process_due_steps()

        assert len(results) == 1
        result = results[0]
        assert result["enrollment_id"] == test_enrollment.id
        assert result["step_type"] == "email"
        assert result["status"] == "executed"

        # Check enrollment advanced
        await db_session.refresh(test_enrollment)
        assert test_enrollment.current_step == 1

    @pytest.mark.asyncio
    async def test_process_due_advances_to_completion(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
    ):
        """Test that processing all steps completes the enrollment."""
        # Create a simple 1-step sequence
        seq = Sequence(
            name="One Step",
            steps=[{"step_number": 0, "type": "task", "delay_days": 0, "task_description": "Call"}],
            is_active=True,
            created_by_id=test_user.id,
        )
        db_session.add(seq)
        await db_session.flush()

        enrollment = SequenceEnrollment(
            sequence_id=seq.id,
            contact_id=test_contact.id,
            current_step=0,
            status="active",
            next_step_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(enrollment)
        await db_session.commit()

        service = SequenceService(db_session)
        results = await service.process_due_steps()

        assert len(results) == 1
        assert results[0]["status"] == "completed"

        await db_session.refresh(enrollment)
        assert enrollment.status == "completed"
        assert enrollment.completed_at is not None

    @pytest.mark.asyncio
    async def test_process_due_skips_paused(
        self,
        db_session: AsyncSession,
        test_sequence: Sequence,
        test_contact: Contact,
    ):
        """Test that paused enrollments are not processed."""
        enrollment = SequenceEnrollment(
            sequence_id=test_sequence.id,
            contact_id=test_contact.id,
            current_step=0,
            status="paused",
            next_step_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db_session.add(enrollment)
        await db_session.commit()

        service = SequenceService(db_session)
        results = await service.process_due_steps()

        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_process_due_skips_future(
        self,
        db_session: AsyncSession,
        test_sequence: Sequence,
        test_contact: Contact,
    ):
        """Test that enrollments with future next_step_at are not processed."""
        enrollment = SequenceEnrollment(
            sequence_id=test_sequence.id,
            contact_id=test_contact.id,
            current_step=0,
            status="active",
            next_step_at=datetime.now(timezone.utc) + timedelta(days=5),
        )
        db_session.add(enrollment)
        await db_session.commit()

        service = SequenceService(db_session)
        results = await service.process_due_steps()

        assert len(results) == 0


class TestPauseResume:
    """Tests for pause and resume enrollment."""

    @pytest.mark.asyncio
    async def test_pause_enrollment(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_enrollment: SequenceEnrollment,
    ):
        """Test pausing an active enrollment."""
        response = await client.put(
            f"/api/sequences/enrollments/{test_enrollment.id}/pause",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "paused"

    @pytest.mark.asyncio
    async def test_pause_non_active_fails(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_sequence: Sequence,
        test_contact: Contact,
    ):
        """Test that pausing a non-active enrollment fails."""
        enrollment = SequenceEnrollment(
            sequence_id=test_sequence.id,
            contact_id=test_contact.id,
            status="completed",
        )
        db_session.add(enrollment)
        await db_session.commit()
        await db_session.refresh(enrollment)

        response = await client.put(
            f"/api/sequences/enrollments/{enrollment.id}/pause",
            headers=auth_headers,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_resume_enrollment(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_enrollment: SequenceEnrollment,
    ):
        """Test resuming a paused enrollment."""
        # First pause it
        test_enrollment.status = "paused"
        await db_session.commit()

        response = await client.put(
            f"/api/sequences/enrollments/{test_enrollment.id}/resume",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"

    @pytest.mark.asyncio
    async def test_resume_non_paused_fails(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_enrollment: SequenceEnrollment,
    ):
        """Test that resuming a non-paused enrollment fails."""
        response = await client.put(
            f"/api/sequences/enrollments/{test_enrollment.id}/resume",
            headers=auth_headers,
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_pause_not_found(
        self, client: AsyncClient, db_session: AsyncSession, auth_headers: dict
    ):
        """Test pause on non-existent enrollment."""
        response = await client.put(
            "/api/sequences/enrollments/99999/pause",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestProcessDueEndpoint:
    """Tests for the process-due endpoint."""

    @pytest.mark.asyncio
    async def test_process_due_endpoint(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_enrollment: SequenceEnrollment,
    ):
        """Test the POST /sequences/process-due endpoint."""
        response = await client.post(
            "/api/sequences/process-due",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["processed"] >= 1
        assert len(data["details"]) >= 1


class TestContactEnrollments:
    """Tests for getting enrollments by contact."""

    @pytest.mark.asyncio
    async def test_get_contact_enrollments(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_enrollment: SequenceEnrollment,
        test_contact: Contact,
    ):
        """Test getting enrollments for a contact."""
        response = await client.get(
            f"/api/sequences/contacts/{test_contact.id}/enrollments",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1


class TestSequencesUnauthorized:
    """Tests for unauthorized access."""

    @pytest.mark.asyncio
    async def test_create_sequence_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.post(
            "/api/sequences",
            json={"name": "Test", "steps": []},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_sequences_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        response = await client.get("/api/sequences")
        assert response.status_code == 401
