# CRM Application - Page Documentation

This directory contains detailed documentation for every page in the CRM application frontend.

## Pages Index

| Page | Route | Description |
|------|-------|-------------|
| [Auth](./auth.md) | `/login`, `/register` | User authentication pages |
| [Dashboard](./dashboard.md) | `/` | Main dashboard with KPIs and charts |
| [Contacts](./contacts.md) | `/contacts`, `/contacts/:id` | Contact management |
| [Companies](./companies.md) | `/companies`, `/companies/:id` | Company management |
| [Leads](./leads.md) | `/leads`, `/leads/:id` | Lead tracking and conversion |
| [Opportunities](./opportunities.md) | `/opportunities` | Sales pipeline with Kanban board |
| [Activities](./activities.md) | `/activities` | Activity tracking (calls, emails, meetings, tasks) |
| [Campaigns](./campaigns.md) | `/campaigns`, `/campaigns/:id` | Marketing campaign management |
| [AI Assistant](./ai-assistant.md) | `/ai-assistant` | AI-powered CRM assistant |
| [Reports](./reports.md) | `/reports` | Analytics and reporting |
| [Settings](./settings.md) | `/settings` | User settings and profile |

## Documentation Structure

Each page document includes:

1. **Page Overview** - Name, file path, route path
2. **UI Components** - All React components used
3. **Functions/Handlers** - Event handlers and utility functions
4. **Hooks Used** - React hooks and custom hooks
5. **API Calls** - Backend endpoints called
6. **Form Fields** - Input fields with validation rules (where applicable)
7. **Navigation Flows** - User journey and redirects

## Quick Reference

### Authentication
- Login: `demo@demo.com` / `demo123`

### Main Features
- **Contacts/Companies**: Full CRUD with search and filters
- **Leads**: Scoring, status tracking, conversion to Contact/Opportunity
- **Opportunities**: Kanban board with drag-drop, pipeline stages
- **Activities**: Calls, emails, meetings, tasks, notes with timeline
- **Campaigns**: Member management, metrics tracking
- **AI Assistant**: Chat, recommendations, daily summaries
- **Reports**: Pipeline, leads, conversion, revenue analytics

### Tech Stack (Frontend)
- React 18 + TypeScript
- TanStack Query (data fetching)
- Zustand (state management)
- React Hook Form (forms)
- Tailwind CSS (styling)
- Headless UI (modals, dialogs)
- DnD Kit (drag and drop)

## File Structure

```
frontend/src/
├── features/
│   ├── auth/           # LoginPage, RegisterPage
│   ├── dashboard/      # DashboardPage
│   ├── contacts/       # ContactsPage, ContactDetailPage
│   ├── companies/      # CompaniesPage, CompanyDetailPage
│   ├── leads/          # LeadsPage, LeadDetailPage
│   ├── opportunities/  # OpportunitiesPage, KanbanBoard
│   ├── activities/     # ActivitiesPage
│   ├── campaigns/      # CampaignsPage, CampaignDetailPage
│   ├── ai-assistant/   # AIAssistantPage
│   ├── reports/        # ReportsPage
│   └── settings/       # SettingsPage
├── components/
│   ├── ui/             # Shared UI components
│   ├── forms/          # Form components
│   └── layout/         # Layout, Header, Sidebar
├── hooks/              # Custom React hooks
├── api/                # API client modules
├── store/              # Zustand stores
└── types/              # TypeScript type definitions
```
