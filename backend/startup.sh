#!/bin/bash

echo "Starting CRM App..."

if [ -f "migrate_production.py" ]; then
    echo "Running database migrations..."
    python3 migrate_production.py
    if [ $? -ne 0 ]; then
        echo "❌ Migration failed! Aborting startup."
        exit 1
    fi
    echo "Migrations completed"
fi

echo "Starting FastAPI server on port 5000..."
exec uvicorn src.main:app --host 0.0.0.0 --port 5000
