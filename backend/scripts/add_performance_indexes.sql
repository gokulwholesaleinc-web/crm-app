-- Performance indexes migration
-- Run via: docker compose exec db psql -U <user> -d <db> -f /scripts/add_performance_indexes.sql
-- Or: docker compose exec backend python scripts/run_migration.py

-- Index on created_at for all entity tables (used in ORDER BY on every list endpoint)
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_contacts_created_at ON contacts (created_at);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_leads_created_at ON leads (created_at);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_opportunities_created_at ON opportunities (created_at);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_companies_created_at ON companies (created_at);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_activities_created_at ON activities (created_at);

-- Composite indexes for common query pattern: filter by owner + sort by created_at
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_contacts_owner_created ON contacts (owner_id, created_at);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_leads_owner_created ON leads (owner_id, created_at);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_opportunities_owner_created ON opportunities (owner_id, created_at);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_companies_owner_created ON companies (owner_id, created_at);
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_activities_owner_created ON activities (owner_id, created_at);
