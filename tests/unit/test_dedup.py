"""
Unit tests for duplicate detection and merge endpoints.

Tests for contact dedup (email, phone, name match), company dedup (name match),
merge operations, and no-false-positive verification.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.auth.models import User
from src.contacts.models import Contact
from src.companies.models import Company
from src.leads.models import Lead
from src.activities.models import Activity
from src.core.models import Note


class TestDedupCheckContacts:
    """Tests for contact duplicate detection."""

    @pytest.mark.asyncio
    async def test_check_duplicate_contact_email_match(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test that duplicate check finds contacts by matching email."""
        response = await client.post(
            "/api/dedup/check",
            headers=auth_headers,
            json={
                "entity_type": "contacts",
                "data": {"email": test_contact.email},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_duplicates"] is True
        assert len(data["duplicates"]) >= 1
        assert any(d["id"] == test_contact.id for d in data["duplicates"])
        assert any("Email match" in d["match_reason"] for d in data["duplicates"])

    @pytest.mark.asyncio
    async def test_check_duplicate_contact_phone_match(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test that duplicate check finds contacts by matching phone."""
        response = await client.post(
            "/api/dedup/check",
            headers=auth_headers,
            json={
                "entity_type": "contacts",
                "data": {"phone": test_contact.phone},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_duplicates"] is True
        assert len(data["duplicates"]) >= 1
        assert any("Phone match" in d["match_reason"] for d in data["duplicates"])

    @pytest.mark.asyncio
    async def test_check_duplicate_contact_name_match(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test that duplicate check finds contacts by matching first and last name."""
        response = await client.post(
            "/api/dedup/check",
            headers=auth_headers,
            json={
                "entity_type": "contacts",
                "data": {
                    "first_name": test_contact.first_name,
                    "last_name": test_contact.last_name,
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_duplicates"] is True
        assert any("Name match" in d["match_reason"] for d in data["duplicates"])

    @pytest.mark.asyncio
    async def test_check_no_duplicate_contact(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test that no false positives when checking unique data."""
        response = await client.post(
            "/api/dedup/check",
            headers=auth_headers,
            json={
                "entity_type": "contacts",
                "data": {
                    "email": "unique_person_99999@example.com",
                    "first_name": "UniqueFirst",
                    "last_name": "UniqueLast",
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_duplicates"] is False
        assert data["duplicates"] == []

    @pytest.mark.asyncio
    async def test_check_duplicate_contact_case_insensitive_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_contact: Contact,
    ):
        """Test that email matching is case insensitive."""
        response = await client.post(
            "/api/dedup/check",
            headers=auth_headers,
            json={
                "entity_type": "contacts",
                "data": {"email": test_contact.email.upper()},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_duplicates"] is True


class TestDedupCheckCompanies:
    """Tests for company duplicate detection."""

    @pytest.mark.asyncio
    async def test_check_duplicate_company_name_match(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Test that duplicate check finds companies by normalized name."""
        response = await client.post(
            "/api/dedup/check",
            headers=auth_headers,
            json={
                "entity_type": "companies",
                "data": {"name": test_company.name},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_duplicates"] is True
        assert len(data["duplicates"]) >= 1

    @pytest.mark.asyncio
    async def test_check_duplicate_company_suffix_normalization(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_company: Company,
    ):
        """Test that company name matching strips suffixes like Inc, LLC, etc."""
        # test_company.name is "Test Company Inc"
        # Searching for "Test Company" should still match
        response = await client.post(
            "/api/dedup/check",
            headers=auth_headers,
            json={
                "entity_type": "companies",
                "data": {"name": "Test Company"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_duplicates"] is True

    @pytest.mark.asyncio
    async def test_check_no_duplicate_company(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test no false positives for unique company names."""
        response = await client.post(
            "/api/dedup/check",
            headers=auth_headers,
            json={
                "entity_type": "companies",
                "data": {"name": "Completely Unique Corporation XYZ 99999"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_duplicates"] is False


class TestDedupCheckLeads:
    """Tests for lead duplicate detection."""

    @pytest.mark.asyncio
    async def test_check_duplicate_lead_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
        test_lead: Lead,
    ):
        """Test that duplicate check finds leads by email."""
        response = await client.post(
            "/api/dedup/check",
            headers=auth_headers,
            json={
                "entity_type": "leads",
                "data": {"email": test_lead.email},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_duplicates"] is True
        assert any("Email match" in d["match_reason"] for d in data["duplicates"])

    @pytest.mark.asyncio
    async def test_check_no_duplicate_lead(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test no false positives for unique lead data."""
        response = await client.post(
            "/api/dedup/check",
            headers=auth_headers,
            json={
                "entity_type": "leads",
                "data": {"email": "absolutely_unique_lead_99999@example.com"},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_duplicates"] is False


class TestDedupCheckValidation:
    """Tests for dedup endpoint validation."""

    @pytest.mark.asyncio
    async def test_check_invalid_entity_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
    ):
        """Test that invalid entity type returns 400."""
        response = await client.post(
            "/api/dedup/check",
            headers=auth_headers,
            json={
                "entity_type": "invalid_type",
                "data": {"email": "test@example.com"},
            },
        )

        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_check_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test dedup check without auth returns 401."""
        response = await client.post(
            "/api/dedup/check",
            json={
                "entity_type": "contacts",
                "data": {"email": "test@example.com"},
            },
        )

        assert response.status_code == 401


class TestMergeContacts:
    """Tests for contact merge endpoint."""

    @pytest.mark.asyncio
    async def test_merge_contacts_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_user: User,
    ):
        """Test successful merge of two contacts."""
        # Create primary and secondary contacts
        primary = Contact(
            first_name="Primary",
            last_name="Contact",
            email="primary@example.com",
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        secondary = Contact(
            first_name="Secondary",
            last_name="Contact",
            email="secondary@example.com",
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add_all([primary, secondary])
        await db_session.commit()
        await db_session.refresh(primary)
        await db_session.refresh(secondary)

        response = await client.post(
            "/api/dedup/merge",
            headers=admin_auth_headers,
            json={
                "entity_type": "contacts",
                "primary_id": primary.id,
                "secondary_id": secondary.id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["primary_id"] == primary.id
        assert "merged" in data["message"].lower()

        # Contacts are soft-deleted on merge (deleted_at set, merged_into_id
        # points at primary) — the "never delete contacts" rule means the row
        # stays in the table so AR history and activities remain linkable.
        result = await db_session.execute(
            select(Contact).where(Contact.id == secondary.id)
        )
        merged = result.scalar_one_or_none()
        assert merged is not None
        assert merged.deleted_at is not None
        assert merged.merged_into_id == primary.id

    @pytest.mark.asyncio
    async def test_merge_contacts_transfers_activities(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_user: User,
    ):
        """Test that merge transfers activities from secondary to primary."""
        primary = Contact(
            first_name="Primary",
            last_name="WithAct",
            email="primary_act@example.com",
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        secondary = Contact(
            first_name="Secondary",
            last_name="WithAct",
            email="secondary_act@example.com",
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add_all([primary, secondary])
        await db_session.commit()
        await db_session.refresh(primary)
        await db_session.refresh(secondary)

        # Create activity linked to secondary
        from datetime import datetime, timezone
        activity = Activity(
            activity_type="call",
            subject="Call from secondary",
            entity_type="contacts",
            entity_id=secondary.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(activity)
        await db_session.commit()
        await db_session.refresh(activity)

        response = await client.post(
            "/api/dedup/merge",
            headers=admin_auth_headers,
            json={
                "entity_type": "contacts",
                "primary_id": primary.id,
                "secondary_id": secondary.id,
            },
        )

        assert response.status_code == 200

        # Verify activity was transferred to primary
        await db_session.refresh(activity)
        assert activity.entity_id == primary.id

    @pytest.mark.asyncio
    async def test_merge_contacts_transfers_notes(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_user: User,
    ):
        """Test that merge transfers notes from secondary to primary."""
        primary = Contact(
            first_name="PrimaryNote",
            last_name="Contact",
            email="primary_note@example.com",
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        secondary = Contact(
            first_name="SecondaryNote",
            last_name="Contact",
            email="secondary_note@example.com",
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add_all([primary, secondary])
        await db_session.commit()
        await db_session.refresh(primary)
        await db_session.refresh(secondary)

        # Create note linked to secondary
        note = Note(
            content="Note from secondary",
            entity_type="contacts",
            entity_id=secondary.id,
            created_by_id=test_user.id,
        )
        db_session.add(note)
        await db_session.commit()
        await db_session.refresh(note)

        await client.post(
            "/api/dedup/merge",
            headers=admin_auth_headers,
            json={
                "entity_type": "contacts",
                "primary_id": primary.id,
                "secondary_id": secondary.id,
            },
        )

        # Verify note was transferred
        await db_session.refresh(note)
        assert note.entity_id == primary.id

    @pytest.mark.asyncio
    async def test_merge_same_id_fails(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        """Test that merging an entity with itself fails."""
        response = await client.post(
            "/api/dedup/merge",
            headers=admin_auth_headers,
            json={
                "entity_type": "contacts",
                "primary_id": 1,
                "secondary_id": 1,
            },
        )

        assert response.status_code == 400
        assert "different" in response.json()["detail"].lower()


class TestMergeCompanies:
    """Tests for company merge endpoint."""

    @pytest.mark.asyncio
    async def test_merge_companies_success(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_user: User,
    ):
        """Test successful company merge."""
        primary = Company(
            name="Primary Corp",
            status="prospect",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        secondary = Company(
            name="Secondary Corp",
            status="prospect",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add_all([primary, secondary])
        await db_session.commit()
        await db_session.refresh(primary)
        await db_session.refresh(secondary)

        response = await client.post(
            "/api/dedup/merge",
            headers=admin_auth_headers,
            json={
                "entity_type": "companies",
                "primary_id": primary.id,
                "secondary_id": secondary.id,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_merge_companies_transfers_contacts(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_user: User,
    ):
        """Test that company merge moves contacts from secondary to primary."""
        primary = Company(
            name="Primary Co Transfer",
            status="prospect",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        secondary = Company(
            name="Secondary Co Transfer",
            status="prospect",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add_all([primary, secondary])
        await db_session.commit()
        await db_session.refresh(primary)
        await db_session.refresh(secondary)

        # Create contact under secondary company
        contact = Contact(
            first_name="Orphan",
            last_name="Contact",
            email="orphan@example.com",
            company_id=secondary.id,
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(contact)
        await db_session.commit()
        await db_session.refresh(contact)

        await client.post(
            "/api/dedup/merge",
            headers=admin_auth_headers,
            json={
                "entity_type": "companies",
                "primary_id": primary.id,
                "secondary_id": secondary.id,
            },
        )

        # Verify contact was transferred
        await db_session.refresh(contact)
        assert contact.company_id == primary.id


class TestMergeUnauthorized:
    """Tests for unauthorized merge access."""

    @pytest.mark.asyncio
    async def test_merge_unauthorized(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Test merge without auth returns 401."""
        response = await client.post(
            "/api/dedup/merge",
            json={
                "entity_type": "contacts",
                "primary_id": 1,
                "secondary_id": 2,
            },
        )

        assert response.status_code == 401


class TestDedupMergeSoftDelete:
    """Service-level tests for the Session 3 dedup soft-delete + FK transfer.

    These exercise ``DedupService`` directly to avoid the manager-role
    gate on the ``/api/dedup/merge`` router, so they cover both the
    legacy regular-user path and the fix regardless of RBAC changes.
    """

    @pytest.mark.asyncio
    async def test_merge_contacts_soft_deletes_secondary(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Secondary contact must be soft-deleted, not dropped from the table."""
        from src.dedup.service import DedupService

        primary = Contact(
            first_name="Primary",
            last_name="SoftMerge",
            email="primary.soft@example.com",
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        secondary = Contact(
            first_name="Secondary",
            last_name="SoftMerge",
            email="secondary.soft@example.com",
            status="active",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add_all([primary, secondary])
        await db_session.commit()
        await db_session.refresh(primary)
        await db_session.refresh(secondary)

        await DedupService(db_session).merge_contacts(
            primary.id, secondary.id, user_id=test_user.id
        )
        await db_session.commit()

        # Secondary row MUST still exist — project rule forbids hard delete.
        row = await db_session.execute(
            select(Contact).where(Contact.id == secondary.id)
        )
        archived = row.scalar_one_or_none()
        assert archived is not None
        assert archived.status == "merged"
        assert archived.deleted_at is not None
        assert archived.merged_into_id == primary.id
        # Email slot must be released so the address can be reused.
        assert archived.email != "secondary.soft@example.com"

    @pytest.mark.asyncio
    async def test_merge_contacts_transfers_quote_fk(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Quotes pointing at the secondary contact must follow the merge."""
        from src.dedup.service import DedupService
        from src.quotes.models import Quote

        primary = Contact(
            first_name="Q", last_name="Primary",
            email="qprimary@example.com",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        secondary = Contact(
            first_name="Q", last_name="Secondary",
            email="qsecondary@example.com",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        db_session.add_all([primary, secondary])
        await db_session.commit()
        await db_session.refresh(primary)
        await db_session.refresh(secondary)

        quote = Quote(
            quote_number="Q-MERGE-1",
            title="Merge test",
            contact_id=secondary.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
            subtotal=0, tax_rate=0, tax_amount=0, total=0,
        )
        db_session.add(quote)
        await db_session.commit()
        await db_session.refresh(quote)

        await DedupService(db_session).merge_contacts(
            primary.id, secondary.id, user_id=test_user.id
        )
        await db_session.commit()
        await db_session.refresh(quote)

        assert quote.contact_id == primary.id

    @pytest.mark.asyncio
    async def test_merge_contacts_transfers_notes_and_audit(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Notes + audit log entry must be written when merging."""
        from src.dedup.service import DedupService
        from src.audit.models import AuditLog

        primary = Contact(
            first_name="NotePrimary", last_name="X",
            email="note.primary@example.com",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        secondary = Contact(
            first_name="NoteSecondary", last_name="X",
            email="note.secondary@example.com",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        db_session.add_all([primary, secondary])
        await db_session.commit()
        await db_session.refresh(primary)
        await db_session.refresh(secondary)

        note = Note(
            content="Secondary note",
            entity_type="contacts",
            entity_id=secondary.id,
            created_by_id=test_user.id,
        )
        db_session.add(note)
        await db_session.commit()
        await db_session.refresh(note)

        await DedupService(db_session).merge_contacts(
            primary.id, secondary.id, user_id=test_user.id
        )
        await db_session.commit()
        await db_session.refresh(note)

        assert note.entity_id == primary.id

        audit_rows = await db_session.execute(
            select(AuditLog)
            .where(AuditLog.entity_type == "contact")
            .where(AuditLog.entity_id == primary.id)
            .where(AuditLog.action == "merge")
        )
        entries = list(audit_rows.scalars().all())
        assert len(entries) == 1
        assert entries[0].user_id == test_user.id

    @pytest.mark.asyncio
    async def test_merge_companies_soft_deletes_and_reassigns_contacts(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Company merge moves child contacts and soft-deletes the secondary."""
        from src.dedup.service import DedupService

        primary = Company(
            name="Acme Primary",
            status="customer",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        secondary = Company(
            name="Acme Secondary",
            status="prospect",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add_all([primary, secondary])
        await db_session.commit()
        await db_session.refresh(primary)
        await db_session.refresh(secondary)

        child = Contact(
            first_name="Child",
            last_name="Contact",
            email="childco@example.com",
            company_id=secondary.id,
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(child)
        await db_session.commit()
        await db_session.refresh(child)

        await DedupService(db_session).merge_companies(
            primary.id, secondary.id, user_id=test_user.id
        )
        await db_session.commit()
        await db_session.refresh(child)

        # Child contact now points at primary.
        assert child.company_id == primary.id

        # Secondary still in table, soft-deleted with forwarding pointer.
        row = await db_session.execute(
            select(Company).where(Company.id == secondary.id)
        )
        archived = row.scalar_one_or_none()
        assert archived is not None
        assert archived.status == "merged"
        assert archived.merged_into_id == primary.id

    @pytest.mark.asyncio
    async def test_merge_same_id_raises(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Passing the same id as primary and secondary must raise."""
        from src.dedup.service import DedupService

        with pytest.raises(ValueError, match="itself"):
            await DedupService(db_session).merge_contacts(1, 1)

    @pytest.mark.asyncio
    async def test_merge_leads_soft_deletes(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        from src.dedup.service import DedupService

        primary = Lead(
            first_name="LeadP", last_name="X",
            email="leadp@example.com",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        secondary = Lead(
            first_name="LeadS", last_name="X",
            email="leads@example.com",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        db_session.add_all([primary, secondary])
        await db_session.commit()
        await db_session.refresh(primary)
        await db_session.refresh(secondary)

        await DedupService(db_session).merge_leads(
            primary.id, secondary.id, user_id=test_user.id
        )
        await db_session.commit()

        row = await db_session.execute(select(Lead).where(Lead.id == secondary.id))
        archived = row.scalar_one_or_none()
        assert archived is not None
        assert archived.status == "merged"
        assert archived.merged_into_id == primary.id

    @pytest.mark.asyncio
    async def test_merge_contacts_transfers_attachments_and_comments(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Polymorphic attachments/comments/notifications must follow the merge.

        Covers the Session 3 review finding that the original merge
        implementation only repointed Activity/Note/EntityTag and
        silently orphaned every other (entity_type, entity_id) table.
        """
        from src.dedup.service import DedupService
        from src.attachments.models import Attachment
        from src.comments.models import Comment
        from src.notifications.models import Notification

        primary = Contact(
            first_name="Attach", last_name="Primary",
            email="attach.primary@example.com",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        secondary = Contact(
            first_name="Attach", last_name="Secondary",
            email="attach.secondary@example.com",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        db_session.add_all([primary, secondary])
        await db_session.commit()
        await db_session.refresh(primary)
        await db_session.refresh(secondary)

        attachment = Attachment(
            filename="stored.pdf",
            original_filename="Contract.pdf",
            file_path="/tmp/stored.pdf",
            file_size=1024,
            mime_type="application/pdf",
            entity_type="contacts",
            entity_id=secondary.id,
            uploaded_by=test_user.id,
        )
        comment = Comment(
            content="Called the secondary, follow up next week.",
            entity_type="contacts",
            entity_id=secondary.id,
            user_id=test_user.id,
        )
        notification = Notification(
            user_id=test_user.id,
            type="mention",
            title="You were mentioned",
            message="about secondary",
            entity_type="contacts",
            entity_id=secondary.id,
        )
        db_session.add_all([attachment, comment, notification])
        await db_session.commit()
        await db_session.refresh(attachment)
        await db_session.refresh(comment)
        await db_session.refresh(notification)

        await DedupService(db_session).merge_contacts(
            primary.id, secondary.id, user_id=test_user.id
        )
        await db_session.commit()
        await db_session.refresh(attachment)
        await db_session.refresh(comment)
        await db_session.refresh(notification)

        assert attachment.entity_id == primary.id
        assert comment.entity_id == primary.id
        assert notification.entity_id == primary.id

    @pytest.mark.asyncio
    async def test_merged_companies_hidden_from_list(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Companies soft-deleted via merge must not leak into list views."""
        from src.dedup.service import DedupService
        from src.companies.service import CompanyService

        primary = Company(
            name="Visible Primary Co",
            status="customer",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        secondary = Company(
            name="Hidden Secondary Co",
            status="prospect",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add_all([primary, secondary])
        await db_session.commit()
        await db_session.refresh(primary)
        await db_session.refresh(secondary)

        await DedupService(db_session).merge_companies(
            primary.id, secondary.id, user_id=test_user.id
        )
        await db_session.commit()

        items, _ = await CompanyService(db_session).get_list()
        ids = [c.id for c in items]
        assert primary.id in ids
        assert secondary.id not in ids

        # Explicit merged filter still surfaces the tombstone.
        merged_items, _ = await CompanyService(db_session).get_list(
            status="merged"
        )
        assert any(c.id == secondary.id for c in merged_items)

    @pytest.mark.asyncio
    async def test_merged_leads_hidden_from_list(
        self,
        db_session: AsyncSession,
        test_user: User,
    ):
        """Leads soft-deleted via merge must not leak into list views."""
        from src.dedup.service import DedupService
        from src.leads.service import LeadService

        primary = Lead(
            first_name="LeadVisible", last_name="Primary",
            email="lead.visible@example.com",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        secondary = Lead(
            first_name="LeadHidden", last_name="Secondary",
            email="lead.hidden@example.com",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        db_session.add_all([primary, secondary])
        await db_session.commit()
        await db_session.refresh(primary)
        await db_session.refresh(secondary)

        await DedupService(db_session).merge_leads(
            primary.id, secondary.id, user_id=test_user.id
        )
        await db_session.commit()

        items, _ = await LeadService(db_session).get_list()
        ids = [l.id for l in items]
        assert primary.id in ids
        assert secondary.id not in ids


class TestClustersEndpoint:
    """Admin /api/dedup/clusters endpoint + cluster discovery."""

    @pytest.mark.asyncio
    async def test_clusters_groups_contacts_by_phone(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        manager_auth_headers: dict,
        test_user: User,
    ):
        """Three contacts sharing a normalized phone show up as one cluster of 3."""
        db_session.add_all([
            Contact(
                first_name="One", last_name="Cluster", phone="(312) 555-1111",
                owner_id=test_user.id, created_by_id=test_user.id,
            ),
            Contact(
                first_name="Two", last_name="Cluster", phone="3125551111",
                owner_id=test_user.id, created_by_id=test_user.id,
            ),
            Contact(
                first_name="Three", last_name="Cluster", phone="312.555.1111",
                owner_id=test_user.id, created_by_id=test_user.id,
            ),
            # Decoy: different phone, must not appear.
            Contact(
                first_name="Solo", last_name="Decoy", phone="3125559999",
                owner_id=test_user.id, created_by_id=test_user.id,
            ),
        ])
        await db_session.commit()

        resp = await client.get(
            "/api/dedup/clusters?entity_type=contacts&key=phone",
            headers=manager_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["entity_type"] == "contacts"
        assert body["key"] == "phone"
        # Solo contact is not in any cluster — only the 3 should be returned.
        assert len(body["clusters"]) == 1
        cluster = body["clusters"][0]
        assert cluster["member_count"] == 3
        labels = {m["label"] for m in cluster["members"]}
        assert labels == {"One Cluster", "Two Cluster", "Three Cluster"}

    @pytest.mark.asyncio
    async def test_clusters_excludes_soft_deleted(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        manager_auth_headers: dict,
        test_user: User,
    ):
        """Soft-deleted + merged-away rows must not appear in any cluster."""
        from datetime import datetime, timezone

        live = Contact(
            first_name="Live", last_name="Twin", phone="3125557000",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        soft = Contact(
            first_name="Soft", last_name="Twin", phone="3125557000",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        db_session.add_all([live, soft])
        await db_session.commit()
        await db_session.refresh(live)
        await db_session.refresh(soft)
        # Soft-delete one of the twins; cluster should disappear because
        # the live count drops to 1.
        soft.deleted_at = datetime.now(timezone.utc)
        await db_session.commit()

        resp = await client.get(
            "/api/dedup/clusters?entity_type=contacts&key=phone",
            headers=manager_auth_headers,
        )
        assert resp.status_code == 200
        for c in resp.json()["clusters"]:
            for m in c["members"]:
                assert m["id"] != soft.id

    @pytest.mark.asyncio
    async def test_clusters_member_count_meta(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        manager_auth_headers: dict,
        test_user: User,
    ):
        """Each cluster member carries activity_count + last_activity_at."""
        c1 = Contact(
            first_name="MetaA", last_name="Pair", phone="3125556500",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        c2 = Contact(
            first_name="MetaB", last_name="Pair", phone="3125556500",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        db_session.add_all([c1, c2])
        await db_session.commit()
        await db_session.refresh(c1)
        await db_session.refresh(c2)

        # 2 activities on c1, none on c2 — winner-pick UI should sort c1 first.
        from src.activities.models import ActivityType
        db_session.add_all([
            Activity(
                entity_type="contacts", entity_id=c1.id, activity_type=ActivityType.NOTE,
                subject="touch1", owner_id=test_user.id, created_by_id=test_user.id,
            ),
            Activity(
                entity_type="contacts", entity_id=c1.id, activity_type=ActivityType.NOTE,
                subject="touch2", owner_id=test_user.id, created_by_id=test_user.id,
            ),
        ])
        await db_session.commit()

        resp = await client.get(
            "/api/dedup/clusters?entity_type=contacts&key=phone",
            headers=manager_auth_headers,
        )
        body = resp.json()
        cluster = next(c for c in body["clusters"] if c["key_value"] == "3125556500")
        # Sorted by last_activity_at desc — c1 comes first.
        first, second = cluster["members"]
        assert first["id"] == c1.id
        assert first["activity_count"] == 2
        assert second["id"] == c2.id
        assert second["activity_count"] == 0

    @pytest.mark.asyncio
    async def test_clusters_reports_skipped_no_key(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        manager_auth_headers: dict,
        test_user: User,
    ):
        """Contacts with no value for the chosen match key get counted as skipped_no_key."""
        # Two contacts with phone (one cluster of 2), 3 with no phone at all.
        db_session.add_all([
            Contact(
                first_name="Skip", last_name="ContactA", phone="3125558081",
                owner_id=test_user.id, created_by_id=test_user.id,
            ),
            Contact(
                first_name="Skip", last_name="ContactB", phone="3125558081",
                owner_id=test_user.id, created_by_id=test_user.id,
            ),
            Contact(
                first_name="NoPhone", last_name="One", email="np1@example.com",
                owner_id=test_user.id, created_by_id=test_user.id,
            ),
            Contact(
                first_name="NoPhone", last_name="Two", email="np2@example.com",
                owner_id=test_user.id, created_by_id=test_user.id,
            ),
            Contact(
                first_name="NoPhone", last_name="Three", email="np3@example.com",
                owner_id=test_user.id, created_by_id=test_user.id,
            ),
        ])
        await db_session.commit()

        resp = await client.get(
            "/api/dedup/clusters?entity_type=contacts&key=phone",
            headers=manager_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["skipped_no_key"] >= 3  # at minimum the 3 phone-less ones

    @pytest.mark.asyncio
    async def test_clusters_invalid_entity_returns_400(
        self,
        client: AsyncClient,
        manager_auth_headers: dict,
    ):
        resp = await client.get(
            "/api/dedup/clusters?entity_type=invoices&key=email",
            headers=manager_auth_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_clusters_invalid_key_returns_400(
        self,
        client: AsyncClient,
        manager_auth_headers: dict,
    ):
        resp = await client.get(
            "/api/dedup/clusters?entity_type=leads&key=name",
            headers=manager_auth_headers,
        )
        # leads doesn't support name-key (no canonical name normalization)
        assert resp.status_code == 400


class TestMergeCluster:
    """POST /api/dedup/merge-cluster — winner_id + list of loser_ids."""

    @pytest.mark.asyncio
    async def test_merge_cluster_collapses_three_into_one(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        manager_auth_headers: dict,
        test_user: User,
    ):
        """Merging 2 losers into a winner soft-deletes the losers and keeps the winner."""
        winner = Contact(
            first_name="Winner", last_name="Keep", email="merge.cluster@example.com",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        loser_a = Contact(
            first_name="Loser", last_name="A", phone="3125550000",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        loser_b = Contact(
            first_name="Loser", last_name="B", phone="3125550000",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        db_session.add_all([winner, loser_a, loser_b])
        await db_session.commit()
        await db_session.refresh(winner)
        await db_session.refresh(loser_a)
        await db_session.refresh(loser_b)

        resp = await client.post(
            "/api/dedup/merge-cluster",
            headers=manager_auth_headers,
            json={
                "entity_type": "contacts",
                "winner_id": winner.id,
                "loser_ids": [loser_a.id, loser_b.id],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["winner_id"] == winner.id
        assert set(body["merged_ids"]) == {loser_a.id, loser_b.id}
        assert body["failures"] == []

        # Winner alive; losers soft-deleted with merged_into_id pointing at winner.
        await db_session.refresh(winner)
        await db_session.refresh(loser_a)
        await db_session.refresh(loser_b)
        assert winner.deleted_at is None
        assert loser_a.deleted_at is not None
        assert loser_b.deleted_at is not None
        assert loser_a.merged_into_id == winner.id
        assert loser_b.merged_into_id == winner.id

    @pytest.mark.asyncio
    async def test_merge_cluster_winner_in_losers_is_400(
        self,
        client: AsyncClient,
        manager_auth_headers: dict,
    ):
        resp = await client.post(
            "/api/dedup/merge-cluster",
            headers=manager_auth_headers,
            json={"entity_type": "contacts", "winner_id": 1, "loser_ids": [1, 2]},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_merge_cluster_partial_failure_continues(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        manager_auth_headers: dict,
        test_user: User,
    ):
        """Bad loser id is reported in `failures`; valid losers still merge."""
        winner = Contact(
            first_name="Winner2", last_name="OK", email="winner2@example.com",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        good_loser = Contact(
            first_name="Good", last_name="Loser", email="good@example.com",
            owner_id=test_user.id, created_by_id=test_user.id,
        )
        db_session.add_all([winner, good_loser])
        await db_session.commit()
        await db_session.refresh(winner)
        await db_session.refresh(good_loser)

        # 999999 will not exist.
        resp = await client.post(
            "/api/dedup/merge-cluster",
            headers=manager_auth_headers,
            json={
                "entity_type": "contacts",
                "winner_id": winner.id,
                "loser_ids": [good_loser.id, 999999],
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert good_loser.id in body["merged_ids"]
        bad = next((f for f in body["failures"] if f["id"] == 999999), None)
        assert bad is not None
        # Reason is classified so the UI can show "refresh and retry" not raw SQL.
        assert bad["reason_code"] == "stale_cluster"
