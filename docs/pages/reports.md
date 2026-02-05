# Reports Page Documentation

## Page Information

| Property | Value |
|----------|-------|
| **Page Name** | ReportsPage |
| **File Path** | `/Users/harshvarma/crm-app/frontend/src/features/reports/ReportsPage.tsx` |
| **Route Path** | `/reports` (inferred from file location) |

## UI Components Used

### Custom Components

| Component | Import Path | Usage |
|-----------|-------------|-------|
| `Card` | `../../components/ui/Card` | Container for report content and conversion rate cards |
| `CardHeader` | `../../components/ui/Card` | Header for pipeline value section in revenue report |
| `CardBody` | `../../components/ui/Card` | Content area within cards |
| `Button` | `../../components/ui/Button` | Export CSV buttons in each report view |
| `Spinner` | `../../components/ui/Spinner` | Loading indicator while data is being fetched |

### Internal Components

| Component | Props | Description |
|-----------|-------|-------------|
| `ReportCard` | `title`, `description`, `icon`, `isActive`, `onClick` | Clickable card for report type selection in sidebar |

### Heroicons (External Icons)

| Icon | Import Path | Usage |
|------|-------------|-------|
| `ChartBarIcon` | `@heroicons/react/24/outline` | Header "last updated" indicator |
| `ArrowDownTrayIcon` | `@heroicons/react/24/outline` | Export CSV button icon |
| `FunnelIcon` | `@heroicons/react/24/outline` | Pipeline report icon, Open Opportunities icon |
| `UserGroupIcon` | `@heroicons/react/24/outline` | Lead Sources report icon |
| `CurrencyDollarIcon` | `@heroicons/react/24/outline` | Revenue Summary report icon, Total Revenue icon |
| `ArrowTrendingUpIcon` | `@heroicons/react/24/outline` | Conversion Rates report icon |

### Utility Functions

| Function | Import Path | Usage |
|----------|-------------|-------|
| `formatCurrency` | `../../utils` | Format monetary values in tables and cards |
| `formatDate` | `../../utils` | Format the "last updated" timestamp |

## Functions/Handlers

| Function | Type | Description |
|----------|------|-------------|
| `ReportsPage` | Component Function | Main page component that orchestrates report display |
| `ReportCard` | Functional Component | Renders individual report selection cards |
| `renderReportContent` | Internal Function | Renders the appropriate report view based on `activeReport` state |
| `setActiveReport` | State Setter | Updates which report is currently displayed |
| `onClick` (ReportCard) | Event Handler | Calls `setActiveReport` when a report card is clicked |

## Hooks Used

| Hook | Source | Purpose |
|------|--------|---------|
| `useState` | `react` | Manages `activeReport` state (default: 'pipeline') |
| `useDashboard` | `../../hooks` | Fetches dashboard data for revenue summary |
| `usePipelineFunnelChart` | `../../hooks` | Fetches pipeline/opportunity stage data |
| `useLeadsBySourceChart` | `../../hooks` | Fetches lead source distribution data |
| `useConversionRatesChart` | `../../hooks` | Fetches conversion rate metrics |

### State Variables

| State | Type | Default | Description |
|-------|------|---------|-------------|
| `activeReport` | `ReportType` | `'pipeline'` | Currently selected report type |

### Custom Type Definitions

```typescript
type ReportType = 'pipeline' | 'leads' | 'conversion' | 'revenue';

interface ReportCardProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  isActive: boolean;
  onClick: () => void;
}
```

## API Calls Made

All API calls are made via custom hooks that wrap React Query:

| Hook | API Endpoint (inferred) | Data Returned |
|------|------------------------|---------------|
| `useDashboard` | Dashboard metrics endpoint | `number_cards` array with `total_revenue`, `open_opportunities` |
| `usePipelineFunnelChart` | Pipeline chart endpoint | `data` array with stage, count, value fields |
| `useLeadsBySourceChart` | Leads by source endpoint | `data` array with source, count fields |
| `useConversionRatesChart` | Conversion rates endpoint | `data` array with label, value fields |

## Data Displayed

### Pipeline Report
| Field | Source | Format |
|-------|--------|--------|
| Stage Name | `pipelineData.data[].stage` or `label` | Text |
| Count | `pipelineData.data[].count` or `value` | Number |
| Value | `pipelineData.data[].value` | Currency (formatted) |
| % of Total | Calculated from count | Percentage |
| Total Row | Aggregated from all items | Count and Currency |

### Lead Sources Report
| Field | Source | Format |
|-------|--------|--------|
| Source Name | `leadsData.data[].source` or `label` | Text |
| Lead Count | `leadsData.data[].count` or `value` | Number |
| % of Total | Calculated from count | Percentage |

### Conversion Rates Report
| Field | Source | Format |
|-------|--------|--------|
| Metric Label | `conversionData.data[].label` | Text |
| Conversion Rate | `conversionData.data[].value` | Percentage (1 decimal) |

### Revenue Summary Report
| Field | Source | Format |
|-------|--------|--------|
| Total Revenue (Won) | `dashboardData.number_cards` with `id='total_revenue'` | Currency |
| Open Opportunities | `dashboardData.number_cards` with `id='open_opportunities'` | Number |
| Pipeline Value by Stage | `pipelineData.data[]` | Horizontal bar chart with currency |

## Interactive Elements

| Element | Type | Action | Description |
|---------|------|--------|-------------|
| Pipeline Report Card | `<button>` | `onClick={() => setActiveReport('pipeline')}` | Selects pipeline report view |
| Lead Sources Card | `<button>` | `onClick={() => setActiveReport('leads')}` | Selects leads by source report view |
| Conversion Rates Card | `<button>` | `onClick={() => setActiveReport('conversion')}` | Selects conversion rates report view |
| Revenue Summary Card | `<button>` | `onClick={() => setActiveReport('revenue')}` | Selects revenue summary report view |
| Export CSV Button (Pipeline) | `<Button>` | None (no handler attached) | Placeholder for export functionality |
| Export CSV Button (Leads) | `<Button>` | None (no handler attached) | Placeholder for export functionality |
| Export CSV Button (Conversion) | `<Button>` | None (no handler attached) | Placeholder for export functionality |
| Export CSV Button (Revenue) | `<Button>` | None (no handler attached) | Placeholder for export functionality |
| Table Rows | `<tr>` | `hover:bg-gray-50` | Visual hover effect on data rows |

**Note:** The "Export CSV" buttons are present but do not have click handlers implemented yet.

## Component Structure

```
ReportsPage
├── Page Header
│   ├── Title: "Reports"
│   ├── Description
│   └── Last Updated Indicator
└── Main Content Grid (1x4 on large screens)
    ├── Report Selection Sidebar (1 column)
    │   ├── ReportCard: Pipeline Report
    │   ├── ReportCard: Lead Sources
    │   ├── ReportCard: Conversion Rates
    │   └── ReportCard: Revenue Summary
    └── Report Content Area (3 columns)
        └── Card
            └── CardBody
                └── renderReportContent()
                    ├── Loading State (Spinner)
                    ├── Pipeline View
                    │   ├── Header with Export Button
                    │   └── Data Table (Stage, Count, Value, %)
                    ├── Leads View
                    │   ├── Header with Export Button
                    │   └── Data Table (Source, Leads, %)
                    ├── Conversion View
                    │   ├── Header with Export Button
                    │   └── Metric Cards Grid (3 columns)
                    └── Revenue View
                        ├── Header with Export Button
                        ├── Summary Cards (2 columns)
                        │   ├── Total Revenue Card
                        │   └── Open Opportunities Card
                        └── Pipeline Value by Stage Card
                            └── Horizontal Bar Chart
```

## Report Views Summary

| Report Type | Display Format | Key Metrics |
|-------------|---------------|-------------|
| Pipeline | Table with totals footer | Opportunities by stage with count, value, percentage |
| Lead Sources | Table | Leads grouped by source with count, percentage |
| Conversion | Grid of metric cards | Individual conversion rate percentages |
| Revenue | Summary cards + bar chart | Total revenue, open opportunities, pipeline value breakdown |
