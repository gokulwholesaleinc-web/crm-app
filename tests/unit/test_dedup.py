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
