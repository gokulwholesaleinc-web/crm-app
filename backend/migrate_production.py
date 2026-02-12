#!/usr/bin/env python3
"""
Production database migration script.
Runs on every deployment to ensure schema is up-to-date.
Safe to run multiple times (idempotent).
"""

import asyncio
import asyncpg
import os
from typing import List, Tuple

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("❌ DATABASE_URL not set in environment")
    exit(1)

# Convert from SQLAlchemy format to asyncpg format
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
if "?sslmode=" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.split("?")[0] + "?ssl=require"

async def run_migrations():
    """Run all database migrations."""
    print("🔄 Starting database migrations...")

    conn = await asyncpg.connect(DATABASE_URL)

    try:
        # Migration 1: Add role column to users table
        print("📋 Migration 1: Add role column to users table...")
        await conn.execute("""
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'sales_rep' NOT NULL
        """)

        # Set admin users to admin role
        updated = await conn.execute("""
            UPDATE users
            SET role = 'admin'
            WHERE (email IN ('admin@admin.com', 'harsh@test.com') OR is_superuser = true)
            AND role != 'admin'
        """)
        print(f"   ✅ Role column exists, {updated.split()[-1]} users updated to admin")

        # Migration 2: Verify critical tables exist
        print("📋 Migration 2: Verify critical tables...")
        tables_to_check = [
            'users', 'tenants', 'tenant_users', 'tenant_settings',
            'leads', 'lead_sources', 'contacts', 'companies',
            'opportunities', 'pipeline_stages', 'activities',
            'campaigns', 'quotes', 'proposals', 'payments'
        ]

        existing_tables = await conn.fetch("""
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
        """)
        existing_table_names = {row['tablename'] for row in existing_tables}

        missing_tables = []
        for table in tables_to_check:
            if table not in existing_table_names:
                missing_tables.append(table)

        if missing_tables:
            print(f"   ⚠️  Missing tables: {', '.join(missing_tables)}")
            print("   ⚠️  You need to run Base.metadata.create_all() to create missing tables")
        else:
            print(f"   ✅ All {len(tables_to_check)} critical tables exist")

        # Migration 3: Verify lead_sources and pipeline_stages have data
        print("📋 Migration 3: Verify reference data...")

        lead_sources_count = await conn.fetchval("SELECT COUNT(*) FROM lead_sources")
        pipeline_stages_count = await conn.fetchval("SELECT COUNT(*) FROM pipeline_stages")

        if lead_sources_count == 0:
            print("   ⚠️  No lead_sources found - dashboard charts will be empty")
        else:
            print(f"   ✅ {lead_sources_count} lead sources found")

        if pipeline_stages_count == 0:
            print("   ⚠️  No pipeline_stages found - pipeline funnel will be empty")
        else:
            print(f"   ✅ {pipeline_stages_count} pipeline stages found")

        print("\n✅ All migrations completed successfully!")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(run_migrations())
