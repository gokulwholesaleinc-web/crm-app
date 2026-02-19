# CRM Application

## Overview

A full-stack CRM (Customer Relationship Management) application for managing contacts, companies, leads, opportunities, activities, campaigns, and sales pipelines. The system includes AI-powered assistance (OpenAI GPT-4), white-label/multi-tenant support, Stripe payment integration, email campaigns with branded templates, role-based access control, workflow automation, and comprehensive reporting.

The backend is a FastAPI Python application with PostgreSQL (using pgvector for AI embeddings). The frontend is a React 18 + TypeScript SPA built with Vite. Everything runs via Docker Compose.

## User Preferences

Preferred communication style: Simple, everyday language.

- Always create a feature branch named `<name_of_feature>/features` and merge it before starting a new feature.
- Keep code DRY — search for existing methods before writing new ones.
- All new endpoints and methods must have one or more test cases that validate functionality without mocking anything.
- Always git push on feature completion. Keep commit messages detailed.
- Do not write unnecessary markdown files for commits and new features.
- Follow KISS coding principles — no spaghetti code.
- Use Docker Compose to manage services. Ask permission before adding new services like Redis, Celery, etc.
- Follow all rules in CLAUDE.md at all times.

## System Architecture

### Backend (FastAPI + Python 3.11+)

- **Framework**: FastAPI with async support throughout
- **Entry point**: `backend/src/main.py` — registers all routers, middleware, and lifespan events
- **Configuration**: `backend/src/config.py` using Pydantic Settings, reads from environment variables
- **Database layer**: `backend/src/database.py` — SQLAlchemy 2.0 async with `asyncpg` driver, `DeclarativeBase` for models
- **Migrations**: Alembic (`backend/alembic/`) plus a production migration script (`backend/migrate_production.py`) using raw asyncpg
- **Authentication**: JWT tokens via `python-jose`, password hashing with `passlib[bcrypt]`. Auth module at `src/auth/`
- **Rate limiting**: `slowapi` middleware
- **Multi-tenancy**: White-label support via `TenantMiddleware` — tenant resolution, branding, and per-tenant settings stored in DB (`src/whitelabel/`)

### Backend Module Structure

Each domain feature lives in its own package under `backend/src/`:

| Module | Purpose |
|---|---|
| `auth` | User registration, login, JWT tokens, password security |
| `contacts` | Contact CRUD |
| `companies` | Company CRUD |
| `leads` | Lead CRUD, lead scoring (`leads/scoring.py`) |
| `opportunities` | Opportunity CRUD, pipeline stages |
| `activities` | Activity/task tracking |
| `campaigns` | Marketing campaigns, email templates, campaign steps |
| `dashboard` | KPI number cards, charts |
| `ai` | OpenAI chat assistant, embeddings, RAG, action execution, learning system |
| `whitelabel` | Multi-tenant support, tenant settings, branding |
| `import_export` | CSV import/export |
| `notes` | Notes CRUD |
| `workflows` | Workflow automation rules and execution |
| `attachments` | File upload/download |
| `dedup` | Duplicate detection and merge |
| `email` | Email sending (Resend API), branded templates, PDF generation, tracking |
| `notifications` | In-app notification system |
| `filters` | Saved filters with advanced filter operators |
| `reports` | Report execution, templates, CSV export |
| `audit` | Audit logging for entity changes |
| `comments` | Team collaboration comments with @mentions |
| `roles` | RBAC — roles, permissions, user-role assignment |
| `webhooks` | Outgoing webhook delivery |
| `assignment` | Lead auto-assignment (round-robin, load-balance) |
| `sequences` | Email/outreach sequences with enrollment |
| `quotes` | Quotes with line items, product bundles, public view, e-sign |
| `proposals` | Proposals with templates, public view, AI generation |
| `payments` | Stripe integration — products, prices, payments, subscriptions |
| `admin` | Admin dashboard — user management, system stats |
| `core` | Shared models (Note, Tag, EntityTag, EntityShare), filtering engine, caching, currencies, sharing, rate limiting |
| `events` | Internal event bus for cross-module communication |

### Frontend (React 18 + TypeScript + Vite)

- **Build tool**: Vite with React plugin, dev server on port 5000
- **Styling**: Tailwind CSS 3.4 with dark mode (`class` strategy), CSS custom properties for white-label theming
- **State management**: Zustand for auth state, TanStack React Query for server state
- **Routing**: React Router DOM v6
- **UI components**: Headless UI, Heroicons, react-hot-toast, react-hook-form
- **Drag & drop**: @dnd-kit for Kanban-style pipeline views
- **Charts**: Recharts
- **HTTP client**: Axios with proxy to backend (`/api` → `localhost:8000`)
- **Path aliases**: `@/`, `@components/`, `@features/`, `@hooks/`, `@api/`, `@store/`, `@types/` configured in both tsconfig and vite config
- **Code splitting**: Manual chunks for vendor, query, headlessui, axios, date-fns, dndkit, recharts

### Database (PostgreSQL 16 + pgvector)

- Async SQLAlchemy 2.0 with `asyncpg` driver
- pgvector extension for AI embedding similarity search
- SSL auto-configured for remote databases (e.g., NeonDB)
- In-memory SQLite with `aiosqlite` used for tests
- Seed data script at `backend/src/seed.py` (idempotent, controlled by `SEED_ON_STARTUP` env var)
- Models use SQLAlchemy `DeclarativeBase` with naming conventions for constraints

### Testing

- **Framework**: pytest + pytest-asyncio
- **Location**: `tests/` directory with `tests/unit/` subdirectory
- **Database**: In-memory SQLite via aiosqlite (no PostgreSQL needed for tests)
- **HTTP client**: httpx `AsyncClient` with ASGI transport
- **Key rule**: No mocking — all tests use real database operations
- **Fixtures**: Shared fixtures in `tests/conftest.py` for db sessions, test users, test entities, auth headers
- **Coverage**: Tests cover all major modules — auth, CRUD for all entities, AI, payments, proposals, quotes, campaigns, audit, RBAC, data isolation, events, notifications, caching, filtering, import/export

### Key Design Patterns

- **Router/Service/Model pattern**: Each module has a router (FastAPI endpoints), optional service layer, SQLAlchemy models, and Pydantic schemas
- **Event-driven**: Internal event bus (`src/events/`) for cross-cutting concerns (notifications, webhooks, audit logging)
- **RBAC with data isolation**: Sales reps see only their own data; managers and admins see all. Sharing system allows granting access to specific records.
- **Caching**: In-memory TTL cache for reference data (tags, lead sources, pipeline stages, roles, tenant settings)
- **Advanced filtering**: Generic filter engine (`src/core/filtering.py`) with operators like eq, neq, contains, gt, lt, etc., applied across all entity list endpoints

## External Dependencies

### Third-Party Services

| Service | Purpose | Config |
|---|---|---|
| **OpenAI** | GPT-4 for AI assistant chat, text-embedding-3-small for RAG embeddings | `OPENAI_API_KEY` env var |
| **Stripe** | Payment processing — products, prices, subscriptions, checkout sessions, webhooks | `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` |
| **Resend** | Transactional email delivery | `RESEND_API_KEY`, `EMAIL_FROM` |
| **PostgreSQL 16** | Primary database with pgvector extension | `DATABASE_URL` env var |

### Key Python Packages

- `fastapi` + `uvicorn` — Web framework and ASGI server
- `sqlalchemy[asyncio]` + `asyncpg` — Async ORM and PostgreSQL driver
- `alembic` — Database migrations
- `pgvector` — Vector similarity search for AI embeddings
- `python-jose` + `passlib` — JWT auth and password hashing
- `openai` — OpenAI API client
- `stripe` — Stripe API client
- `resend` — Email service client
- `slowapi` — Rate limiting
- `pydantic` + `pydantic-settings` — Validation and configuration
- `httpx` — Async HTTP client (used in tests and internal calls)

### Key Frontend Packages

- `react` + `react-dom` — UI framework
- `react-router-dom` — Client-side routing
- `@tanstack/react-query` — Server state management
- `zustand` — Client state management
- `axios` — HTTP client
- `tailwindcss` — Utility-first CSS
- `@headlessui/react` — Accessible UI primitives
- `@heroicons/react` — Icon set
- `@dnd-kit/core` + `@dnd-kit/sortable` — Drag and drop
- `recharts` — Charts and data visualization
- `react-hook-form` — Form handling
- `react-hot-toast` — Toast notifications
- `date-fns` — Date utilities