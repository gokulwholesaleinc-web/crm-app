"""Sales sequence service layer."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Tuple, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.sequences.models import Sequence, SequenceEnrollment
from src.sequences.schemas import SequenceCreate, SequenceUpdate
from src.core.base_service import BaseService
from src.core.constants import DEFAULT_PAGE_SIZE

logger = logging.getLogger(__name__)


class SequenceService(BaseService[Sequence]):
    """Service for Sequence CRUD and enrollment management."""

    model = Sequence

    async def get_list(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        is_active: Optional[bool] = None,
    ) -> Tuple[List[Sequence], int]:
        """Get paginated list of sequences."""
        query = select(Sequence)

        if is_active is not None:
            query = query.where(Sequence.is_active == is_active)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Sequence.created_at.desc())

        result = await self.db.execute(query)
        sequences = list(result.scalars().all())
        return sequences, total

    async def create_sequence(self, data: SequenceCreate, user_id: int) -> Sequence:
        """Create a new sequence."""
        steps_data = [s.model_dump() for s in data.steps] if data.steps else []
        seq = Sequence(
            name=data.name,
            description=data.description,
            steps=steps_data,
            is_active=data.is_active,
            created_by_id=user_id,
        )
        self.db.add(seq)
        await self.db.flush()
        await self.db.refresh(seq)
        return seq

    async def update_sequence(self, seq: Sequence, data: SequenceUpdate) -> Sequence:
        """Update a sequence."""
        update_data = data.model_dump(exclude_unset=True)
        if "steps" in update_data and update_data["steps"] is not None:
            update_data["steps"] = [s if isinstance(s, dict) else s.model_dump() for s in update_data["steps"]]
        for field, value in update_data.items():
            setattr(seq, field, value)
        await self.db.flush()
        await self.db.refresh(seq)
        return seq

    async def delete_sequence(self, seq: Sequence) -> None:
        """Delete a sequence."""
        await self.db.delete(seq)
        await self.db.flush()

    async def enroll_contact(self, sequence_id: int, contact_id: int) -> SequenceEnrollment:
        """Enroll a contact in a sequence."""
        # Check if already enrolled and active
        result = await self.db.execute(
            select(SequenceEnrollment).where(
                SequenceEnrollment.sequence_id == sequence_id,
                SequenceEnrollment.contact_id == contact_id,
                SequenceEnrollment.status == "active",
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        # Get sequence to determine first step timing
        seq = await self.get_by_id(sequence_id)
        next_step_at = datetime.now(timezone.utc)
        if seq and seq.steps:
            first_step = seq.steps[0]
            delay_days = first_step.get("delay_days", 0)
            next_step_at = datetime.now(timezone.utc) + timedelta(days=delay_days)

        enrollment = SequenceEnrollment(
            sequence_id=sequence_id,
            contact_id=contact_id,
            current_step=0,
            status="active",
            next_step_at=next_step_at,
        )
        self.db.add(enrollment)
        await self.db.flush()
        await self.db.refresh(enrollment)
        return enrollment

    async def pause_enrollment(self, enrollment_id: int) -> Optional[SequenceEnrollment]:
        """Pause an enrollment."""
        result = await self.db.execute(
            select(SequenceEnrollment).where(SequenceEnrollment.id == enrollment_id)
        )
        enrollment = result.scalar_one_or_none()
        if not enrollment or enrollment.status != "active":
            return enrollment
        enrollment.status = "paused"
        await self.db.flush()
        await self.db.refresh(enrollment)
        return enrollment

    async def resume_enrollment(self, enrollment_id: int) -> Optional[SequenceEnrollment]:
        """Resume a paused enrollment."""
        result = await self.db.execute(
            select(SequenceEnrollment).where(SequenceEnrollment.id == enrollment_id)
        )
        enrollment = result.scalar_one_or_none()
        if not enrollment or enrollment.status != "paused":
            return enrollment
        enrollment.status = "active"
        # Reset next_step_at to now so the step can be processed
        enrollment.next_step_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(enrollment)
        return enrollment

    async def get_enrollments(
        self,
        sequence_id: int,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> Tuple[List[SequenceEnrollment], int]:
        """Get enrollments for a sequence."""
        query = select(SequenceEnrollment).where(
            SequenceEnrollment.sequence_id == sequence_id
        )

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(
            SequenceEnrollment.started_at.desc()
        )

        result = await self.db.execute(query)
        enrollments = list(result.scalars().all())
        return enrollments, total

    async def get_enrollment_by_id(self, enrollment_id: int) -> Optional[SequenceEnrollment]:
        """Get a single enrollment by ID."""
        result = await self.db.execute(
            select(SequenceEnrollment).where(SequenceEnrollment.id == enrollment_id)
        )
        return result.scalar_one_or_none()

    async def get_contact_enrollments(self, contact_id: int) -> List[SequenceEnrollment]:
        """Get all enrollments for a contact."""
        result = await self.db.execute(
            select(SequenceEnrollment).where(
                SequenceEnrollment.contact_id == contact_id
            ).order_by(SequenceEnrollment.started_at.desc())
        )
        return list(result.scalars().all())

    async def process_due_steps(self) -> List[Dict[str, Any]]:
        """Process all enrollments with due steps.

        Finds enrollments where next_step_at <= now and status == active,
        executes the current step, and advances to the next.
        """
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(SequenceEnrollment).where(
                SequenceEnrollment.status == "active",
                SequenceEnrollment.next_step_at <= now,
            )
        )
        due_enrollments = list(result.scalars().all())

        processed = []
        for enrollment in due_enrollments:
            try:
                step_result = await self._execute_step(enrollment)
                processed.append(step_result)
            except Exception as e:
                logger.error(
                    "Failed to process step for enrollment %s: %s",
                    enrollment.id, e,
                )
                processed.append({
                    "enrollment_id": enrollment.id,
                    "status": "error",
                    "error": str(e),
                })

        await self.db.flush()
        return processed

    async def _execute_step(self, enrollment: SequenceEnrollment) -> Dict[str, Any]:
        """Execute the current step for an enrollment and advance."""
        seq = await self.get_by_id(enrollment.sequence_id)
        if not seq or not seq.steps:
            enrollment.status = "completed"
            enrollment.completed_at = datetime.now(timezone.utc)
            return {
                "enrollment_id": enrollment.id,
                "status": "completed",
                "reason": "no_steps",
            }

        steps = seq.steps
        current_step_index = enrollment.current_step

        if current_step_index >= len(steps):
            enrollment.status = "completed"
            enrollment.completed_at = datetime.now(timezone.utc)
            return {
                "enrollment_id": enrollment.id,
                "status": "completed",
                "reason": "all_steps_done",
            }

        step = steps[current_step_index]
        step_type = step.get("type", "wait")

        result = {
            "enrollment_id": enrollment.id,
            "step_number": current_step_index,
            "step_type": step_type,
            "status": "executed",
        }

        if step_type == "email":
            result["action"] = "email_queued"
            result["template_id"] = step.get("template_id")
        elif step_type == "task":
            result["action"] = "task_created"
            result["task_description"] = step.get("task_description")
        elif step_type == "wait":
            result["action"] = "wait_completed"

        # Advance to next step
        next_step_index = current_step_index + 1
        enrollment.current_step = next_step_index

        if next_step_index >= len(steps):
            enrollment.status = "completed"
            enrollment.completed_at = datetime.now(timezone.utc)
            result["status"] = "completed"
        else:
            next_step = steps[next_step_index]
            delay_days = next_step.get("delay_days", 0)
            enrollment.next_step_at = datetime.now(timezone.utc) + timedelta(days=delay_days)

        return result
