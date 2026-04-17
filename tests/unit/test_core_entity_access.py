"""Unit tests for core/entity_access.py — _resolve_entity and require_entity_access."""

from datetime import date

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.data_scope import DataScope
from src.core.entity_access import _resolve_entity, require_entity_access


# ---------------------------------------------------------------------------
# TestResolveEntity
# ---------------------------------------------------------------------------

class TestResolveEntity:
    async def test_unknown_entity_type_returns_none(self, db_session: AsyncSession):
        """Unknown entity_type returns (None, normalized) without raising."""
        entity, plural = await _resolve_entity(db_session, "widget", 999)
        assert entity is None
        assert plural == "widget"

    async def test_resolves_contact_singular(
        self, db_session: AsyncSession, test_user, test_company
    ):
        """_resolve_entity('contact', id) returns the Contact row and plural 'contacts'."""
        from src.contacts.models import Contact

        contact = Contact(
            first_name="Alice",
            last_name="Resolve",
            email="alice.resolve@example.com",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(contact)
        await db_session.commit()
        await db_session.refresh(contact)

        entity, plural = await _resolve_entity(db_session, "contact", contact.id)
        assert entity is not None
        assert entity.id == contact.id
        assert plural == "contacts"

    async def test_resolves_contact_plural_form(
        self, db_session: AsyncSession, test_user
    ):
        """_resolve_entity('contacts', id) normalises to singular and resolves."""
        from src.contacts.models import Contact

        contact = Contact(
            first_name="Bob",
            last_name="Plural",
            email="bob.plural@example.com",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(contact)
        await db_session.commit()
        await db_session.refresh(contact)

        entity, plural = await _resolve_entity(db_session, "contacts", contact.id)
        assert entity is not None
        assert entity.id == contact.id
        assert plural == "contacts"

    async def test_returns_none_when_contact_id_missing(self, db_session: AsyncSession):
        """Non-existent contact id returns (None, 'contacts')."""
        entity, plural = await _resolve_entity(db_session, "contact", 99999)
        assert entity is None
        assert plural == "contacts"

    async def test_resolves_company(
        self, db_session: AsyncSession, test_user
    ):
        """_resolve_entity('company', id) returns the Company row."""
        from src.companies.models import Company

        company = Company(
            name="Resolve Co",
            status="prospect",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(company)
        await db_session.commit()
        await db_session.refresh(company)

        entity, plural = await _resolve_entity(db_session, "company", company.id)
        assert entity is not None
        assert entity.id == company.id
        assert plural == "companies"

    async def test_expense_returns_parent_company(
        self, db_session: AsyncSession, test_user, test_company
    ):
        """Expense branch returns the parent Company; plural is canonical 'expenses'."""
        from src.expenses.models import Expense

        expense = Expense(
            company_id=test_company.id,
            amount=100.0,
            currency="USD",
            description="Office supplies",
            expense_date=date.today(),
            created_by_id=test_user.id,
        )
        db_session.add(expense)
        await db_session.commit()
        await db_session.refresh(expense)

        entity, plural = await _resolve_entity(db_session, "expense", expense.id)
        assert entity is not None
        assert entity.id == test_company.id
        assert plural == "expenses"

    async def test_expense_missing_returns_none(self, db_session: AsyncSession):
        """Non-existent expense id returns (None, 'expenses')."""
        entity, plural = await _resolve_entity(db_session, "expense", 99999)
        assert entity is None
        assert plural == "expenses"

    @pytest.mark.parametrize(
        "singular, expected_plural",
        [
            ("contact", "contacts"),
            ("company", "companies"),
            ("lead", "leads"),
            ("opportunity", "opportunities"),
            ("quote", "quotes"),
            ("proposal", "proposals"),
            ("contract", "contracts"),
            ("payment", "payments"),
            ("activity", "activities"),
            ("expense", "expenses"),
        ],
    )
    async def test_plural_matches_entity_share_convention(
        self, db_session: AsyncSession, singular: str, expected_plural: str
    ):
        """Plural output must match the canonical keys used by EntityShare/DataScope.

        A naive `normalized + 's'` produces 'companys'/'opportunitys'/'activitys'
        which do NOT match ENTITY_TYPE_COMPANIES='companies' etc., silently
        dropping shared access for those entity types.
        """
        _, plural = await _resolve_entity(db_session, singular, 99999)
        assert plural == expected_plural


# ---------------------------------------------------------------------------
# TestRequireEntityAccess
# ---------------------------------------------------------------------------

class TestRequireEntityAccess:
    def _admin_scope(self, user_id: int) -> DataScope:
        return DataScope(
            user_id=user_id,
            role_name="admin",
            owner_id=None,
            is_scoped=False,
        )

    def _scoped_scope(self, user_id: int, shared: dict | None = None) -> DataScope:
        return DataScope(
            user_id=user_id,
            role_name="sales_rep",
            owner_id=user_id,
            is_scoped=True,
            shared_entity_ids=shared or {},
        )

    async def test_admin_existing_entity_passes(
        self, db_session: AsyncSession, test_user, test_contact
    ):
        """Admin DataScope with existing entity raises nothing."""
        scope = self._admin_scope(test_user.id)
        await require_entity_access(
            db_session, "contact", test_contact.id, test_user, scope
        )

    async def test_admin_missing_entity_raises_404(
        self, db_session: AsyncSession, test_user
    ):
        """Admin DataScope with non-existent entity raises HTTP 404."""
        scope = self._admin_scope(test_user.id)
        with pytest.raises(HTTPException) as exc_info:
            await require_entity_access(
                db_session, "contact", 99999, test_user, scope
            )
        assert exc_info.value.status_code == 404

    async def test_scoped_user_owns_entity_passes(
        self, db_session: AsyncSession, test_user
    ):
        """Scoped user who owns the entity gets no exception."""
        from src.contacts.models import Contact

        contact = Contact(
            first_name="Owner",
            last_name="Test",
            email="owner.test@example.com",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(contact)
        await db_session.commit()
        await db_session.refresh(contact)

        scope = self._scoped_scope(test_user.id)
        await require_entity_access(
            db_session, "contact", contact.id, test_user, scope
        )

    async def test_scoped_user_not_owner_raises(
        self, db_session: AsyncSession, test_user, _sales_rep_user, seed_roles
    ):
        """Scoped user who does NOT own the entity and has no share gets 403."""
        from src.contacts.models import Contact

        contact = Contact(
            first_name="Other",
            last_name="Owner",
            email="other.owner@example.com",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(contact)
        await db_session.commit()
        await db_session.refresh(contact)

        scope = self._scoped_scope(_sales_rep_user.id)
        with pytest.raises(HTTPException) as exc_info:
            await require_entity_access(
                db_session, "contact", contact.id, _sales_rep_user, scope
            )
        assert exc_info.value.status_code == 403

    async def test_scoped_user_shared_entity_passes(
        self, db_session: AsyncSession, test_user, _sales_rep_user, seed_roles
    ):
        """Scoped user with entity in shared_ids gets no exception."""
        from src.contacts.models import Contact

        contact = Contact(
            first_name="Shared",
            last_name="Contact",
            email="shared.contact@example.com",
            owner_id=test_user.id,
            created_by_id=test_user.id,
        )
        db_session.add(contact)
        await db_session.commit()
        await db_session.refresh(contact)

        scope = self._scoped_scope(
            _sales_rep_user.id,
            shared={"contacts": [contact.id]},
        )
        await require_entity_access(
            db_session, "contact", contact.id, _sales_rep_user, scope
        )

    async def test_scoped_user_missing_entity_raises_404(
        self, db_session: AsyncSession, _sales_rep_user, seed_roles
    ):
        """Scoped user with non-existent entity id gets HTTP 404."""
        scope = self._scoped_scope(_sales_rep_user.id)
        with pytest.raises(HTTPException) as exc_info:
            await require_entity_access(
                db_session, "contact", 99999, _sales_rep_user, scope
            )
        assert exc_info.value.status_code == 404

    async def test_unknown_entity_type_scoped_raises_404(
        self, db_session: AsyncSession, _sales_rep_user, seed_roles
    ):
        """Unknown entity_type for scoped user is treated as missing — raises 404."""
        scope = self._scoped_scope(_sales_rep_user.id)
        with pytest.raises(HTTPException) as exc_info:
            await require_entity_access(
                db_session, "widget", 1, _sales_rep_user, scope
            )
        assert exc_info.value.status_code == 404

    async def test_unknown_entity_type_admin_raises_404(
        self, db_session: AsyncSession, test_superuser
    ):
        """Unknown entity_type for admin is also treated as missing — raises 404."""
        scope = self._admin_scope(test_superuser.id)
        with pytest.raises(HTTPException) as exc_info:
            await require_entity_access(
                db_session, "widget", 1, test_superuser, scope
            )
        assert exc_info.value.status_code == 404

    async def test_detail_contains_entity_info(
        self, db_session: AsyncSession, test_user
    ):
        """404 detail string mentions entity_type and entity_id."""
        scope = self._admin_scope(test_user.id)
        with pytest.raises(HTTPException) as exc_info:
            await require_entity_access(
                db_session, "lead", 12345, test_user, scope
            )
        detail = exc_info.value.detail
        assert "lead" in detail
        assert "12345" in detail
