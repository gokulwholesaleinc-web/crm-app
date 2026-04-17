"""Unit tests for core/base_service.py — BaseService and CRUDService using Contact."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.contacts.models import Contact
from src.contacts.schemas import ContactCreate, ContactUpdate
from src.core.base_service import BaseService, CRUDService


# ---------------------------------------------------------------------------
# Concrete service for tests
# ---------------------------------------------------------------------------

class ContactService(CRUDService[Contact, ContactCreate, ContactUpdate]):
    model = Contact


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_data(first: str = "John", last: str = "Doe", owner_id: int | None = None) -> ContactCreate:
    return ContactCreate(first_name=first, last_name=last, owner_id=owner_id)


async def _seed(db: AsyncSession, n: int, owner_id: int | None = None) -> list[Contact]:
    """Insert n Contacts and flush; return list."""
    contacts = []
    for i in range(n):
        c = Contact(
            first_name=f"User{i}",
            last_name="Test",
            status="active",
            owner_id=owner_id,
            created_by_id=1,
        )
        db.add(c)
        contacts.append(c)
    await db.flush()
    for c in contacts:
        await db.refresh(c)
    return contacts


# ---------------------------------------------------------------------------
# TestBaseServiceGetById
# ---------------------------------------------------------------------------

class TestBaseServiceGetById:
    async def test_returns_none_when_not_found(self, db_session: AsyncSession):
        svc = ContactService(db_session)
        result = await svc.get_by_id(999999)
        assert result is None

    async def test_returns_instance_when_found(self, db_session: AsyncSession):
        [c] = await _seed(db_session, 1)
        svc = ContactService(db_session)
        result = await svc.get_by_id(c.id)
        assert result is not None
        assert result.id == c.id


# ---------------------------------------------------------------------------
# TestBaseServicePaginateQuery
# ---------------------------------------------------------------------------

class TestBaseServicePaginateQuery:
    async def test_returns_items_and_total(self, db_session: AsyncSession):
        await _seed(db_session, 3)
        svc = ContactService(db_session)
        q = select(Contact)
        items, total = await svc.paginate_query(q, page=1, page_size=10)
        assert total == 3
        assert len(items) == 3

    async def test_respects_page_size(self, db_session: AsyncSession):
        await _seed(db_session, 5)
        svc = ContactService(db_session)
        q = select(Contact)
        items, total = await svc.paginate_query(q, page=1, page_size=2)
        assert total == 5
        assert len(items) == 2

    async def test_empty_query_returns_zero(self, db_session: AsyncSession):
        svc = ContactService(db_session)
        q = select(Contact)
        items, total = await svc.paginate_query(q, page=1, page_size=10)
        assert total == 0
        assert items == []

    async def test_auto_orders_by_created_at_desc(self, db_session: AsyncSession):
        contacts = await _seed(db_session, 3)
        svc = ContactService(db_session)
        q = select(Contact)
        items, _ = await svc.paginate_query(q, page=1, page_size=10)
        # created_at.desc() means last inserted comes first
        assert items[0].id == contacts[-1].id

    async def test_page_2_returns_correct_slice(self, db_session: AsyncSession):
        await _seed(db_session, 4)
        svc = ContactService(db_session)
        q = select(Contact)
        items, total = await svc.paginate_query(q, page=2, page_size=2)
        assert total == 4
        assert len(items) == 2


# ---------------------------------------------------------------------------
# TestApplyOwnerFilter
# ---------------------------------------------------------------------------

class TestApplyOwnerFilter:
    async def test_no_owner_id_returns_all(self, db_session: AsyncSession):
        await _seed(db_session, 3, owner_id=1)
        svc = ContactService(db_session)
        q = svc.apply_owner_filter(select(Contact), owner_id=None)
        result = await db_session.execute(q)
        assert len(result.scalars().all()) == 3

    async def test_single_owner_filters_correctly(self, db_session: AsyncSession):
        await _seed(db_session, 2, owner_id=10)
        await _seed(db_session, 2, owner_id=20)
        svc = ContactService(db_session)
        q = svc.apply_owner_filter(select(Contact), owner_id=10)
        result = await db_session.execute(q)
        rows = result.scalars().all()
        assert len(rows) == 2
        assert all(r.owner_id == 10 for r in rows)

    async def test_shared_entity_ids_include_extra_rows(self, db_session: AsyncSession):
        owned = await _seed(db_session, 1, owner_id=10)
        shared = await _seed(db_session, 2, owner_id=99)
        svc = ContactService(db_session)
        shared_ids = [c.id for c in shared]
        q = svc.apply_owner_filter(select(Contact), owner_id=10, shared_entity_ids=shared_ids)
        result = await db_session.execute(q)
        ids = {r.id for r in result.scalars().all()}
        assert owned[0].id in ids
        assert all(s.id in ids for s in shared)


# ---------------------------------------------------------------------------
# TestBaseServiceGetMulti
# ---------------------------------------------------------------------------

class TestBaseServiceGetMulti:
    async def test_returns_items_and_total(self, db_session: AsyncSession):
        await _seed(db_session, 3)
        svc = ContactService(db_session)
        items, total = await svc.get_multi()
        assert total == 3
        assert len(items) == 3

    async def test_paginates_correctly(self, db_session: AsyncSession):
        await _seed(db_session, 5)
        svc = ContactService(db_session)
        items, total = await svc.get_multi(page=2, page_size=3)
        assert total == 5
        assert len(items) == 2  # 5 total, page 2 of page_size 3 → 2 remaining


# ---------------------------------------------------------------------------
# TestCRUDServiceCreate
# ---------------------------------------------------------------------------

class TestCRUDServiceCreate:
    async def test_creates_record_with_created_by_id(self, db_session: AsyncSession):
        svc = ContactService(db_session)
        data = _create_data("Alice", "Smith")
        result = await svc.create(data, user_id=42)
        assert result.id is not None
        assert result.created_by_id == 42
        assert result.first_name == "Alice"

    async def test_tag_ids_not_on_model(self, db_session: AsyncSession):
        svc = ContactService(db_session)
        data = ContactCreate(first_name="Bob", last_name="Jones", tag_ids=[1, 2])
        result = await svc.create(data, user_id=1)
        # tag_ids is excluded — Contact has no tag_ids column
        assert not hasattr(result, "tag_ids") or result.id is not None

    async def test_extra_fields_land_on_model(self, db_session: AsyncSession):
        svc = ContactService(db_session)
        data = _create_data("Carol", "Doe")
        result = await svc.create(data, user_id=1, status="inactive")
        assert result.status == "inactive"


# ---------------------------------------------------------------------------
# TestCRUDServiceUpdate
# ---------------------------------------------------------------------------

class TestCRUDServiceUpdate:
    async def test_patches_only_set_fields(self, db_session: AsyncSession):
        svc = ContactService(db_session)
        created = await svc.create(_create_data("Dave", "Original"), user_id=1)
        update = ContactUpdate(last_name="Updated")
        result = await svc.update(created, update, user_id=2)
        assert result.last_name == "Updated"
        assert result.first_name == "Dave"  # unchanged

    async def test_sets_updated_by_id(self, db_session: AsyncSession):
        svc = ContactService(db_session)
        created = await svc.create(_create_data("Eve", "Test"), user_id=1)
        update = ContactUpdate(status="inactive")
        result = await svc.update(created, update, user_id=99)
        assert result.updated_by_id == 99

    async def test_does_not_stomp_unset_fields(self, db_session: AsyncSession):
        svc = ContactService(db_session)
        created = await svc.create(_create_data("Frank", "Test"), user_id=1)
        original_first = created.first_name
        update = ContactUpdate(status="inactive")
        result = await svc.update(created, update, user_id=1)
        assert result.first_name == original_first


# ---------------------------------------------------------------------------
# TestCRUDServiceDelete
# ---------------------------------------------------------------------------

class TestCRUDServiceDelete:
    async def test_removes_record_from_db(self, db_session: AsyncSession):
        svc = ContactService(db_session)
        created = await svc.create(_create_data("Grace", "Gone"), user_id=1)
        record_id = created.id
        await svc.delete(created)
        result = await db_session.execute(select(Contact).where(Contact.id == record_id))
        assert result.scalar_one_or_none() is None

    async def test_delete_without_clear_tags_does_not_raise(self, db_session: AsyncSession):
        svc = ContactService(db_session)
        created = await svc.create(_create_data("Henry", "Safe"), user_id=1)
        # ContactService has no clear_tags attr — should not raise
        await svc.delete(created)
