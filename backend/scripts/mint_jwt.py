"""Mint a JWT for a CRM user and emit a paste-ready Chrome console snippet.

Pulls SECRET_KEY + DATABASE_URL from the current process env — run with
`railway run python backend/scripts/mint_jwt.py ...` to pick up prod env.

Usage
-----
  railway run python backend/scripts/mint_jwt.py --email giancarlo@... --hours 8
  railway run python backend/scripts/mint_jwt.py --user-id 42 --hours 2 -v

Stdout is a single line you can paste into the Chrome console as-is.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dataclasses import dataclass  # noqa: E402
from datetime import datetime  # noqa: E402

from sqlalchemy import text  # noqa: E402

from src.auth.security import create_access_token  # noqa: E402
from src.database import get_db  # noqa: E402


@dataclass
class _UserRow:
    id: int
    email: str
    full_name: str
    is_active: bool
    is_superuser: bool
    created_at: datetime | None


async def _resolve_user(*, email: str | None, user_id: int | None) -> _UserRow:
    """Plain SQL lookup so we don't trigger the User mapper's relationship
    init — the full ORM model needs every related model imported, which
    is overkill for a one-shot mint script.
    """
    if email is None and user_id is None:
        raise SystemExit("Pass --email or --user-id")

    sql = (
        "SELECT id, email, full_name, is_active, is_superuser, created_at "
        "FROM users WHERE "
        + ("email = :email" if email is not None else "id = :user_id")
        + " LIMIT 1"
    )
    params = {"email": email} if email is not None else {"user_id": user_id}

    async for db in get_db():
        row = (await db.execute(text(sql), params)).first()
        if row is None:
            raise SystemExit(f"No user found (email={email!r}, id={user_id!r})")
        return _UserRow(
            id=row.id,
            email=row.email,
            full_name=row.full_name,
            is_active=row.is_active,
            is_superuser=row.is_superuser,
            created_at=row.created_at,
        )
    raise SystemExit("Could not open a DB session")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Mint a JWT for a CRM user.")
    parser.add_argument("--email")
    parser.add_argument("--user-id", type=int)
    parser.add_argument("--hours", type=int, default=8)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if not os.environ.get("SECRET_KEY"):
        raise SystemExit("SECRET_KEY missing — run via `railway run`.")

    user = await _resolve_user(email=args.email, user_id=args.user_id)
    token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(hours=args.hours),
    )

    user_obj = {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
    # Build a single-line JS expression. `json.dumps` produces valid JS
    # literals (JSON ⊂ JS for these shapes), so we can inline them into
    # the JS source without further escaping.
    js_token = json.dumps(token)
    js_user = json.dumps(user_obj, separators=(",", ":"))
    snippet = (
        "localStorage.setItem('crm-auth-storage',"
        f"JSON.stringify({{state:{{token:{js_token},user:{js_user}}},version:0}}));"
        "location.reload();"
    )

    print(snippet)

    if args.verbose:
        print(
            f"# user_id={user.id} email={user.email!r} "
            f"is_superuser={user.is_superuser} expires_in={args.hours}h",
            file=sys.stderr,
        )


if __name__ == "__main__":
    asyncio.run(main())
