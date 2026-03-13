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

        # Set admin users to admin role and superuser
        updated = await conn.execute("""
            UPDATE users
            SET role = 'admin', is_superuser = true
            WHERE email IN ('admin@admin.com', 'harsh@test.com')
            AND (role != 'admin' OR is_superuser = false)
        """)
        print(f"   ✅ Role column exists, {updated.split()[-1]} users updated to admin")

        # Ensure admin users have admin role mapping in user_roles
        await conn.execute("""
            INSERT INTO user_roles (user_id, role_id, created_at, updated_at)
            SELECT u.id, r.id, NOW(), NOW()
            FROM users u, roles r
            WHERE u.email IN ('admin@admin.com', 'harsh@test.com')
            AND r.name = 'admin'
            AND NOT EXISTS (
                SELECT 1 FROM user_roles ur WHERE ur.user_id = u.id AND ur.role_id = r.id
            )
        """)
        print("   ✅ Admin user_roles mappings verified")

        # Migration 2: Add missing columns to existing tables
        # (Base.metadata.create_all only creates new tables, not new columns)
        print("📋 Migration 2: Add missing columns to existing tables...")
        column_migrations = [
            # leads
            ("ALTER TABLE leads ADD COLUMN IF NOT EXISTS sales_code VARCHAR(100)", "leads.sales_code"),
            ("CREATE INDEX IF NOT EXISTS ix_leads_sales_code ON leads(sales_code)", "index leads.sales_code"),
            # contacts
            ("ALTER TABLE contacts ADD COLUMN IF NOT EXISTS sales_code VARCHAR(100)", "contacts.sales_code"),
            ("CREATE INDEX IF NOT EXISTS ix_contacts_sales_code ON contacts(sales_code)", "index contacts.sales_code"),
            # companies
            ("ALTER TABLE companies ADD COLUMN IF NOT EXISTS segment VARCHAR(100)", "companies.segment"),
            ("CREATE INDEX IF NOT EXISTS ix_companies_segment ON companies(segment)", "index companies.segment"),
            # proposal_templates
            ("ALTER TABLE proposal_templates ADD COLUMN IF NOT EXISTS body TEXT NOT NULL DEFAULT ''", "proposal_templates.body"),
            ("ALTER TABLE proposal_templates ADD COLUMN IF NOT EXISTS legal_terms TEXT", "proposal_templates.legal_terms"),
            ("ALTER TABLE proposal_templates ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE", "proposal_templates.is_default"),
            ("ALTER TABLE proposal_templates ADD COLUMN IF NOT EXISTS owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL", "proposal_templates.owner_id"),
            # attachments
            ("ALTER TABLE attachments ADD COLUMN IF NOT EXISTS category VARCHAR(50)", "attachments.category"),
            # saved_filters
            ("ALTER TABLE saved_filters ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE", "saved_filters.is_public"),
            # saved_reports
            ("ALTER TABLE saved_reports ADD COLUMN IF NOT EXISTS schedule VARCHAR(20)", "saved_reports.schedule"),
            ("ALTER TABLE saved_reports ADD COLUMN IF NOT EXISTS recipients TEXT", "saved_reports.recipients"),
            # leads.pipeline_stage_id (FK to pipeline_stages)
            ("ALTER TABLE leads ADD COLUMN IF NOT EXISTS pipeline_stage_id INTEGER REFERENCES pipeline_stages(id) ON DELETE SET NULL", "leads.pipeline_stage_id"),
            ("CREATE INDEX IF NOT EXISTS ix_leads_pipeline_stage_id ON leads(pipeline_stage_id)", "index leads.pipeline_stage_id"),
            # pipeline_stages.pipeline_type
            ("ALTER TABLE pipeline_stages ADD COLUMN IF NOT EXISTS pipeline_type VARCHAR(20) DEFAULT 'opportunity'", "pipeline_stages.pipeline_type"),
            ("CREATE INDEX IF NOT EXISTS ix_pipeline_stages_pipeline_type ON pipeline_stages(pipeline_type)", "index pipeline_stages.pipeline_type"),
            # companies custom fields
            ("ALTER TABLE companies ADD COLUMN IF NOT EXISTS link_creative_tier VARCHAR(10)", "companies.link_creative_tier"),
            ("ALTER TABLE companies ADD COLUMN IF NOT EXISTS sow_url VARCHAR(500)", "companies.sow_url"),
            ("ALTER TABLE companies ADD COLUMN IF NOT EXISTS account_manager VARCHAR(255)", "companies.account_manager"),
        ]

        for sql, desc in column_migrations:
            try:
                await conn.execute(sql)
                print(f"   ✅ {desc}")
            except Exception as e:
                print(f"   ⚠️  {desc}: {e}")

        # Migration 2b: Set pipeline_type for lead-type stages
        print("📋 Migration 2b: Backfill pipeline_type for lead stages...")
        try:
            updated = await conn.execute("""
                UPDATE pipeline_stages
                SET pipeline_type = 'lead'
                WHERE LOWER(name) IN ('new', 'contacted', 'qualified', 'nurturing', 'unqualified', 'converted')
                AND pipeline_type != 'lead'
            """)
            print(f"   ✅ Updated {updated.split()[-1]} pipeline stages to pipeline_type='lead'")
        except Exception as e:
            print(f"   ⚠️  pipeline_type backfill: {e}")

        # Migration 3: Verify critical tables exist
        print("📋 Migration 3: Verify critical tables...")
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

        # Migration 4: Verify lead_sources and pipeline_stages have data
        print("📋 Migration 4: Verify reference data...")

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
