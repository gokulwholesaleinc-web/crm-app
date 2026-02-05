# CRM Application

## Overview
A modern CRM (Customer Relationship Management) application with AI assistant capabilities.

## Tech Stack
- **Frontend**: React 18 + TypeScript + Vite + TailwindCSS
- **Backend**: FastAPI (Python 3.11)
- **Database**: PostgreSQL with pgvector extension

## Project Structure
- `frontend/` - React + TypeScript + Vite application (port 5000)
- `backend/` - FastAPI Python application (port 8000)
- `tests/` - Unit, integration, and E2E tests

## Running the Application
The application runs with two workflows:
1. **Frontend**: Vite dev server on port 5000 (proxies /api to backend)
2. **Backend API**: FastAPI server on port 8000

## API Documentation
Backend API docs available at: http://localhost:8000/docs

## Key Features
- Contact and Company management
- Lead tracking and conversion
- Opportunity pipeline
- Activity tracking (calls, emails, meetings, tasks)
- Campaign management
- Dashboard with charts and metrics
- AI-powered assistant using OpenAI GPT-4

## Environment Variables
- `DATABASE_URL` - PostgreSQL connection string (auto-configured by Replit)
- `SECRET_KEY` - JWT authentication secret
- `OPENAI_API_KEY` - OpenAI API key for AI features

## Database
Uses Replit's built-in PostgreSQL database with pgvector extension for AI embeddings.
