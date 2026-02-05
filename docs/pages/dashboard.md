# Dashboard Page Documentation

## Page Information

| Property | Value |
|----------|-------|
| **Page Name** | Dashboard |
| **File Path** | `/frontend/src/features/dashboard/DashboardPage.tsx` |
| **Route Path** | `/dashboard` (assumed based on naming convention) |
| **Purpose** | Overview of CRM performance with KPIs, charts, and recent activities |

---

## UI Components

### Custom Dashboard Components

| Component | File Path | Props | Description |
|-----------|-----------|-------|-------------|
| `NumberCard` | `/frontend/src/features/dashboard/components/NumberCard.tsx` | `title`, `value`, `subtitle?`, `icon?`, `trend?`, `className?` | Displays KPI metric with optional trend indicator and icon |
| `ChartCard` | `/frontend/src/features/dashboard/components/ChartCard.tsx` | `title`, `subtitle?`, `children`, `actions?`, `className?` | Container card for chart visualizations with title and optional actions |

### Shared UI Components

| Component | Import Path | Usage |
|-----------|-------------|-------|
| `Spinner` | `../../components/ui/Spinner` | Loading state indicator (size="lg") |

### NumberCard Props Interface

```typescript
interface NumberCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: React.ReactNode;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  className?: string;
}
```

### ChartCard Props Interface

```typescript
interface ChartCardProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}
```

---

## Helper Functions

| Function | Parameters | Return Type | Description |
|----------|------------|-------------|-------------|
| `findCardValue` | `cards: NumberCardData[], id: string` | `number` | Finds a number card by ID and returns its value (or 0 if not found) |
| `findCardChange` | `cards: NumberCardData[], id: string` | `number` | Finds a number card by ID and returns its change percentage (or 0 if not found) |

---

## Hooks Used

### Data Fetching Hooks

| Hook | Source File | Return Type | Description |
|------|-------------|-------------|-------------|
| `useDashboard` | `/frontend/src/hooks/useDashboard.ts` | `{ data, isLoading, error }` | Fetches full dashboard data (KPIs + charts) |
| `usePipelineFunnelChart` | `/frontend/src/hooks/useDashboard.ts` | `{ data }` | Fetches pipeline funnel chart data |
| `useLeadsBySourceChart` | `/frontend/src/hooks/useDashboard.ts` | `{ data }` | Fetches leads by source chart data |
| `useUserTimeline` | `/frontend/src/hooks/useActivities.ts` | `{ data }` | Fetches user's activity timeline |

### Hook Configurations

```typescript
// useDashboard configuration
{
  queryKey: ['dashboard', 'full'],
  queryFn: () => dashboardApi.getDashboard(),
  staleTime: 60 * 1000, // 1 minute
  enabled: isAuthenticated && !authLoading,
}

// usePipelineFunnelChart configuration
{
  queryKey: ['dashboard', 'charts', 'pipeline-funnel'],
  queryFn: () => dashboardApi.getPipelineFunnelChart(),
  enabled: isAuthenticated && !authLoading,
}

// useLeadsBySourceChart configuration
{
  queryKey: ['dashboard', 'charts', 'leads-by-source'],
  queryFn: () => dashboardApi.getLeadsBySourceChart(),
  enabled: isAuthenticated && !authLoading,
}

// useUserTimeline configuration
{
  queryKey: ['activities', 'user-timeline', activityTypes],
  queryFn: () => activitiesApi.getUserTimeline(50, true, activityTypes),
}
```

---

## API Calls Made

### Dashboard API (`/api/dashboard`)

| Endpoint | Method | API Function | Description |
|----------|--------|--------------|-------------|
| `/api/dashboard` | GET | `dashboardApi.getDashboard()` | Full dashboard data with number cards and charts |
| `/api/dashboard/charts/pipeline-funnel` | GET | `dashboardApi.getPipelineFunnelChart()` | Pipeline funnel chart data |
| `/api/dashboard/charts/leads-by-source` | GET | `dashboardApi.getLeadsBySourceChart()` | Leads by source chart data |

### Activities API (`/api/activities`)

| Endpoint | Method | API Function | Description |
|----------|--------|--------------|-------------|
| `/api/activities/timeline/user` | GET | `activitiesApi.getUserTimeline()` | User's activity timeline (limit: 50) |

### Response Types

```typescript
// DashboardResponse
interface DashboardResponse {
  number_cards: NumberCardData[];
  charts: ChartData[];
}

// NumberCardData
interface NumberCardData {
  id: string;
  label: string;
  value: number | string;
  format?: string | null;
  icon?: string | null;
  color: string;
  change?: number | null;
}

// ChartData
interface ChartData {
  type: 'bar' | 'line' | 'pie' | 'funnel' | 'area';
  title: string;
  data: ChartDataPoint[];
}

// TimelineResponse
interface TimelineResponse {
  items: TimelineItem[];
}
```

---

## Data Displayed

### KPI Number Cards

| Card ID | Title | Value Source | Trend Source | Icon |
|---------|-------|--------------|--------------|------|
| `total_contacts` | Total Contacts | `number_cards` | `change` field | Users/group SVG icon |
| `total_leads` | Total Leads | `number_cards` | `change` field | Trending up SVG icon |
| `open_opportunities` | Open Opportunities | `number_cards` | `change` field | Checkmark circle SVG icon |
| `total_revenue` | Total Revenue | `number_cards` (formatted with `formatCurrency`) | `change` field | Currency/dollar SVG icon |

### Charts

#### Pipeline Overview Chart
- **Title**: "Pipeline Overview"
- **Subtitle**: "Opportunities by stage"
- **Data Source**: `usePipelineFunnelChart` hook
- **Display**: Horizontal bar chart showing opportunity count and value per stage
- **Bar Color**: `bg-primary-500`
- **Data Fields**:
  - `stage` / `label`: Stage name
  - `count` / `value`: Number of opportunities
  - Value in currency format

#### Leads by Source Chart
- **Title**: "Leads by Source"
- **Subtitle**: "Where your leads come from"
- **Data Source**: `useLeadsBySourceChart` hook
- **Display**: Horizontal bar chart showing lead count per source
- **Bar Color**: `bg-green-500`
- **Data Fields**:
  - `source` / `label`: Lead source name
  - `count` / `value`: Number of leads

### Recent Activities Timeline
- **Title**: "Recent Activities"
- **Subtitle**: "Latest actions in your CRM"
- **Data Source**: `useUserTimeline` hook (first 10 items)
- **Display**: Vertical timeline with connected dots
- **Data Fields**:
  - `id`: Activity ID
  - `description`: Activity subject or description
  - `timestamp`: Scheduled, completed, or due date (formatted with `formatDate`)

---

## Interactive Elements

### Loading State
- **Spinner**: Full-height centered spinner displayed while `isLoadingDashboard` is true
- Uses `Spinner` component with `size="lg"`

### Error State
- **Error Message**: Red-styled alert box with error title and message
- Displays when dashboard fetch fails

### Visual Indicators
- **Trend Badges**: Show percentage change with color coding
  - Positive trends: Green text (`text-green-600`)
  - Negative trends: Red text (`text-red-600`)
  - Format: `+X%` or `-X%`

### Chart Bars
- **Progress Bars**: Visual representation of data proportions
  - Width calculated as percentage of max value
  - Rounded full style (`rounded-full`)
  - Animated width transitions

### Timeline
- **Connecting Lines**: Vertical lines between timeline items
- **Activity Icons**: Circular badges with plus icon
- **Empty State**: "No recent activities" message when timeline is empty

---

## Utility Functions Used

| Function | Import Path | Usage |
|----------|-------------|-------|
| `formatCurrency` | `../../utils` | Formats revenue values as currency |
| `formatDate` | `../../utils` | Formats activity timestamps for display |

---

## Component Layout Structure

```
DashboardPage
├── Header Section
│   ├── h1: "Dashboard"
│   └── p: "Overview of your CRM performance"
│
├── KPI Cards Grid (4 columns on lg, 2 on sm, 1 on mobile)
│   ├── NumberCard: Total Contacts
│   ├── NumberCard: Total Leads
│   ├── NumberCard: Open Opportunities
│   └── NumberCard: Total Revenue
│
├── Charts Section Grid (2 columns on lg, 1 on mobile)
│   ├── ChartCard: Pipeline Overview
│   │   └── Horizontal bar chart with stage breakdown
│   └── ChartCard: Leads by Source
│       └── Horizontal bar chart with source breakdown
│
└── Recent Activities Section
    └── ChartCard: Recent Activities
        └── Timeline list of activities
```

---

## CSS Classes / Styling

### Layout Classes
- `space-y-6`: Vertical spacing between sections
- `grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4`: Responsive KPI grid
- `grid grid-cols-1 lg:grid-cols-2`: Two-column chart layout

### Card Styling
- `bg-white rounded-lg shadow p-6 border border-gray-200`: NumberCard container
- `bg-white rounded-lg shadow border border-gray-200`: ChartCard container

### Typography
- `text-2xl font-bold text-gray-900`: Page title
- `text-sm text-gray-500`: Subtitles and descriptions
- `text-lg font-medium text-gray-900`: Chart titles

---

## State Management

The component uses TanStack Query for server state management:
- Automatic caching with 1-minute stale time for dashboard data
- Conditional fetching based on authentication state
- Query invalidation handled by hooks

---

## Error Handling

- Errors from `useDashboard` hook are caught and displayed
- Error message extracted using: `error instanceof Error ? error.message : String(error)`
- User-friendly error display with styled alert component

---

## Dependencies

### External Libraries
- `@tanstack/react-query`: Data fetching and caching
- `clsx`: Conditional CSS class composition

### Internal Dependencies
- Auth store (`useAuthStore`): Authentication state
- API client (`apiClient`): HTTP request handling
- Utils (`formatCurrency`, `formatDate`): Data formatting
