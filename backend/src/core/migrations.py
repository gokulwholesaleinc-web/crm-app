"""Production schema migrations runner.

Runs idempotent DDL and data migrations at startup via raw asyncpg (no ORM).
Called from the lifespan handler in main.py via _init_database().
"""

import logging
import os

from src.config import settings

logger = logging.getLogger(__name__)


async def _run_production_migrations():
    """Run idempotent schema migrations using raw asyncpg (no ORM)."""
    import asyncpg

    admin_emails = [
        e.strip() for e in os.getenv("ADMIN_EMAILS", "admin@admin.com").split(",") if e.strip()
    ]

    db_url = settings.db_url
    if db_url.startswith("postgresql+asyncpg://"):
        db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    if "?sslmode=" in db_url:
        db_url = db_url.split("?")[0]

    try:
        conn = await asyncpg.connect(db_url)
        try:
            await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(50) DEFAULT 'sales_rep' NOT NULL")
            placeholders = ", ".join(f"${i+1}" for i in range(len(admin_emails)))
            await conn.execute(f"""
                UPDATE users SET role = 'admin', is_superuser = true
                WHERE email IN ({placeholders})
                AND (role != 'admin' OR is_superuser = false)
            """, *admin_emails)
            await conn.execute(f"""
                INSERT INTO user_roles (user_id, role_id, created_at, updated_at)
                SELECT u.id, r.id, NOW(), NOW()
                FROM users u, roles r
                WHERE u.email IN ({placeholders})
                AND r.name = 'admin'
                AND NOT EXISTS (
                    SELECT 1 FROM user_roles ur WHERE ur.user_id = u.id AND ur.role_id = r.id
                )
            """, *admin_emails)

            # Unique constraints and missing indexes
            for idx_sql in [
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_contacts_unique_email ON contacts(email) WHERE email IS NOT NULL",
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_companies_unique_name_owner ON companies(name, owner_id)",
                "CREATE INDEX IF NOT EXISTS ix_companies_status ON companies(status)",
                "CREATE INDEX IF NOT EXISTS ix_companies_industry ON companies(industry)",
                "CREATE INDEX IF NOT EXISTS ix_contacts_status ON contacts(status)",
                "CREATE INDEX IF NOT EXISTS ix_activities_entity ON activities(entity_type, entity_id)",
            ]:
                try:
                    await conn.execute(idx_sql)
                except asyncpg.PostgresError as exc:
                    logger.warning("Migration DDL skipped: %s", exc)

            column_migrations = [
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS sales_code VARCHAR(100)",
                "CREATE INDEX IF NOT EXISTS ix_leads_sales_code ON leads(sales_code)",
                "ALTER TABLE contacts ADD COLUMN IF NOT EXISTS sales_code VARCHAR(100)",
                "CREATE INDEX IF NOT EXISTS ix_contacts_sales_code ON contacts(sales_code)",
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS segment VARCHAR(100)",
                "CREATE INDEX IF NOT EXISTS ix_companies_segment ON companies(segment)",
                "ALTER TABLE proposal_templates ADD COLUMN IF NOT EXISTS body TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE proposal_templates ADD COLUMN IF NOT EXISTS legal_terms TEXT",
                "ALTER TABLE proposal_templates ADD COLUMN IF NOT EXISTS is_default BOOLEAN DEFAULT FALSE",
                "ALTER TABLE proposal_templates ADD COLUMN IF NOT EXISTS owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
                "ALTER TABLE attachments ADD COLUMN IF NOT EXISTS category VARCHAR(50)",
                "ALTER TABLE saved_filters ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT FALSE",
                "ALTER TABLE saved_reports ADD COLUMN IF NOT EXISTS schedule VARCHAR(20)",
                "ALTER TABLE saved_reports ADD COLUMN IF NOT EXISTS recipients TEXT",
                "ALTER TABLE leads ADD COLUMN IF NOT EXISTS pipeline_stage_id INTEGER REFERENCES pipeline_stages(id) ON DELETE SET NULL",
                "CREATE INDEX IF NOT EXISTS ix_leads_pipeline_stage_id ON leads(pipeline_stage_id)",
                "ALTER TABLE pipeline_stages ADD COLUMN IF NOT EXISTS pipeline_type VARCHAR(20) DEFAULT 'opportunity'",
                "CREATE INDEX IF NOT EXISTS ix_pipeline_stages_pipeline_type ON pipeline_stages(pipeline_type)",
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS link_creative_tier VARCHAR(10)",
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS sow_url VARCHAR(500)",
                "ALTER TABLE companies ADD COLUMN IF NOT EXISTS account_manager VARCHAR(255)",
                "ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS retry_count INTEGER DEFAULT 0 NOT NULL",
                "ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ",
                # Infrastructure buildout: campaign multi-step execution
                "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS current_step INTEGER DEFAULT 0",
                "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS next_step_at TIMESTAMPTZ",
                "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS is_executing BOOLEAN DEFAULT FALSE",
                # Campaign member tracking: Date → DateTime
                "ALTER TABLE campaign_members ALTER COLUMN sent_at TYPE TIMESTAMPTZ USING sent_at::TIMESTAMPTZ",
                "ALTER TABLE campaign_members ALTER COLUMN responded_at TYPE TIMESTAMPTZ USING responded_at::TIMESTAMPTZ",
                "ALTER TABLE campaign_members ALTER COLUMN converted_at TYPE TIMESTAMPTZ USING converted_at::TIMESTAMPTZ",
                # Scheduled report delivery
                "ALTER TABLE saved_reports ADD COLUMN IF NOT EXISTS last_sent_at TIMESTAMPTZ",
                # Meta integration: Instagram fields
                "ALTER TABLE company_meta_data ADD COLUMN IF NOT EXISTS instagram_id VARCHAR(100)",
                "ALTER TABLE company_meta_data ADD COLUMN IF NOT EXISTS instagram_username VARCHAR(255)",
                "ALTER TABLE company_meta_data ADD COLUMN IF NOT EXISTS instagram_followers INTEGER",
                "ALTER TABLE company_meta_data ADD COLUMN IF NOT EXISTS instagram_media_count INTEGER",
                # Stripe invoice tracking
                "ALTER TABLE payments ADD COLUMN IF NOT EXISTS stripe_invoice_id VARCHAR(255)",
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_payments_stripe_invoice_id ON payments(stripe_invoice_id) WHERE stripe_invoice_id IS NOT NULL",
                # Email logging: new columns on email_queue
                "ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS from_email VARCHAR(255)",
                "ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS cc TEXT",
                "ALTER TABLE email_queue ADD COLUMN IF NOT EXISTS bcc TEXT",
                # Google OAuth sign-in: identity columns + nullable password
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS google_sub VARCHAR(255)",
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_google_sub ON users(google_sub) WHERE google_sub IS NOT NULL",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(20) NOT NULL DEFAULT 'password'",
                "ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL",
                # Audit Session 2: unguessable public tokens on sales docs
                "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS public_token VARCHAR(64)",
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_quotes_public_token ON quotes(public_token) WHERE public_token IS NOT NULL",
                "ALTER TABLE proposals ADD COLUMN IF NOT EXISTS public_token VARCHAR(64)",
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_proposals_public_token ON proposals(public_token) WHERE public_token IS NOT NULL",
                # Audit Session 2: relax subscriptions.price_id so webhook-driven
                # subscription creation (no matching local Price row) can insert
                "ALTER TABLE subscriptions ALTER COLUMN price_id DROP NOT NULL",
                # Lead import: allow company-only leads without a contact name
                "ALTER TABLE leads ALTER COLUMN first_name DROP NOT NULL",
                "ALTER TABLE leads ALTER COLUMN last_name DROP NOT NULL",
                # User approval gate
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS is_approved BOOLEAN NOT NULL DEFAULT TRUE",
            ]
            for sql in column_migrations:
                try:
                    await conn.execute(sql)
                except asyncpg.PostgresError as exc:
                    logger.warning("Column migration skipped: %s", exc)

            # User approval gate: rejected emails block list
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS rejected_access_emails (
                        id SERIAL PRIMARY KEY,
                        email VARCHAR(255) NOT NULL,
                        rejected_by_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                        rejected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        reason TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                await conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_rejected_access_emails_email ON rejected_access_emails(email)"
                )
            except asyncpg.PostgresError as exc:
                logger.warning("Failed to create rejected_access_emails table: %s", exc)

            # Audit Session 2: Stripe webhook idempotency log
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS webhook_events (
                        id SERIAL PRIMARY KEY,
                        event_id VARCHAR(255) NOT NULL,
                        event_type VARCHAR(100) NOT NULL,
                        received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                await conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_webhook_events_event_id ON webhook_events(event_id)"
                )
            except asyncpg.PostgresError as exc:
                logger.warning("Failed to create webhook_events table: %s", exc)

            # Audit Session 2: backfill public_token on any pre-existing quote
            # / proposal rows that pre-date the column. Per-row UPDATE so each
            # token is unique. Prod row count is small at time of the fix.
            try:
                import secrets as _secrets
                quote_rows = await conn.fetch(
                    "SELECT id FROM quotes WHERE public_token IS NULL"
                )
                for row in quote_rows:
                    await conn.execute(
                        "UPDATE quotes SET public_token = $1 WHERE id = $2",
                        _secrets.token_urlsafe(32), row["id"],
                    )
                proposal_rows = await conn.fetch(
                    "SELECT id FROM proposals WHERE public_token IS NULL"
                )
                for row in proposal_rows:
                    await conn.execute(
                        "UPDATE proposals SET public_token = $1 WHERE id = $2",
                        _secrets.token_urlsafe(32), row["id"],
                    )
            except Exception:
                # Broad catch: backfill walks rows and can hit data-shape
                # surprises; log the full traceback so we can diagnose.
                logger.exception("Failed to backfill public_token on quotes/proposals")

            # Create inbound_emails table if it doesn't exist
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS inbound_emails (
                        id SERIAL PRIMARY KEY,
                        resend_email_id VARCHAR(255) UNIQUE NOT NULL,
                        from_email VARCHAR(255) NOT NULL,
                        to_email VARCHAR(255) NOT NULL,
                        cc TEXT,
                        bcc TEXT,
                        subject VARCHAR(500) NOT NULL,
                        body_text TEXT,
                        body_html TEXT,
                        message_id VARCHAR(500),
                        in_reply_to VARCHAR(500),
                        attachments JSONB,
                        entity_type VARCHAR(50),
                        entity_id INTEGER,
                        received_at TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                await conn.execute("CREATE INDEX IF NOT EXISTS ix_inbound_emails_entity ON inbound_emails(entity_type, entity_id)")
                await conn.execute("CREATE INDEX IF NOT EXISTS ix_inbound_emails_from ON inbound_emails(from_email)")
            except asyncpg.PostgresError as exc:
                logger.warning("Failed to create inbound_emails table: %s", exc)

            # Create email_settings table if it doesn't exist
            try:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS email_settings (
                        id SERIAL PRIMARY KEY,
                        daily_send_limit INTEGER NOT NULL DEFAULT 200,
                        warmup_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                        warmup_start_date DATE,
                        warmup_target_daily INTEGER NOT NULL DEFAULT 200,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
            except asyncpg.PostgresError as exc:
                logger.warning("Failed to create email_settings table: %s", exc)

            try:
                await conn.execute("""
                    UPDATE pipeline_stages SET pipeline_type = 'lead'
                    WHERE LOWER(name) IN ('new', 'contacted', 'qualified', 'nurturing', 'unqualified', 'converted')
                    AND pipeline_type != 'lead'
                """)
            except asyncpg.PostgresError as exc:
                logger.warning("Failed to update pipeline_stages pipeline_type: %s", exc)

            print("Production migrations completed successfully")
        finally:
            await conn.close()
    except Exception:
        # Broad catch: outermost wrapper; connection + any unexpected
        # failure. Non-fatal because app can serve cached/existing schema;
        # log the traceback so we can still see what broke.
        logger.exception("Production migration error (non-fatal)")
