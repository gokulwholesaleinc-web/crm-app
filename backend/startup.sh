#!/bin/bash

echo "Starting CRM App..."

if [ -f "migrate_production.py" ]; then
    echo "Running database migrations..."
    python3 migrate_production.py
    echo "Migrations completed"
fi

echo "Starting FastAPI server..."
exec uvicorn src.main:app --host 0.0.0.0 --port 5000
