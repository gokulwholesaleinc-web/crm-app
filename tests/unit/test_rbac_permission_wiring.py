"""Targeted regressions for RBAC gaps in proposal/import/activity routes."""

import secrets
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from src.activities.models import Activity
from src.auth.models import User
from src.auth.security import create_access_token, get_password_hash
from src.contacts.models import Contact
from src.proposals.models import Proposal, ProposalTemplate
from src.roles.models import Role, UserRole


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(data={'sub': str(user.id)})}"}


async def _make_user(
    db_session: AsyncSession,
    email: str,
    *,
    role: str = "sales_rep",
) -> User:
    user = User(
        email=email,
        hashed_password=get_password_hash("testpassword123"),
        full_name=email.split("@")[0],
        is_active=True,
        is_superuser=False,
        role=role,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_custom_role_user(
    db_session: AsyncSession,
    *,
    email: str,
    permissions: dict[str, list[str]],
) -> User:
    user = await _make_user(db_session, email)
    role = Role(
        name=f"custom_{secrets.token_hex(4)}",
        description="Targeted custom RBAC test role",
        permissions=permissions,
    )
    db_session.add(role)
    await db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_id=role.id))
    await db_session.commit()
    await db_session.refresh(user)
    return user


def _csv_file(body: str) -> dict[str, tuple[str, str, str]]:
    return {"file": ("rows.csv", body, "text/csv")}


@pytest.mark.asyncio
async def test_viewer_cannot_create_proposal(
    client: AsyncClient,
    viewer_auth_headers: dict[str, str],
):
    response = await client.post(
        "/api/proposals",
        headers=viewer_auth_headers,
        json={"title": "Viewer draft", "status": "draft"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("patch", "/api/proposals/{proposal_id}", {"title": "Blocked"}),
        ("delete", "/api/proposals/{proposal_id}", None),
        ("post", "/api/proposals/{proposal_id}/send", None),
        ("post", "/api/proposals/{proposal_id}/accept", None),
        ("post", "/api/proposals/{proposal_id}/reject", None),
        ("post", "/api/proposals/{proposal_id}/duplicate", None),
    ],
)
async def test_viewer_cannot_mutate_existing_proposal(
    client: AsyncClient,
    db_session: AsyncSession,
    viewer_auth_headers: dict[str, str],
    test_user: User,
    method: str,
    path: str,
    body: dict[str, Any] | None,
):
    proposal = Proposal(
        proposal_number=f"PR-RBAC-{secrets.token_hex(4)}",
        public_token=secrets.token_urlsafe(32),
        title="Owned proposal",
        status="draft",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(proposal)
    await db_session.commit()
    await db_session.refresh(proposal)

    response = await client.request(
        method,
        path.format(proposal_id=proposal.id),
        headers=viewer_auth_headers,
        json=body,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_create_or_edit_proposal_templates(
    client: AsyncClient,
    db_session: AsyncSession,
    viewer_auth_headers: dict[str, str],
    test_user: User,
):
    template = ProposalTemplate(
        name="Owner template",
        body="Hello {{contact_name}}",
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(template)
    await db_session.commit()
    await db_session.refresh(template)

    create_response = await client.post(
        "/api/proposals/templates",
        headers=viewer_auth_headers,
        json={"name": "Viewer template", "body": "Nope"},
    )
    update_response = await client.patch(
        f"/api/proposals/templates/{template.id}",
        headers=viewer_auth_headers,
        json={"name": "Nope"},
    )
    delete_response = await client.delete(
        f"/api/proposals/templates/{template.id}",
        headers=viewer_auth_headers,
    )

    assert create_response.status_code == 403
    assert update_response.status_code == 403
    assert delete_response.status_code == 403


@pytest.mark.asyncio
async def test_custom_read_only_role_cannot_create_proposal(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await _make_custom_role_user(
        db_session,
        email="proposal-readonly@example.com",
        permissions={"contacts": ["read"]},
    )

    response = await client.post(
        "/api/proposals",
        headers=_headers(user),
        json={"title": "Custom read-only draft", "status": "draft"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_sales_rep_cannot_create_proposal_for_inaccessible_contact(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
):
    peer = await _make_user(db_session, "proposal-peer@example.com")
    contact = Contact(
        first_name="Peer",
        last_name="Contact",
        email="peer.contact@example.com",
        owner_id=peer.id,
        created_by_id=peer.id,
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)

    response = await client.post(
        "/api/proposals",
        headers=auth_headers,
        json={
            "title": "Cross-owner proposal",
            "status": "draft",
            "contact_id": contact.id,
        },
    )

    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/import-export/import/contacts", "first_name,last_name,email\nA,B,a@example.com\n"),
        ("/api/import-export/import/leads", "first_name,last_name,email\nA,B,a@example.com\n"),
        ("/api/import-export/import/companies", "name,email\nAcme,info@example.com\n"),
    ],
)
async def test_viewer_cannot_import_records(
    client: AsyncClient,
    viewer_auth_headers: dict[str, str],
    path: str,
    body: str,
):
    response = await client.post(
        path,
        headers=viewer_auth_headers,
        files=_csv_file(body),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_custom_read_only_role_cannot_run_mapped_import(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await _make_custom_role_user(
        db_session,
        email="import-readonly@example.com",
        permissions={"contacts": ["read"]},
    )

    response = await client.post(
        "/api/import-export/import/contacts/mapped",
        headers=_headers(user),
        data={"column_mapping": '{"Email": "email"}'},
        files=_csv_file("Email\nreadonly@example.com\n"),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_only_custom_role_cannot_merge_contact_imports(
    client: AsyncClient,
    db_session: AsyncSession,
):
    user = await _make_custom_role_user(
        db_session,
        email="import-createonly@example.com",
        permissions={"contacts": ["create"]},
    )
    contact = Contact(
        first_name="Existing",
        last_name="Contact",
        email="existing@example.com",
        owner_id=user.id,
        created_by_id=user.id,
    )
    db_session.add(contact)
    await db_session.commit()

    response = await client.post(
        "/api/import-export/import/contacts",
        headers=_headers(user),
        data={"match_key": "email", "merge_strategy": "overwrite_all"},
        files=_csv_file("first_name,last_name,email\nUpdated,Contact,existing@example.com\n"),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_sales_rep_cannot_complete_someone_elses_activity(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
):
    peer = await _make_user(db_session, "activity-peer@example.com")
    activity = Activity(
        activity_type="task",
        subject="Peer task",
        entity_type="contacts",
        entity_id=999_001,
        owner_id=peer.id,
        created_by_id=peer.id,
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)

    response = await client.post(
        f"/api/activities/{activity.id}/complete",
        headers=auth_headers,
        json={},
    )
    await db_session.refresh(activity)

    assert response.status_code == 403
    assert activity.is_completed is False


@pytest.mark.asyncio
async def test_sales_rep_calendar_owner_id_is_coerced_to_self(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict[str, str],
):
    peer = await _make_user(db_session, "calendar-peer@example.com")
    scheduled_at = datetime.now(UTC) + timedelta(days=1)
    activity = Activity(
        activity_type="meeting",
        subject="Peer meeting",
        entity_type="contacts",
        entity_id=999_002,
        scheduled_at=scheduled_at,
        owner_id=peer.id,
        created_by_id=peer.id,
    )
    db_session.add(activity)
    await db_session.commit()

    start = date.today().isoformat()
    end = (date.today() + timedelta(days=2)).isoformat()
    response = await client.get(
        "/api/activities/calendar",
        headers=auth_headers,
        params={"start_date": start, "end_date": end, "owner_id": peer.id},
    )

    assert response.status_code == 200
    assert response.json()["total_activities"] == 0
