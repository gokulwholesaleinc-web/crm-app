# Leads Module Documentation

This document provides comprehensive documentation for the Leads feature in the CRM application.

## Table of Contents

1. [LeadsPage](#leadspage)
2. [LeadDetailPage](#leaddetailpage)
3. [Components](#components)
4. [Hooks](#hooks)
5. [API Reference](#api-reference)

---

## LeadsPage

### Overview

| Property | Value |
|----------|-------|
| **File Path** | `/frontend/src/features/leads/LeadsPage.tsx` |
| **Route Path** | `/leads` |
| **Purpose** | Display a paginated, searchable, and filterable list of all leads with CRUD operations |

### UI Components Used

| Component | Source | Purpose |
|-----------|--------|---------|
| `Button` | `../../components/ui` | Primary action buttons (Add Lead, Search, Pagination) |
| `Spinner` | `../../components/ui` | Loading state indicator |
| `Modal` | `../../components/ui` | Container for LeadForm (create/edit) |
| `ConfirmDialog` | `../../components/ui` | Delete confirmation dialog |
| `LeadForm` | `./components/LeadForm` | Form for creating/editing leads |
| `Link` | `react-router-dom` | Navigation to lead detail pages |
| `PlusIcon` | `@heroicons/react/24/outline` | Icon for Add Lead button |
| `ScoreIndicator` | Local component | Visual lead score display with progress bar |

### State Variables

| State | Type | Purpose |
|-------|------|---------|
| `searchQuery` | `string` | Current search input value |
| `statusFilter` | `string` | Selected status filter value |
| `currentPage` | `number` | Current pagination page |
| `showForm` | `boolean` | Controls form modal visibility |
| `editingLead` | `Lead \| null` | Lead being edited (null for create) |
| `deleteConfirm` | `{ isOpen: boolean; lead: Lead \| null }` | Delete confirmation state |

### Functions/Handlers

| Function | Purpose | Description |
|----------|---------|-------------|
| `handleSearch` | Search submission | Prevents default form submission, resets to page 1 |
| `handleDeleteClick` | Initiate delete | Opens delete confirmation dialog for selected lead |
| `handleDeleteConfirm` | Confirm delete | Executes lead deletion via mutation |
| `handleDeleteCancel` | Cancel delete | Closes delete confirmation dialog |
| `handleEdit` | Edit lead | Sets editing lead and opens form modal |
| `handleFormSubmit` | Create/Update | Submits form data to create or update lead |
| `handleFormCancel` | Cancel form | Closes form modal and resets editing state |
| `getInitialFormData` | Form initialization | Transforms lead data for form pre-population |
| `getScoreColor` | Utility | Returns color class based on lead score |

### Hooks Used

| Hook | Source | Purpose |
|------|--------|---------|
| `useState` | React | Local state management |
| `useLeads` | `../../hooks` | Fetch paginated leads with filters |
| `useCreateLead` | `../../hooks` | Mutation for creating leads |
| `useUpdateLead` | `../../hooks` | Mutation for updating leads |
| `useDeleteLead` | `../../hooks` | Mutation for deleting leads |

### API Calls

| Operation | Endpoint | Method | Trigger |
|-----------|----------|--------|---------|
| List Leads | `GET /api/leads` | GET | Page load, filter change, pagination |
| Create Lead | `POST /api/leads` | POST | Form submit (new lead) |
| Update Lead | `PATCH /api/leads/:id` | PATCH | Form submit (existing lead) |
| Delete Lead | `DELETE /api/leads/:id` | DELETE | Delete confirmation |

#### API Parameters (List Leads)

```typescript
{
  page: number;
  page_size: number;      // Default: 10
  search?: string;        // Search by name, email, or company
  status?: string;        // Filter by status
}
```

### Table Columns

| Column | Field | Description |
|--------|-------|-------------|
| Name | `first_name`, `last_name`, `email` | Clickable link to detail page, email below name |
| Company | `company_name` | Company name or '-' if empty |
| Status | `status` | Color-coded status badge |
| Score | `score` | Visual score indicator with progress bar (0-100) |
| Source | `source.name` | Lead source formatted label |
| Created | `created_at` | Formatted creation date |
| Actions | - | Edit and Delete buttons |

### Table Row Actions

| Action | Handler | Description |
|--------|---------|-------------|
| View | Click on name | Navigates to `/leads/:id` |
| Edit | `handleEdit` | Opens edit form modal |
| Delete | `handleDeleteClick` | Opens delete confirmation |

### Filter Options

#### Status Filter

| Value | Label |
|-------|-------|
| `''` | All Statuses |
| `new` | New |
| `contacted` | Contacted |
| `qualified` | Qualified |
| `unqualified` | Unqualified |
| `nurturing` | Nurturing |

### Pagination

- Page size: 10 items per page
- Shows current range and total count
- Previous/Next navigation buttons
- Disabled state when at boundaries

---

## LeadDetailPage

### Overview

| Property | Value |
|----------|-------|
| **File Path** | `/frontend/src/features/leads/LeadDetailPage.tsx` |
| **Route Path** | `/leads/:id` |
| **Purpose** | Display detailed lead information with edit, delete, and conversion capabilities |

### UI Components Used

| Component | Source | Purpose |
|-----------|--------|---------|
| `Button` | `../../components/ui` | Action buttons (Convert, Edit, Delete) |
| `Spinner` | `../../components/ui` | Loading state indicator |
| `Modal` | `../../components/ui` | Container for edit form |
| `ConfirmDialog` | `../../components/ui` | Delete confirmation dialog |
| `ConvertLeadModal` | `./components/ConvertLeadModal` | Lead conversion workflow |
| `LeadForm` | `./components/LeadForm` | Form for editing lead |
| `Link` | `react-router-dom` | Back navigation to leads list |

### State Variables

| State | Type | Purpose |
|-------|------|---------|
| `showConvertModal` | `boolean` | Controls convert modal visibility |
| `showEditForm` | `boolean` | Controls edit form visibility |
| `showDeleteConfirm` | `boolean` | Controls delete confirmation visibility |

### Functions/Handlers

| Function | Purpose | Description |
|----------|---------|-------------|
| `handleEditSubmit` | Update lead | Submits updated lead data via mutation |
| `getInitialFormData` | Form initialization | Transforms lead data for form pre-population |
| `handleDeleteConfirm` | Confirm delete | Executes deletion and navigates to leads list |
| `handleConvert` | Convert lead | Executes full lead conversion (contact + opportunity) |
| `getScoreColor` | Utility | Returns color class based on lead score |

### Hooks Used

| Hook | Source | Purpose |
|------|--------|---------|
| `useState` | React | Local state management |
| `useParams` | `react-router-dom` | Extract lead ID from URL |
| `useNavigate` | `react-router-dom` | Programmatic navigation |
| `useLead` | `../../hooks` | Fetch single lead by ID |
| `useDeleteLead` | `../../hooks` | Mutation for deleting lead |
| `useConvertLead` | `../../hooks` | Mutation for full lead conversion |
| `useUpdateLead` | `../../hooks` | Mutation for updating lead |

### API Calls

| Operation | Endpoint | Method | Trigger |
|-----------|----------|--------|---------|
| Get Lead | `GET /api/leads/:id` | GET | Page load |
| Update Lead | `PATCH /api/leads/:id` | PATCH | Edit form submit |
| Delete Lead | `DELETE /api/leads/:id` | DELETE | Delete confirmation |
| Convert Lead | `POST /api/leads/:id/convert/full` | POST | Conversion confirmation |

### Lead Details Displayed

| Field | Source | Description |
|-------|--------|-------------|
| Name | `first_name`, `last_name` | Full name as page title |
| Job Title & Company | `job_title`, `company_name` | Subtitle if both present |
| Lead Score | `score` | Large numeric display with circular progress |
| Email | `email` | Clickable mailto link |
| Phone | `phone` | Clickable tel link (formatted) |
| Company | `company_name` | Company name |
| Job Title | `job_title` | Position/role |
| Status | `status` | Color-coded badge |
| Source | `source.name` | Lead acquisition source |
| Description | `description` | Additional notes |
| Created | `created_at` | Creation timestamp |
| Last Updated | `updated_at` | Last modification timestamp |

### Lead Score Visual

The lead score is displayed with:
- Large numeric value (out of 100)
- Circular SVG progress indicator
- Color coding:
  - Green (80-100): High quality
  - Yellow (60-79): Medium quality
  - Orange (40-59): Low quality
  - Red (0-39): Poor quality

### Action Buttons

| Button | Condition | Action |
|--------|-----------|--------|
| Convert Lead | `status === 'qualified'` | Opens conversion modal |
| Edit | Always visible | Opens edit form modal |
| Delete | Always visible | Opens delete confirmation |

### Navigation Flows

| Action | Destination | Condition |
|--------|-------------|-----------|
| Back arrow | `/leads` | Always available |
| After delete | `/leads` | After successful deletion |
| After convert | `/contacts/:id` | If contact was created |
| After convert | `/opportunities` | If only opportunity created |
| After convert (fallback) | `/leads` | Default fallback |

---

## Components

### LeadForm

| Property | Value |
|----------|-------|
| **File Path** | `/frontend/src/features/leads/components/LeadForm.tsx` |
| **Purpose** | Reusable form for creating and editing leads |

#### Form Fields

| Section | Field | Type | Required | Validation |
|---------|-------|------|----------|------------|
| **Basic Information** | | | | |
| | First Name | text | Yes | Required |
| | Last Name | text | Yes | Required |
| | Email | email | Yes | Required, valid email pattern |
| | Phone | tel | No | None |
| **Work Information** | | | | |
| | Company | text | No | None |
| | Job Title | text | No | None |
| **Lead Information** | | | | |
| | Source | select | Yes | Required |
| | Status | select | Yes | Required |
| | Lead Score | number | No | Min: 0, Max: 100 |
| **Notes** | | | | |
| | Notes | textarea | No | None |

#### Source Options

| Value | Label |
|-------|-------|
| `website` | Website |
| `referral` | Referral |
| `social_media` | Social Media |
| `email_campaign` | Email Campaign |
| `cold_call` | Cold Call |
| `trade_show` | Trade Show |
| `other` | Other |

#### Status Options

| Value | Label |
|-------|-------|
| `new` | New |
| `contacted` | Contacted |
| `qualified` | Qualified |
| `unqualified` | Unqualified |
| `nurturing` | Nurturing |

#### Props Interface

```typescript
interface LeadFormProps {
  initialData?: Partial<LeadFormData>;
  onSubmit: (data: LeadFormData) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
  submitLabel?: string;
}
```

#### Form Data Interface

```typescript
interface LeadFormData {
  firstName: string;
  lastName: string;
  email: string;
  phone?: string;
  company?: string;
  jobTitle?: string;
  source: string;
  status: string;
  score?: number;
  notes?: string;
}
```

---

### ConvertLeadModal

| Property | Value |
|----------|-------|
| **File Path** | `/frontend/src/features/leads/components/ConvertLeadModal.tsx` |
| **Purpose** | Modal dialog for converting qualified leads to contacts/opportunities |

#### Props Interface

```typescript
interface ConvertLeadModalProps {
  isOpen: boolean;
  leadId: string;
  leadName: string;
  onClose: () => void;
  onConvert: (data: ConvertLeadFormData) => Promise<void>;
}
```

#### Conversion Form Fields

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| Create Contact | checkbox | `true` | No | Create a contact from lead info |
| Create Opportunity | checkbox | `false` | No | Create an opportunity |
| Opportunity Name | text | - | Conditional* | Name for the opportunity |
| Expected Value | number | `0` | No | Dollar value (min: 0) |
| Stage | select | `qualification` | No | Pipeline stage |

*Required when "Create Opportunity" is checked

#### Opportunity Stage Options

| Value | Label | Stage ID |
|-------|-------|----------|
| `qualification` | Qualification | 1 |
| `proposal` | Proposal | 2 |
| `negotiation` | Negotiation | 3 |
| `closed_won` | Closed Won | 4 |
| `closed_lost` | Closed Lost | 5 |

#### Conversion Flow

```
Lead (qualified status)
    |
    v
[Convert Lead Button]
    |
    v
ConvertLeadModal
    |
    +-- Create Contact? (checkbox)
    |
    +-- Create Opportunity? (checkbox)
    |       |
    |       +-- Opportunity Name
    |       +-- Expected Value
    |       +-- Stage
    |
    v
[Convert Lead]
    |
    v
API: POST /api/leads/:id/convert/full
    |
    v
Navigate to created entity
```

---

## Hooks

### useLeads

Fetches paginated list of leads with optional filters.

```typescript
function useLeads(filters?: LeadFilters): UseQueryResult<LeadListResponse>
```

### useLead

Fetches a single lead by ID.

```typescript
function useLead(id: number | undefined): UseQueryResult<Lead>
```

### useCreateLead

Mutation hook for creating new leads.

```typescript
function useCreateLead(): UseMutationResult<Lead, Error, LeadCreate>
```

### useUpdateLead

Mutation hook for updating existing leads.

```typescript
function useUpdateLead(): UseMutationResult<Lead, Error, { id: number; data: LeadUpdate }>
```

### useDeleteLead

Mutation hook for deleting leads.

```typescript
function useDeleteLead(): UseMutationResult<void, Error, number>
```

### useConvertLead

Mutation hook for full lead conversion (contact + company + opportunity).

```typescript
function useConvertLead(): UseMutationResult<ConversionResponse, Error, { leadId: number; data: LeadFullConversionRequest }>
```

#### Query Invalidation

On successful conversion, the following queries are invalidated:
- `leads` (list and detail)
- `contacts` (list)
- `companies` (list)
- `opportunities` (list)

---

## API Reference

### Base URL

```
/api/leads
```

### Endpoints

#### List Leads

```http
GET /api/leads
```

**Query Parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `page` | number | Page number (default: 1) |
| `page_size` | number | Items per page (default: 10) |
| `search` | string | Search by name, email, or company |
| `status` | string | Filter by status |

**Response:**

```typescript
interface LeadListResponse {
  items: Lead[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}
```

#### Get Lead

```http
GET /api/leads/:id
```

#### Create Lead

```http
POST /api/leads
```

**Request Body:**

```typescript
interface LeadCreate {
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  company_name?: string;
  job_title?: string;
  status: string;
  budget_currency: string;  // Required, e.g., "USD"
}
```

#### Update Lead

```http
PATCH /api/leads/:id
```

**Request Body:**

```typescript
interface LeadUpdate {
  first_name?: string;
  last_name?: string;
  email?: string;
  phone?: string;
  company_name?: string;
  job_title?: string;
  status?: string;
}
```

#### Delete Lead

```http
DELETE /api/leads/:id
```

#### Full Conversion

```http
POST /api/leads/:id/convert/full
```

**Request Body:**

```typescript
interface LeadFullConversionRequest {
  pipeline_stage_id: number;
  create_company: boolean;
}
```

**Response:**

```typescript
interface ConversionResponse {
  contact_id?: number;
  company_id?: number;
  opportunity_id?: number;
}
```

---

## Type Definitions

### Lead

```typescript
interface Lead {
  id: number;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  company_name?: string;
  job_title?: string;
  status: string;
  score: number;
  source?: LeadSource;
  description?: string;
  created_at: string;
  updated_at: string;
}
```

### LeadSource

```typescript
interface LeadSource {
  id: number;
  name: string;
  is_active: boolean;
}
```

---

## Utility Functions

### getStatusBadgeClasses

Returns CSS classes for status badge styling.

```typescript
getStatusBadgeClasses(status: string, type: 'lead'): string
```

### formatStatusLabel

Converts snake_case status to human-readable label.

```typescript
formatStatusLabel(status: string): string
```

### formatDate

Formats ISO date string to display format.

```typescript
formatDate(date: string): string
```

### formatPhoneNumber

Formats phone number for display.

```typescript
formatPhoneNumber(phone: string): string
```
