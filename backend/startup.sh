#!/bin/bash

echo "Starting CRM App..."

pip install -r requirements.txt

# Run migrations if script exists
if [ -f "migrate_production.py" ]; then
    echo "Running database migrations..."
    python3 migrate_production.py
    if [ $? -eq 0 ]; then
        echo "Migrations completed successfully"
    else
        echo "Migrations failed - check logs above"
    fi
fi

# Start the application on port 5000 for Replit
echo "Starting FastAPI server..."
uvicorn src.main:app --host 0.0.0.0 --port 5000
