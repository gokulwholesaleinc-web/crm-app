# Activities Page Documentation

## 1. Page Name and Path

| Property | Value |
|----------|-------|
| **Page Name** | ActivitiesPage |
| **Route Path** | `/activities` |
| **File Location** | `/frontend/src/features/activities/ActivitiesPage.tsx` |
| **Access** | Protected (requires authentication via PrivateRoute) |
| **Description** | Activities list/timeline view with filters by type for tracking and managing CRM activities |

---

## 2. UI Components Used

### External UI Components (from `../../components/ui`)

| Component | Usage |
|-----------|-------|
| `Button` | Primary action buttons (New Activity, Pagination, Filter toggle) |
| `Select` | Dropdown selects for priority and status filters |
| `Spinner` | Loading indicator while fetching data |
| `Modal` | Container for the activity create/edit form |
| `ConfirmDialog` | Confirmation dialog for delete operations |

### Local Feature Components (from `./components`)

| Component | File | Usage |
|-----------|------|-------|
| `ActivityCard` | `ActivityCard.tsx` | Displays individual activity in list view with type-specific icons and actions |
| `ActivityTimeline` | `ActivityTimeline.tsx` | Displays activities in a chronological timeline view grouped by date |
| `ActivityForm` | `ActivityForm.tsx` | Form for creating and editing activities with type-specific fields |

### Heroicons Used

| Icon | Purpose |
|------|---------|
| `PlusIcon` | Add new activity button |
| `FunnelIcon` | Toggle filters panel |
| `ListBulletIcon` | List view mode toggle |
| `ClockIcon` | Timeline view mode toggle |
| `PhoneIcon` | Call activity type indicator |
| `EnvelopeIcon` | Email activity type indicator |
| `CalendarIcon` | Meeting activity type indicator |
| `ClipboardDocumentCheckIcon` | Task activity type indicator |
| `DocumentTextIcon` | Note activity type indicator, empty state icon |

---

## 3. Functions and Handlers

### Filter Management

| Function | Description | Parameters |
|----------|-------------|------------|
| `updateFilter` | Updates URL search params for filtering and resets to page 1 | `key: string, value: string` |

### CRUD Operations

| Handler | Description | API Hook Used |
|---------|-------------|---------------|
| `handleFormSubmit` | Creates new activity or updates existing one | `createActivity.mutateAsync` / `updateActivity.mutateAsync` |
| `handleDeleteConfirm` | Deletes activity after confirmation | `deleteActivity.mutateAsync` |

### Activity Completion

| Handler | Description | API Hook Used |
|---------|-------------|---------------|
| `handleComplete` | Marks an activity as completed | `completeActivity.mutateAsync` |

### UI State Management

| Handler | Description |
|---------|-------------|
| `handleEdit` | Sets the activity to edit mode and opens the form modal |
| `handleDeleteClick` | Opens delete confirmation dialog with the selected activity |
| `handleDeleteCancel` | Closes delete confirmation dialog |
| `handleFormCancel` | Closes form modal and clears editing state |
| `setViewMode` | Toggles between 'list' and 'timeline' view modes |
| `setShowFilters` | Toggles visibility of the filters panel |
| `setShowForm` | Toggles visibility of the activity form modal |

---

## 4. Hooks Used

### React Hooks

| Hook | Usage |
|------|-------|
| `useState` | Managing local state (viewMode, showFilters, showForm, editingActivity, deleteConfirm) |
| `useMemo` | Memoizing filter values derived from URL search params |

### React Router Hooks

| Hook | Usage |
|------|-------|
| `useSearchParams` | Reading and updating URL query parameters for filters and pagination |

### Custom Activity Hooks (from `../../hooks/useActivities`)

| Hook | Return Type | Purpose |
|------|-------------|---------|
| `useActivities(filters)` | `{ data: ActivityListResponse, isLoading }` | Fetches paginated list of activities with filters |
| `useUserTimeline(activityType)` | `{ data: TimelineResponse, isLoading }` | Fetches user's activity timeline |
| `useCreateActivity()` | Mutation hook | Creates a new activity |
| `useUpdateActivity()` | Mutation hook | Updates an existing activity |
| `useDeleteActivity()` | Mutation hook | Deletes an activity |
| `useCompleteActivity()` | Mutation hook | Marks an activity as completed |

---

## 5. API Calls Made

### Base URL
`/api/activities`

### Endpoints Used

| Method | Endpoint | Description | Hook |
|--------|----------|-------------|------|
| GET | `/api/activities` | List activities with pagination and filters | `useActivities` |
| GET | `/api/activities/timeline/user` | Get user's activity timeline | `useUserTimeline` |
| POST | `/api/activities` | Create a new activity | `useCreateActivity` |
| PATCH | `/api/activities/:id` | Update an activity | `useUpdateActivity` |
| DELETE | `/api/activities/:id` | Delete an activity | `useDeleteActivity` |
| POST | `/api/activities/:id/complete` | Mark activity as completed | `useCompleteActivity` |

### Request/Response Types

```typescript
// Activity Filters (Query Parameters)
interface ActivityFilters {
  page?: number;
  page_size?: number;
  entity_type?: string;
  entity_id?: number;
  activity_type?: string;
  priority?: string;
  is_completed?: boolean;
}

// Paginated Response
interface ActivityListResponse {
  items: Activity[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// Timeline Response
interface TimelineResponse {
  items: TimelineItem[];
}
```

---

## 6. Form Fields and Validation

### ActivityForm Component

The form is rendered inside a Modal and adapts based on the selected activity type.

#### Common Fields (All Activity Types)

| Field | Type | Required | Validation | Default |
|-------|------|----------|------------|---------|
| `activity_type` | Select | Yes | Required | `'task'` |
| `subject` | Input (text) | Yes | Required | `''` |
| `description` | Textarea | No | None | `''` |
| `scheduled_at` | Input (datetime-local) | No | Valid datetime | `null` |
| `due_date` | Input (date) | No | Valid date | `null` |
| `priority` | Select | No | None | `'normal'` |

#### Call-Specific Fields (when `activity_type === 'call'`)

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `call_duration_minutes` | Input (number) | No | Positive integer |
| `call_outcome` | Select | No | None |

**Call Outcome Options:**
- `''` - Select outcome...
- `'connected'` - Connected
- `'voicemail'` - Left Voicemail
- `'no_answer'` - No Answer
- `'busy'` - Busy

#### Email-Specific Fields (when `activity_type === 'email'`)

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `email_to` | Input (email) | No | Email format |
| `email_cc` | Input (email) | No | Email format |

#### Meeting-Specific Fields (when `activity_type === 'meeting'`)

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `meeting_location` | Input (text) | No | None |
| `meeting_attendees` | Textarea | No | None (one per line) |

#### Task-Specific Fields (when `activity_type === 'task'`)

| Field | Type | Required | Validation |
|-------|------|----------|------------|
| `task_reminder_at` | Input (datetime-local) | No | Valid datetime |

### Form Libraries Used

- **react-hook-form**: Form state management and validation
- **Controller**: Used for Select components integration with react-hook-form

---

## 7. Activity Types

### Supported Activity Types

| Type | Value | Icon | Color Theme |
|------|-------|------|-------------|
| Call | `'call'` | `PhoneIcon` | Blue (`bg-blue-50`, `text-blue-600`, `border-blue-200`) |
| Email | `'email'` | `EnvelopeIcon` | Purple (`bg-purple-50`, `text-purple-600`, `border-purple-200`) |
| Meeting | `'meeting'` | `CalendarIcon` | Green (`bg-green-50`, `text-green-600`, `border-green-200`) |
| Task | `'task'` | `ClipboardDocumentCheckIcon` | Yellow (`bg-yellow-50`, `text-yellow-600`, `border-yellow-200`) |
| Note | `'note'` | `DocumentTextIcon` | Gray (`bg-gray-50`, `text-gray-600`, `border-gray-200`) |

### Priority Levels

| Priority | Value | Display Color |
|----------|-------|---------------|
| Low | `'low'` | Gray (`text-gray-500`) |
| Normal | `'normal'` | Blue (`text-blue-500`) |
| High | `'high'` | Orange (`text-orange-500`) |
| Urgent | `'urgent'` | Red (`text-red-500`) |

### Status Options

| Status | Value | Filter Mapping |
|--------|-------|----------------|
| All Status | `''` | `is_completed: undefined` |
| Pending | `'pending'` | `is_completed: false` |
| Completed | `'completed'` | `is_completed: true` |

---

## 8. Table/List Structure

### View Modes

The page supports two view modes toggled via icon buttons:

1. **List View** (`viewMode === 'list'`)
2. **Timeline View** (`viewMode === 'timeline'`)

### List View Structure (ActivityCard)

Each activity card displays:

```
+------------------------------------------------------------------+
| [Type Icon]  Subject                    [Priority Badge] [Overdue]|
|              Description (2 line clamp)                           |
|              [Clock] Scheduled At  [Calendar] Due Date            |
|              [Type-specific details: duration, location, etc.]    |
|              [Completed timestamp if completed]                   |
|                                          [Complete] [Edit] [Delete]|
+------------------------------------------------------------------+
```

**Card Information Displayed:**
- Activity type icon with color-coded background
- Subject (with strikethrough if completed)
- Priority badge (if not 'normal')
- Overdue indicator (if past due date and not completed)
- Description (optional, truncated to 2 lines)
- Scheduled at timestamp
- Due date
- Type-specific details:
  - Call: duration, outcome
  - Meeting: location
- Completed at timestamp (if completed)
- Action buttons: Complete, Edit, Delete

### Timeline View Structure (ActivityTimeline)

Activities are grouped by date with a vertical timeline connector:

```
Today
|
O---- [Type Badge] [Priority]                    [Time]
|     Subject (with strikethrough if completed)
|     Description (2 line clamp)
|     [Type-specific badges]
|     [Mark as complete button]
|
O---- [Next activity...]

Yesterday
|
O---- [Activity...]
```

**Timeline Entry Information:**
- Date group header (Today, Yesterday, or formatted date)
- Circular icon with activity type or checkmark (if completed)
- Activity type badge
- Priority indicator (if not normal)
- Creation time
- Subject
- Description (optional)
- Type-specific metadata badges (duration, outcome, location)
- Mark as complete button (if not completed)

### Pagination (List View Only)

```
[Previous]  Page X of Y  [Next]
```

- Appears when `activitiesData.pages > 1`
- Previous button disabled on page 1
- Next button disabled on last page
- Page navigation updates URL params via `updateFilter('page', newPage)`

### Empty State

When no activities exist:

```
        [Document Icon]
      No activities
Get started by creating a new activity.
        [New Activity Button]
```

---

## Component File Structure

```
frontend/src/features/activities/
├── ActivitiesPage.tsx       # Main page component
├── index.ts                 # Module exports
└── components/
    ├── ActivityCard.tsx     # Card component for list view
    ├── ActivityTimeline.tsx # Timeline component for timeline view
    └── ActivityForm.tsx     # Create/edit form component
```

## Related Files

| File | Purpose |
|------|---------|
| `/frontend/src/hooks/useActivities.ts` | Custom hooks for activity data fetching and mutations |
| `/frontend/src/api/activities.ts` | API client functions for activities endpoints |
| `/frontend/src/types/index.ts` | TypeScript interfaces (Activity, ActivityCreate, etc.) |
| `/frontend/src/routes/index.tsx` | Route configuration |

## State Management

- **URL State**: Filters and pagination managed via `useSearchParams`
- **Local State**: View mode, form visibility, edit state, delete confirmation
- **Server State**: Managed via TanStack Query (react-query) through custom hooks
