# CRM Application Development Guidelines

## App Startup
- Use `docker-compose up` to start
- Ensure Docker is running after computer restart

## Development Rules
1. **Feature Branches** - Create `<name_of_feature>/features` branch, merge before starting new feature
2. **DRY Code** - Always search for existing methods before writing new ones
3. **Testing** - All new endpoints/methods MUST have test cases (no mocking)
4. **Git Push** - Push on feature completion, follow KISS principles
5. **Commit Messages** - Keep detailed, NO unnecessary MD files
6. **New Services** - Ask permission before adding Redis, Celery, etc.

## Database
- Credentials in environment variables (see .env.example for DATABASE_URL)

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
