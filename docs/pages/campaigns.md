# Campaigns Feature Documentation

## Overview

The Campaigns feature provides comprehensive marketing campaign management functionality, including campaign creation, editing, deletion, member management, and performance tracking metrics.

---

## Pages

### 1. CampaignsPage

**File Path:** `/frontend/src/features/campaigns/CampaignsPage.tsx`

**Route Path:** `/campaigns`

**Description:** A list view page displaying all marketing campaigns in a card-based grid layout with filtering, pagination, and CRUD operations.

#### UI Components Used

| Component | Source | Purpose |
|-----------|--------|---------|
| `Button` | `../../components/ui` | Action buttons (New Campaign, filters, pagination) |
| `Select` | `../../components/ui` | Filter dropdowns for status and type |
| `Spinner` | `../../components/ui` | Loading state indicator |
| `Modal` | `../../components/ui` | Campaign form modal for create/edit |
| `ConfirmDialog` | `../../components/ui` | Delete confirmation dialog |
| `CampaignForm` | `./components/CampaignForm` | Form component for campaign data entry |
| `CampaignCard` | Internal component | Individual campaign display card |

**Icons Used (from @heroicons/react/24/outline):**
- `PlusIcon` - New campaign button
- `FunnelIcon` - Filter toggle button
- `MegaphoneIcon` - Empty state illustration
- `ChartBarIcon` - Response metrics icon
- `UsersIcon` - Sent count icon
- `CurrencyDollarIcon` - Revenue icon

#### State Management

| State Variable | Type | Purpose |
|----------------|------|---------|
| `showFilters` | `boolean` | Toggle visibility of filter panel |
| `showForm` | `boolean` | Toggle visibility of campaign form modal |
| `editingCampaign` | `Campaign \| null` | Currently editing campaign (null for create mode) |
| `deleteConfirm` | `{ isOpen: boolean; campaign: Campaign \| null }` | Delete confirmation dialog state |

#### Functions and Handlers

| Function | Purpose | Description |
|----------|---------|-------------|
| `updateFilter(key, value)` | Filter Management | Updates URL search params for filtering; resets page to 1 when filter changes |
| `handleDeleteClick(campaign)` | Delete Initiation | Opens delete confirmation dialog with selected campaign |
| `handleDeleteConfirm()` | Delete Execution | Executes campaign deletion via mutation |
| `handleDeleteCancel()` | Delete Cancellation | Closes delete confirmation dialog |
| `handleEdit(campaign)` | Edit Initiation | Sets editing campaign and opens form modal |
| `handleFormSubmit(data)` | Form Submission | Creates new campaign or updates existing based on `editingCampaign` state |
| `handleFormCancel()` | Form Cancellation | Closes form modal and resets editing state |

#### Hooks Used

| Hook | Source | Purpose |
|------|--------|---------|
| `useNavigate` | `react-router-dom` | Programmatic navigation to campaign detail pages |
| `useSearchParams` | `react-router-dom` | URL-based filter state management |
| `useState` | `react` | Local component state |
| `useMemo` | `react` | Memoized filter object computation |
| `useCampaigns` | `../../hooks/useCampaigns` | Fetch paginated campaign list |
| `useCreateCampaign` | `../../hooks/useCampaigns` | Create campaign mutation |
| `useUpdateCampaign` | `../../hooks/useCampaigns` | Update campaign mutation |
| `useDeleteCampaign` | `../../hooks/useCampaigns` | Delete campaign mutation |

#### API Calls

| API Call | Endpoint | Method | Trigger |
|----------|----------|--------|---------|
| List Campaigns | `GET /api/campaigns` | GET | Page load, filter change |
| Create Campaign | `POST /api/campaigns` | POST | Form submit (create mode) |
| Update Campaign | `PATCH /api/campaigns/:id` | PATCH | Form submit (edit mode) |
| Delete Campaign | `DELETE /api/campaigns/:id` | DELETE | Delete confirmation |

#### Filter Configuration

**Status Options:**
- All Status (empty value)
- Planned
- Active
- Paused
- Completed

**Type Options:**
- All Types (empty value)
- Email Campaign (`email`)
- Event (`event`)
- Webinar (`webinar`)
- Advertising (`ads`)
- Social Media (`social`)
- Other (`other`)

#### Campaign Metrics Displayed (CampaignCard)

| Metric | Field | Format |
|--------|-------|--------|
| Sent | `num_sent` | Integer |
| Responses | `num_responses` | Integer |
| Response Rate | `response_rate` | Percentage |
| Revenue | `actual_revenue` | Currency |

---

### 2. CampaignDetailPage

**File Path:** `/frontend/src/features/campaigns/CampaignDetailPage.tsx`

**Route Path:** `/campaigns/:id`

**Description:** A detailed view of a single campaign showing campaign information, performance statistics, funnel visualization, and member management.

#### UI Components Used

| Component | Source | Purpose |
|-----------|--------|---------|
| `Button` | `../../components/ui` | Action buttons (Edit, Delete, Add Members, Back) |
| `Spinner` | `../../components/ui` | Loading state indicators |
| `Modal` | `../../components/ui` | Edit form modal |
| `ConfirmDialog` | `../../components/ui` | Delete and remove member confirmation dialogs |
| `CampaignForm` | `./components/CampaignForm` | Edit form component |
| `AddMembersModal` | `./components/AddMembersModal` | Modal for adding contacts/leads to campaign |
| `StatCard` | Internal component | Statistics display cards |
| `MemberRow` | Internal component | Campaign member table row |

**Icons Used (from @heroicons/react/24/outline):**
- `ArrowLeftIcon` - Back navigation
- `PlusIcon` - Add members button
- `UsersIcon` - Total members stat / Empty state
- `ChartBarIcon` - Response/conversion rate stats
- `CurrencyDollarIcon` - Revenue stat
- `TrashIcon` - Remove member button

#### State Management

| State Variable | Type | Purpose |
|----------------|------|---------|
| `showEditForm` | `boolean` | Toggle edit form modal visibility |
| `showAddMembersModal` | `boolean` | Toggle add members modal visibility |
| `showDeleteConfirm` | `boolean` | Toggle delete confirmation dialog |
| `removeMemberConfirm` | `{ isOpen: boolean; memberId: number \| null }` | Remove member confirmation state |

#### Functions and Handlers

| Function | Purpose | Description |
|----------|---------|-------------|
| `handleDeleteConfirm()` | Campaign Deletion | Deletes campaign and navigates back to list |
| `handleFormSubmit(data)` | Campaign Update | Updates campaign via mutation and closes modal |
| `handleRemoveMemberClick(memberId)` | Remove Member Initiation | Opens remove member confirmation dialog |
| `handleRemoveMemberConfirm()` | Remove Member Execution | Removes member from campaign via mutation |
| `handleAddMembers(memberType, memberIds)` | Add Members | Adds contacts or leads to campaign |

#### Hooks Used

| Hook | Source | Purpose |
|------|--------|---------|
| `useParams` | `react-router-dom` | Extract campaign ID from URL |
| `useNavigate` | `react-router-dom` | Navigation after delete |
| `useState` | `react` | Local component state |
| `useMemo` | `react` | Compute existing member IDs for filtering |
| `useCampaign` | `../../hooks/useCampaigns` | Fetch single campaign |
| `useCampaignStats` | `../../hooks/useCampaigns` | Fetch campaign statistics |
| `useCampaignMembers` | `../../hooks/useCampaigns` | Fetch campaign members list |
| `useUpdateCampaign` | `../../hooks/useCampaigns` | Update campaign mutation |
| `useDeleteCampaign` | `../../hooks/useCampaigns` | Delete campaign mutation |
| `useRemoveCampaignMember` | `../../hooks/useCampaigns` | Remove member mutation |
| `useAddCampaignMembers` | `../../hooks/useCampaigns` | Add members mutation |

#### API Calls

| API Call | Endpoint | Method | Trigger |
|----------|----------|--------|---------|
| Get Campaign | `GET /api/campaigns/:id` | GET | Page load |
| Get Campaign Stats | `GET /api/campaigns/:id/stats` | GET | Page load |
| Get Campaign Members | `GET /api/campaigns/:id/members` | GET | Page load |
| Update Campaign | `PATCH /api/campaigns/:id` | PATCH | Edit form submit |
| Delete Campaign | `DELETE /api/campaigns/:id` | DELETE | Delete confirmation |
| Add Members | `POST /api/campaigns/:id/members` | POST | Add members submit |
| Remove Member | `DELETE /api/campaigns/:id/members/:memberId` | DELETE | Remove member confirmation |

#### Campaign Metrics Displayed

**Detail Cards:**
| Metric | Source Field | Format |
|--------|--------------|--------|
| Campaign Type | `campaign_type` | Capitalized string |
| Start Date | `start_date` | Long date format |
| End Date | `end_date` | Long date format |
| Budget | `budget_amount`, `budget_currency` | Currency |

**Statistics Cards (StatCard):**
| Metric | Source | Format |
|--------|--------|--------|
| Total Members | `stats.total_members` | Integer |
| Response Rate | `stats.response_rate` | Percentage with responses count |
| Conversion Rate | `stats.conversion_rate` | Percentage with converted count |
| Revenue | `campaign.actual_revenue` | Currency with ROI percentage |

**Campaign Funnel:**
| Stage | Field | Color |
|-------|-------|-------|
| Pending | `stats.pending` | Gray |
| Sent | `stats.sent` | Blue |
| Responded | `stats.responded` | Green |
| Converted | `stats.converted` | Purple |

#### Member Management

**Member Table Columns:**
- Member (Type and ID)
- Status (with color-coded badge)
- Sent Date
- Responded Date
- Converted Date
- Actions (Remove button)

**Member Status Colors:**
| Status | Background | Text |
|--------|------------|------|
| pending | `bg-gray-100` | `text-gray-700` |
| sent | `bg-blue-100` | `text-blue-700` |
| responded | `bg-green-100` | `text-green-700` |
| converted | `bg-purple-100` | `text-purple-700` |

---

## Supporting Components

### CampaignForm

**File Path:** `/frontend/src/features/campaigns/components/CampaignForm.tsx`

**Description:** Reusable form component for creating and editing campaigns.

#### Form Fields and Validation

| Field | Type | Validation | Default |
|-------|------|------------|---------|
| `name` | `Input` (text) | **Required** - "Campaign name is required" | Empty |
| `description` | `FormTextarea` | Optional | Empty |
| `campaign_type` | `Select` (controlled) | **Required** - "Campaign type is required" | `'email'` |
| `status` | `Select` (controlled) | Optional | `'planned'` |
| `start_date` | `Input` (date) | Optional | Empty |
| `end_date` | `Input` (date) | Optional | Empty |
| `budget_amount` | `Input` (number) | Optional | Empty |
| `budget_currency` | `Select` (controlled) | Optional | `'USD'` |
| `expected_revenue` | `Input` (number) | Optional | Empty |
| `expected_response` | `Input` (number) | Optional | Empty |
| `target_audience` | `FormTextarea` | Optional | Empty |

#### Select Options

**Campaign Type:**
- Email Campaign (`email`)
- Event (`event`)
- Webinar (`webinar`)
- Advertising (`ads`)
- Social Media (`social`)
- Other (`other`)

**Status:**
- Planned (`planned`)
- Active (`active`)
- Paused (`paused`)
- Completed (`completed`)

**Currency:**
- USD ($)
- EUR
- GBP
- INR

#### Hooks Used

| Hook | Source | Purpose |
|------|--------|---------|
| `useEffect` | `react` | Reset form when campaign prop changes |
| `useForm` | `react-hook-form` | Form state management |
| `Controller` | `react-hook-form` | Controlled component integration for Select fields |

---

### AddMembersModal

**File Path:** `/frontend/src/features/campaigns/components/AddMembersModal.tsx`

**Description:** Modal component for adding contacts or leads as campaign members.

#### Props

| Prop | Type | Description |
|------|------|-------------|
| `campaignId` | `number` | ID of the campaign to add members to |
| `existingMemberIds` | `{ contacts: number[]; leads: number[] }` | IDs to exclude from selection |
| `onClose` | `() => void` | Close modal callback |
| `onAdd` | `(memberType, memberIds) => Promise<void>` | Add members callback |
| `isLoading` | `boolean` | Loading state for submit button |

#### State Management

| State Variable | Type | Purpose |
|----------------|------|---------|
| `memberType` | `'contact' \| 'lead'` | Currently selected member type tab |
| `searchQuery` | `string` | Search filter for contacts/leads |
| `selectedIds` | `number[]` | Array of selected member IDs |

#### Functions and Handlers

| Function | Purpose |
|----------|---------|
| `handleToggleSelect(id)` | Toggle selection of a single item |
| `handleSelectAll()` | Select all available items |
| `handleClearSelection()` | Clear all selections |
| `handleSubmit()` | Submit selected members |
| `handleTypeChange(type)` | Switch between contacts/leads tab (clears selection) |

#### API Calls (via hooks)

| Hook | Endpoint | Purpose |
|------|----------|---------|
| `useContacts` | `GET /api/contacts` | Fetch available contacts |
| `useLeads` | `GET /api/leads` | Fetch available leads |

#### Features

- **Tab-based Type Selection:** Switch between Contacts and Leads
- **Search Functionality:** Filter contacts/leads by name/email
- **Bulk Selection:** Select all / Clear selection actions
- **Existing Member Filtering:** Automatically excludes already-added members
- **Selection Counter:** Shows number of selected items

---

## API Reference

### Campaigns API (`/frontend/src/api/campaigns.ts`)

#### CRUD Operations

| Function | Endpoint | Method | Parameters | Returns |
|----------|----------|--------|------------|---------|
| `listCampaigns` | `/api/campaigns` | GET | `CampaignFilters` | `CampaignListResponse` |
| `getCampaign` | `/api/campaigns/:id` | GET | `campaignId: number` | `Campaign` |
| `createCampaign` | `/api/campaigns` | POST | `CampaignCreate` | `Campaign` |
| `updateCampaign` | `/api/campaigns/:id` | PATCH | `campaignId, CampaignUpdate` | `Campaign` |
| `deleteCampaign` | `/api/campaigns/:id` | DELETE | `campaignId: number` | `void` |
| `getCampaignStats` | `/api/campaigns/:id/stats` | GET | `campaignId: number` | `CampaignStats` |

#### Member Operations

| Function | Endpoint | Method | Parameters | Returns |
|----------|----------|--------|------------|---------|
| `getCampaignMembers` | `/api/campaigns/:id/members` | GET | `campaignId, params?` | `CampaignMember[]` |
| `addCampaignMembers` | `/api/campaigns/:id/members` | POST | `campaignId, AddMembersRequest` | `AddMembersResponse` |
| `updateCampaignMember` | `/api/campaigns/:id/members/:memberId` | PATCH | `campaignId, memberId, CampaignMemberUpdate` | `CampaignMember` |
| `removeCampaignMember` | `/api/campaigns/:id/members/:memberId` | DELETE | `campaignId, memberId` | `void` |

---

## Hooks Reference (`/frontend/src/hooks/useCampaigns.ts`)

### Query Keys

```typescript
campaignKeys = {
  all: ['campaigns'],
  lists: () => ['campaigns', 'list'],
  list: (filters) => ['campaigns', 'list', filters],
  details: () => ['campaigns', 'detail'],
  detail: (id) => ['campaigns', 'detail', id],
  stats: (id) => ['campaigns', 'stats', id],
  members: (id, params?) => ['campaigns', 'members', id, params],
}
```

### Available Hooks

| Hook | Purpose | Returns |
|------|---------|---------|
| `useCampaigns(filters?)` | Fetch paginated campaign list | `UseQueryResult<CampaignListResponse>` |
| `useCampaign(id)` | Fetch single campaign | `UseQueryResult<Campaign>` |
| `useCreateCampaign()` | Create campaign mutation | `UseMutationResult` |
| `useUpdateCampaign()` | Update campaign mutation | `UseMutationResult` |
| `useDeleteCampaign()` | Delete campaign mutation | `UseMutationResult` |
| `useCampaignStats(id)` | Fetch campaign statistics | `UseQueryResult<CampaignStats>` |
| `useCampaignMembers(id, params?)` | Fetch campaign members | `UseQueryResult<CampaignMember[]>` |
| `useAddCampaignMembers()` | Add members mutation | `UseMutationResult` |
| `useRemoveCampaignMember()` | Remove member mutation | `UseMutationResult` |

---

## Type Definitions

### Core Types

```typescript
interface Campaign {
  id: number;
  name: string;
  description?: string;
  campaign_type: string;
  status: string;
  start_date?: string;
  end_date?: string;
  budget_amount?: number;
  budget_currency: string;
  target_audience?: string;
  expected_revenue?: number;
  expected_response?: number;
  actual_revenue?: number;
  num_sent: number;
  num_responses: number;
  response_rate: number;
  roi?: number;
}

interface CampaignFilters {
  page?: number;
  page_size?: number;
  search?: string;
  campaign_type?: string;
  status?: string;
}

interface CampaignMember {
  id: number;
  member_type: 'contact' | 'lead';
  member_id: number;
  status: string;
  sent_at?: string;
  responded_at?: string;
  converted_at?: string;
}

interface CampaignStats {
  total_members: number;
  pending: number;
  sent: number;
  responded: number;
  converted: number;
  response_rate: number;
  conversion_rate: number;
}

interface AddMembersRequest {
  member_type: 'contact' | 'lead';
  member_ids: number[];
}
```

---

## Utility Functions Used

| Function | Source | Purpose |
|----------|--------|---------|
| `formatCurrency(amount, currency)` | `../../utils` | Format monetary values |
| `formatDate(date, format)` | `../../utils/formatters` | Format date strings |
| `formatPercentage(value, decimals)` | `../../utils` | Format percentage values |
| `getStatusColor(status, entityType)` | `../../utils/statusColors` | Get status badge colors |
| `formatStatusLabel(status)` | `../../utils/statusColors` | Format status display text |
| `clsx(...)` | `clsx` | Conditional CSS class concatenation |
