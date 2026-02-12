"""
Tests for sequence step execution wiring.

Verifies that:
- Email steps actually create EmailQueue entries via EmailService
- Task steps actually create Activity records
- Full enrollment processing flow works end-to-end
"""

import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.contacts.models import Contact
from src.companies.models import Company
from src.sequences.models import Sequence, SequenceEnrollment
from src.sequences.service import SequenceService
from src.email.models import EmailQueue
from src.activities.models import Activity
from src.campaigns.models import EmailTemplate


@pytest.fixture
async def email_template(db_session: AsyncSession, test_user: User) -> EmailTemplate:
    """Create a test email template for sequence email steps."""
    template = EmailTemplate(
        name="Welcome Email",
        subject_template="Welcome {{first_name}}!",
        body_template="<p>Hello {{full_name}}, welcome aboard!</p>",
        category="sequence",
        created_by_id=test_user.id,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)
    return template


@pytest.fixture
async def email_sequence(
    db_session: AsyncSession, test_user: User, email_template: EmailTemplate
) -> Sequence:
    """Create a sequence with an email step linked to a real template."""
    seq = Sequence(
        name="Email Outreach",
        description="Send welcome email",
        steps=[
            {
                "step_number": 0,
                "type": "email",
                "delay_days": 0,
                "template_id": email_template.id,
            },
        ],
        is_active=True,
        created_by_id=test_user.id,
    )
    db_session.add(seq)
    await db_session.commit()
    await db_session.refresh(seq)
    return seq


@pytest.fixture
async def task_sequence(db_session: AsyncSession, test_user: User) -> Sequence:
    """Create a sequence with a task step."""
    seq = Sequence(
        name="Follow-up Tasks",
        description="Create follow-up tasks",
        steps=[
            {
                "step_number": 0,
                "type": "task",
                "delay_days": 0,
                "task_description": "Call the contact to follow up",
            },
        ],
        is_active=True,
        created_by_id=test_user.id,
    )
    db_session.add(seq)
    await db_session.commit()
    await db_session.refresh(seq)
    return seq


@pytest.fixture
async def multi_step_sequence(
    db_session: AsyncSession, test_user: User, email_template: EmailTemplate
) -> Sequence:
    """Create a sequence with email, wait, and task steps."""
    seq = Sequence(
        name="Full Onboarding",
        description="Complete onboarding flow",
        steps=[
            {
                "step_number": 0,
                "type": "email",
                "delay_days": 0,
                "template_id": email_template.id,
            },
            {
                "step_number": 1,
                "type": "wait",
                "delay_days": 0,
            },
            {
                "step_number": 2,
                "type": "task",
                "delay_days": 0,
                "task_description": "Schedule demo call",
            },
        ],
        is_active=True,
        created_by_id=test_user.id,
    )
    db_session.add(seq)
    await db_session.commit()
    await db_session.refresh(seq)
    return seq


def _create_due_enrollment(
    sequence: Sequence, contact: Contact
) -> SequenceEnrollment:
    """Create an enrollment that is due for processing."""
    return SequenceEnrollment(
        sequence_id=sequence.id,
        contact_id=contact.id,
        current_step=0,
        status="active",
        next_step_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )


class TestEmailStepWiring:
    """Verify that email steps actually create EmailQueue entries."""

    @pytest.mark.asyncio
    async def test_email_step_creates_email_queue_entry(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
        email_sequence: Sequence,
    ):
        """Email step should create an EmailQueue record via EmailService."""
        enrollment = _create_due_enrollment(email_sequence, test_contact)
        db_session.add(enrollment)
        await db_session.commit()

        service = SequenceService(db_session)
        results = await service.process_due_steps()

        assert len(results) == 1
        result = results[0]
        assert result["action"] == "email_queued"
        assert "email_queue_id" in result

        # Verify the EmailQueue record exists in the database
        eq_result = await db_session.execute(
            select(EmailQueue).where(EmailQueue.id == result["email_queue_id"])
        )
        email_record = eq_result.scalar_one_or_none()
        assert email_record is not None
        assert email_record.to_email == test_contact.email
        assert email_record.entity_type == "contacts"
        assert email_record.entity_id == test_contact.id
        assert "Welcome John" in email_record.subject

    @pytest.mark.asyncio
    async def test_email_step_renders_template_variables(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
        email_sequence: Sequence,
    ):
        """Email step should render template variables from contact data."""
        enrollment = _create_due_enrollment(email_sequence, test_contact)
        db_session.add(enrollment)
        await db_session.commit()

        service = SequenceService(db_session)
        await service.process_due_steps()

        eq_result = await db_session.execute(
            select(EmailQueue).where(
                EmailQueue.entity_type == "contacts",
                EmailQueue.entity_id == test_contact.id,
            )
        )
        email_record = eq_result.scalar_one()
        assert test_contact.full_name in email_record.body

    @pytest.mark.asyncio
    async def test_email_step_without_contact_email_skips_send(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_company: Company,
        email_sequence: Sequence,
    ):
        """If contact has no email, no EmailQueue entry should be created."""
        contact_no_email = Contact(
            first_name="NoEmail",
            last_name="Person",
            email=None,
            company_id=test_company.id,
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(contact_no_email)
        await db_session.flush()

        enrollment = _create_due_enrollment(email_sequence, contact_no_email)
        db_session.add(enrollment)
        await db_session.commit()

        service = SequenceService(db_session)
        results = await service.process_due_steps()

        assert len(results) == 1
        result = results[0]
        assert result["action"] == "email_queued"
        assert "email_queue_id" not in result

        # No EmailQueue records should exist
        eq_result = await db_session.execute(select(EmailQueue))
        assert eq_result.scalar_one_or_none() is None


class TestTaskStepWiring:
    """Verify that task steps actually create Activity records."""

    @pytest.mark.asyncio
    async def test_task_step_creates_activity_record(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
        task_sequence: Sequence,
    ):
        """Task step should create an Activity record in the database."""
        enrollment = _create_due_enrollment(task_sequence, test_contact)
        db_session.add(enrollment)
        await db_session.commit()

        service = SequenceService(db_session)
        results = await service.process_due_steps()

        assert len(results) == 1
        result = results[0]
        assert result["action"] == "task_created"
        assert "activity_id" in result

        # Verify the Activity record exists in the database
        act_result = await db_session.execute(
            select(Activity).where(Activity.id == result["activity_id"])
        )
        activity = act_result.scalar_one_or_none()
        assert activity is not None
        assert activity.activity_type == "task"
        assert activity.subject == "Call the contact to follow up"
        assert activity.entity_type == "contacts"
        assert activity.entity_id == test_contact.id
        assert activity.is_completed is False

    @pytest.mark.asyncio
    async def test_task_step_assigns_to_contact_owner(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
        task_sequence: Sequence,
    ):
        """Task step should assign the activity to the contact's owner."""
        enrollment = _create_due_enrollment(task_sequence, test_contact)
        db_session.add(enrollment)
        await db_session.commit()

        service = SequenceService(db_session)
        results = await service.process_due_steps()

        act_result = await db_session.execute(
            select(Activity).where(Activity.id == results[0]["activity_id"])
        )
        activity = act_result.scalar_one()
        assert activity.assigned_to_id == test_contact.owner_id
        assert activity.owner_id == task_sequence.created_by_id

    @pytest.mark.asyncio
    async def test_task_step_includes_sequence_info_in_description(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
        task_sequence: Sequence,
    ):
        """Task activity description should reference the sequence and step."""
        enrollment = _create_due_enrollment(task_sequence, test_contact)
        db_session.add(enrollment)
        await db_session.commit()

        service = SequenceService(db_session)
        results = await service.process_due_steps()

        act_result = await db_session.execute(
            select(Activity).where(Activity.id == results[0]["activity_id"])
        )
        activity = act_result.scalar_one()
        assert task_sequence.name in activity.description
        assert "step 0" in activity.description


class TestEndToEndSequenceFlow:
    """Test the full enrollment processing flow from enrollment to completion."""

    @pytest.mark.asyncio
    async def test_multi_step_sequence_creates_all_records(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
        multi_step_sequence: Sequence,
    ):
        """Processing a multi-step sequence should create email and task records."""
        enrollment = _create_due_enrollment(multi_step_sequence, test_contact)
        db_session.add(enrollment)
        await db_session.commit()

        service = SequenceService(db_session)

        # Step 0: email
        results = await service.process_due_steps()
        assert len(results) == 1
        assert results[0]["step_type"] == "email"
        assert "email_queue_id" in results[0]

        # Advance enrollment to be due again for step 1
        await db_session.refresh(enrollment)
        enrollment.next_step_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await db_session.commit()

        # Step 1: wait
        results = await service.process_due_steps()
        assert len(results) == 1
        assert results[0]["step_type"] == "wait"
        assert results[0]["action"] == "wait_completed"

        # Advance enrollment to be due again for step 2
        await db_session.refresh(enrollment)
        enrollment.next_step_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await db_session.commit()

        # Step 2: task (final step)
        results = await service.process_due_steps()
        assert len(results) == 1
        assert results[0]["step_type"] == "task"
        assert "activity_id" in results[0]
        assert results[0]["status"] == "completed"

        # Verify enrollment is completed
        await db_session.refresh(enrollment)
        assert enrollment.status == "completed"
        assert enrollment.completed_at is not None

        # Verify one EmailQueue and one Activity were created
        eq_count = await db_session.execute(select(EmailQueue))
        assert len(eq_count.scalars().all()) == 1

        act_count = await db_session.execute(
            select(Activity).where(Activity.activity_type == "task")
        )
        assert len(act_count.scalars().all()) == 1

    @pytest.mark.asyncio
    async def test_enrollment_advances_step_index_correctly(
        self,
        db_session: AsyncSession,
        test_user: User,
        test_contact: Contact,
        multi_step_sequence: Sequence,
    ):
        """Each process_due_steps call should advance current_step by 1."""
        enrollment = _create_due_enrollment(multi_step_sequence, test_contact)
        db_session.add(enrollment)
        await db_session.commit()

        service = SequenceService(db_session)

        # Process step 0
        await service.process_due_steps()
        await db_session.refresh(enrollment)
        assert enrollment.current_step == 1

        # Process step 1
        enrollment.next_step_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await db_session.commit()
        await service.process_due_steps()
        await db_session.refresh(enrollment)
        assert enrollment.current_step == 2

        # Process step 2 (final)
        enrollment.next_step_at = datetime.now(timezone.utc) - timedelta(hours=1)
        await db_session.commit()
        await service.process_due_steps()
        await db_session.refresh(enrollment)
        assert enrollment.current_step == 3
        assert enrollment.status == "completed"
