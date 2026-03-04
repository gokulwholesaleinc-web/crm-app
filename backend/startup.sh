#!/bin/bash

echo "Starting CRM App..."
echo "Starting FastAPI server on port 5000..."
exec uvicorn src.main:app --host 0.0.0.0 --port 5000
