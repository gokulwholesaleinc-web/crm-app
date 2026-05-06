"""
Cascade tests for lead → contact conversion.

Verify that when a lead is converted to a contact, the lead's tags,
activities, notes, and sales_code follow it onto the new contact instead
of being silently orphaned on the lead tombstone.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.activities.models import Activity
from src.auth.models import User
from src.contacts.models import Contact
from src.core.models import EntityTag, Note, Tag
from src.leads.conversion import LeadConverter
from src.leads.models import Lead


async def _make_lead(db_session: AsyncSession, owner: User, **overrides) -> Lead:
    defaults = dict(
        first_name="Cascade",
        last_name="Lead",
        email="cascade.lead@example.com",
        status="qualified",
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    defaults.update(overrides)
    lead = Lead(**defaults)
    db_session.add(lead)
    await db_session.commit()
    await db_session.refresh(lead)
    return lead


class TestLeadConversionCascade:
    """Cascading lead-attached records onto the new contact."""

    @pytest.mark.asyncio
    async def test_conversion_relinks_tags(
        self, db_session: AsyncSession, test_user: User
    ):
        """Tags on the lead must appear on the new contact, deduped."""
        lead = await _make_lead(db_session, test_user)

        tag_a = Tag(name="hot")
        tag_b = Tag(name="enterprise")
        db_session.add_all([tag_a, tag_b])
        await db_session.commit()
        await db_session.refresh(tag_a)
        await db_session.refresh(tag_b)

        db_session.add_all([
            EntityTag(tag_id=tag_a.id, entity_type="leads", entity_id=lead.id),
            EntityTag(tag_id=tag_b.id, entity_type="leads", entity_id=lead.id),
        ])
        await db_session.commit()

        converter = LeadConverter(db_session)
        contact, _ = await converter.convert_to_contact(
            lead=lead, user_id=test_user.id, create_company=False
        )
        await db_session.commit()

        result = await db_session.execute(
            select(EntityTag.tag_id).where(
                EntityTag.entity_type == "contacts",
                EntityTag.entity_id == contact.id,
            )
        )
        contact_tag_ids = {row[0] for row in result.all()}
        assert contact_tag_ids == {tag_a.id, tag_b.id}

    @pytest.mark.asyncio
    async def test_conversion_relinks_tags_skips_duplicates(
        self, db_session: AsyncSession, test_user: User
    ):
        """If the contact already has a tag, conversion must not double-insert."""
        lead = await _make_lead(db_session, test_user, email="dup.tag@example.com")

        tag = Tag(name="vip")
        db_session.add(tag)
        await db_session.commit()
        await db_session.refresh(tag)

        # Manually create the contact ahead of conversion to simulate the
        # rare race where a tag was already attached to a freshly-created
        # contact. The cascade path doesn't create such state today, so we
        # exercise the dedupe by attaching to a placeholder contact and
        # passing it through the helper directly.
        placeholder = Contact(
            first_name="Dup",
            last_name="Contact",
            email="dup.tag.contact@example.com",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(placeholder)
        await db_session.commit()
        await db_session.refresh(placeholder)

        db_session.add_all([
            EntityTag(tag_id=tag.id, entity_type="leads", entity_id=lead.id),
            EntityTag(tag_id=tag.id, entity_type="contacts", entity_id=placeholder.id),
        ])
        await db_session.commit()

        converter = LeadConverter(db_session)
        await converter._relink_tags(lead.id, placeholder.id)
        await db_session.commit()

        result = await db_session.execute(
            select(EntityTag).where(
                EntityTag.entity_type == "contacts",
                EntityTag.entity_id == placeholder.id,
                EntityTag.tag_id == tag.id,
            )
        )
        rows = result.scalars().all()
        assert len(rows) == 1, "duplicate tag insert leaked through"

    @pytest.mark.asyncio
    async def test_conversion_relinks_activities(
        self, db_session: AsyncSession, test_user: User
    ):
        """Activities pointed at the lead must be re-pointed at the contact."""
        lead = await _make_lead(
            db_session, test_user, email="cascade.act@example.com"
        )

        a1 = Activity(
            activity_type="call",
            subject="Discovery call",
            entity_type="leads",
            entity_id=lead.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        a2 = Activity(
            activity_type="email",
            subject="Follow-up",
            entity_type="leads",
            entity_id=lead.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add_all([a1, a2])
        await db_session.commit()

        converter = LeadConverter(db_session)
        contact, _ = await converter.convert_to_contact(
            lead=lead, user_id=test_user.id, create_company=False
        )
        await db_session.commit()

        result = await db_session.execute(
            select(Activity).where(
                Activity.entity_type == "contacts",
                Activity.entity_id == contact.id,
            )
        )
        moved = result.scalars().all()
        assert len(moved) == 2
        assert {a.subject for a in moved} == {"Discovery call", "Follow-up"}

        # Lead-pointing rows should be gone (move, not duplicate)
        result = await db_session.execute(
            select(Activity).where(
                Activity.entity_type == "leads",
                Activity.entity_id == lead.id,
            )
        )
        assert result.scalars().all() == []

    @pytest.mark.asyncio
    async def test_conversion_relinks_notes(
        self, db_session: AsyncSession, test_user: User
    ):
        """Notes attached to the lead must move to the contact."""
        lead = await _make_lead(
            db_session, test_user, email="cascade.note@example.com"
        )

        n1 = Note(
            content="Initial intake notes",
            entity_type="leads",
            entity_id=lead.id,
            created_by_id=test_user.id,
        )
        n2 = Note(
            content="Budget confirmed by CFO",
            entity_type="leads",
            entity_id=lead.id,
            created_by_id=test_user.id,
        )
        db_session.add_all([n1, n2])
        await db_session.commit()

        converter = LeadConverter(db_session)
        contact, _ = await converter.convert_to_contact(
            lead=lead, user_id=test_user.id, create_company=False
        )
        await db_session.commit()

        result = await db_session.execute(
            select(Note).where(
                Note.entity_type == "contacts",
                Note.entity_id == contact.id,
            )
        )
        moved = result.scalars().all()
        assert len(moved) == 2
        assert {n.content for n in moved} == {
            "Initial intake notes",
            "Budget confirmed by CFO",
        }

        result = await db_session.execute(
            select(Note).where(
                Note.entity_type == "leads",
                Note.entity_id == lead.id,
            )
        )
        assert result.scalars().all() == []

    @pytest.mark.asyncio
    async def test_conversion_copies_sales_code(
        self, db_session: AsyncSession, test_user: User
    ):
        """sales_code on the lead must be copied onto the new contact."""
        lead = await _make_lead(
            db_session,
            test_user,
            email="cascade.sales@example.com",
            sales_code="REP-42",
        )

        converter = LeadConverter(db_session)
        contact, _ = await converter.convert_to_contact(
            lead=lead, user_id=test_user.id, create_company=False
        )
        await db_session.commit()
        await db_session.refresh(contact)

        assert contact.sales_code == "REP-42"
