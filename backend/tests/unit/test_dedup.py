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
        auth_headers: dict,
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
            headers=auth_headers,
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

        # Verify secondary was deleted
        result = await db_session.execute(
            select(Contact).where(Contact.id == secondary.id)
        )
        assert result.scalar_one_or_none() is None

    @pytest.mark.asyncio
    async def test_merge_contacts_transfers_activities(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        auth_headers: dict,
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
            headers=auth_headers,
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
        auth_headers: dict,
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
            headers=auth_headers,
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
        auth_headers: dict,
    ):
        """Test that merging an entity with itself fails."""
        response = await client.post(
            "/api/dedup/merge",
            headers=auth_headers,
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
        auth_headers: dict,
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
            headers=auth_headers,
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
        auth_headers: dict,
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
            headers=auth_headers,
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
