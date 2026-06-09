# CRM Application Development Guidelines

## App Startup

To Start the app locally use Docker Compose

When restarting the computer make sure docker is running

Command to run the app: `docker compose up` (legacy `docker-compose up` also works)

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
- **Database**: PostgreSQL 16 (pgvector DB extension retained; pgvector pip package removed PR #281)
- **AI**: Removed PR #281 — DB tables preserved; re-enable by restoring src/ai/ + remounting the router
- **Deployment**: Docker Compose for local dev. **Production runs on Railway** (separate backend + frontend services) against **Neon Postgres** + **Cloudflare R2** — not compose.

## Project Structure
- `backend/` - FastAPI application
- `frontend/` - React + TypeScript + Vite application (tests via Vitest; `src/**/__tests__`)
- `tests/` - Backend pytest suite (unit + integration). Config lives at `tests/pytest.ini` (no root pytest.ini). No committed E2E suite.

## API Documentation
- Backend API: http://localhost:8000/docs
- Frontend: http://localhost:3000

## Key Patterns
- CRMNote Mixin: Shared note functionality across entities
- Document Conversion: Lead → Contact/Opportunity → Customer
- Dynamic Links: Polymorphic relationships for activities
- Dashboard Configuration: JSON-based chart and number card definitions

## Testing & Gates (read before writing or running tests)
- **The test DB is in-memory SQLite** (`tests/conftest.py`), not Postgres. Combined with the no-mock rule this means: JSONB columns need the `JSONB`-on-PG / `JSON`-on-SQLite `TypeDecorator` shim (see `onboarding/models.py`); and **Postgres-only features cannot be exercised by the suite** — `INSERT … ON CONFLICT`, `pg_try_advisory_lock`, `ARRAY.overlap()`, etc. Plan an explicit Postgres-backed path for anything that relies on them.
- **Always run gate commands with `backend/.venv`.** System `python3` is 3.9 (causes pytest ImportErrors) and global `ruff`/`pyright` differ from the pinned `ruff 0.5.7` / `pyright 1.1.408` → phantom failures. Don't rely on `echo $?` after a backgrounded gate; it can mask the real exit code.
- **Trio review before every deploy (hard rule):** `code-review` + `pr-review-toolkit:review-pr` + `security-review`.
- A 2–6s GitHub Actions failure is usually a billing/CI block, not your code — verify local gates pass and re-run rather than debugging green code.

## Migrations (Alembic)
- **Check for multiple heads before merging** — a multi-head state crashloops the backend on boot.
- Revision id is capped (~32 chars) and need not match the filename; keep ids short.

## Git Hygiene
- **Never `git add -A`** — stray untracked files get swept into commits/PRs. Stage explicit paths.

## Local Gotchas
- Local WeasyPrint PDF generation/tests on macOS need `DYLD_FALLBACK_LIBRARY_PATH` set for the native libs.
