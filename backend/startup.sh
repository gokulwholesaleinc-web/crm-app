#!/bin/bash
set -euo pipefail

echo "Starting CRM App..."

# Run pending Alembic migrations before the app boots. If this step
# fails, refuse to start uvicorn — a running server against a stale
# schema produces 500s on every new-column query (see 2026-04-24:
# PR #115 shipped migrations 009+010 and the Railway deploy served
# 500s until the migrations were applied manually).
#
# `alembic upgrade head` is idempotent — a no-op when the DB is
# already current — so this is safe to run on every boot.
echo "Running alembic migrations..."
alembic upgrade head

echo "Starting FastAPI server on port 5000..."
exec uvicorn src.main:app --host 0.0.0.0 --port 5000
