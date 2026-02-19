"""Apply performance indexes to the existing database.

Usage: docker compose exec backend python scripts/run_performance_indexes.py
"""

import asyncio
from sqlalchemy import text
from src.database import engine


INDEXES = [
    # created_at indexes for ORDER BY on list endpoints
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_contacts_created_at ON contacts (created_at)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_leads_created_at ON leads (created_at)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_opportunities_created_at ON opportunities (created_at)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_companies_created_at ON companies (created_at)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_activities_created_at ON activities (created_at)",
    # Composite indexes for owner + created_at queries
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_contacts_owner_created ON contacts (owner_id, created_at)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_leads_owner_created ON leads (owner_id, created_at)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_opportunities_owner_created ON opportunities (owner_id, created_at)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_companies_owner_created ON companies (owner_id, created_at)",
    "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_activities_owner_created ON activities (owner_id, created_at)",
]


async def main():
    print("Applying performance indexes...")
    # CONCURRENTLY requires autocommit (not inside a transaction)
    raw_conn = await engine.raw_connection()
    try:
        await raw_conn.set_autocommit(True)
        cursor = await raw_conn.cursor()
        for idx_sql in INDEXES:
            name = idx_sql.split("IF NOT EXISTS ")[1].split(" ON")[0]
            print(f"  Creating {name}...", end=" ")
            await cursor.execute(idx_sql)
            print("OK")
        await cursor.close()
    finally:
        await raw_conn.close()
    await engine.dispose()
    print("Done - all indexes applied.")


if __name__ == "__main__":
    asyncio.run(main())
