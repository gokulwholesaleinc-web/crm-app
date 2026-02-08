# CRM Application Development Guidelines

## App Startup

To Start the app use docker compose

When restarting the computer make sure docker is running

Command to run the app: `docker-compose up`

## Development Rules

Then to Make new features always ensure we make a feature branch

This branch will be called `<name_of_feature>/features` and then merge it before starting new feature

Ensure to keep the code DRY and always read and search for related methods before composing them for the app here.

ALL NEW ENDPOINTS AND METHODS MUST HAVE ONE OR MORE TEST CASES TO VALIDATE FUNCTIONALITY AND MUST NOT MOCK ANYTHING.

ALWAYS GIT PUSH On feature completion here and follow the KISS Coding principles to ensure no spaghetti code here.

Keep Commit Messages Detailed and MUST NOT WRITE UNNECESSARY MD Files for Commits and new Features.

Use Docker compose to manage new services here and always ask permission before considering to add or create new services like Redis, Celery, Etc.

ALWAYS FOLLOW THE RULES HERE

## Database Connection

Database credentials are stored securely in environment variables.
See .env.example for required variables: DATABASE_URL

## Tech Stack
- **Backend**: FastAPI (Python 3.11+)
- **Frontend**: React 18 + TypeScript + Vite
- **Database**: PostgreSQL 16 with pgvector extension
- **AI**: OpenAI GPT-4 for assistant, text-embedding-3-small for RAG
- **Deployment**: Docker Compose

## Project Structure
- `backend/` - FastAPI application
- `frontend/` - React + TypeScript + Vite application
- `tests/` - Unit, integration, and E2E tests

## API Documentation
- Backend API: http://localhost:8000/docs
- Frontend: http://localhost:3000

## Key Patterns
- CRMNote Mixin: Shared note functionality across entities
- Document Conversion: Lead → Contact/Opportunity → Customer
- Dynamic Links: Polymorphic relationships for activities
- Dashboard Configuration: JSON-based chart and number card definitions
