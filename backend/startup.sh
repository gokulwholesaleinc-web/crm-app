#!/bin/bash
# Replit startup script
# Run this on every deployment to ensure database is migrated

echo "🚀 Starting CRM App..."

# Run migrations
echo "📋 Running database migrations..."
cd /home/runner/${REPL_SLUG}/backend || cd backend
python3 migrate_production.py

if [ $? -eq 0 ]; then
    echo "✅ Migrations completed successfully"
else
    echo "❌ Migrations failed - check logs above"
    exit 1
fi

# Start the application
echo "🌐 Starting FastAPI server..."
uvicorn src.main:app --host 0.0.0.0 --port 8000
