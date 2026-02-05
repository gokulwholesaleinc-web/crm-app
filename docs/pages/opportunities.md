# Opportunities Page Documentation

## Page Overview

| Property | Value |
|----------|-------|
| **Page Name** | Opportunities |
| **File Path** | `/frontend/src/features/opportunities/OpportunitiesPage.tsx` |
| **Route** | `/opportunities` |
| **Purpose** | Manage sales pipeline with Kanban and List views |

---

## UI Components

### Page Layout Components

| Component | Source | Purpose |
|-----------|--------|---------|
| `Button` | `../../components/ui` | Primary action buttons |
| `Spinner` | `../../components/ui` | Loading state indicator |
| `Modal` | `../../components/ui` | Form dialog container |
| `PlusIcon` | `@heroicons/react/24/outline` | Add opportunity button icon |

### Kanban Board Components

| Component | File Path | Purpose |
|-----------|-----------|---------|
| `KanbanBoard` | `./components/KanbanBoard/KanbanBoard.tsx` | Main drag-drop board container |
| `KanbanColumn` | `./components/KanbanBoard/KanbanColumn.tsx` | Stage column with drop zone |
| `KanbanCard` | `./components/KanbanBoard/KanbanCard.tsx` | Draggable opportunity card |

### Form Components

| Component | File Path | Purpose |
|-----------|-----------|---------|
| `OpportunityForm` | `./components/OpportunityForm.tsx` | Create/edit opportunity form |
| `FormInput` | `../../components/forms` | Text and number inputs |
| `FormSelect` | `../../components/forms` | Dropdown selects |
| `FormTextarea` | `../../components/forms` | Multi-line text input |

---

## View Modes

### 1. Kanban View (Default)

- **Description**: Visual pipeline board with draggable cards
- **Features**:
  - Drag and drop opportunities between stages
  - Visual indicators for stage colors
  - Stage value totals displayed in column headers
  - Card count badges per stage
  - Click cards to edit

### 2. List View

- **Description**: Tabular view of all opportunities
- **Columns**:
  - Opportunity (name + company)
  - Value (formatted currency)
  - Stage (with status badge)
  - Probability (percentage)
  - Close Date (formatted date)
  - Actions (Edit button)
- **Features**:
  - Hover effects on rows
  - Click row to edit opportunity
  - Empty state with call-to-action

---

## Functions and Handlers

### State Management

```typescript
const [viewMode, setViewMode] = useState<'kanban' | 'list'>('kanban');
const [showForm, setShowForm] = useState(false);
const [editingOpportunity, setEditingOpportunity] = useState<Opportunity | null>(null);
```

### Event Handlers

| Handler | Parameters | Description |
|---------|------------|-------------|
| `handleOpportunityMove` | `opportunityId: string, newStage: string, newIndex: number` | Handles drag-drop stage changes via mutation |
| `handleOpportunityClick` | `opportunity: KanbanOpportunity` | Opens edit modal for clicked opportunity |
| `handleEdit` | `opportunity: Opportunity` | Sets editing state and opens form modal |
| `handleFormSubmit` | `data: OpportunityFormData` | Creates or updates opportunity based on editing state |
| `handleFormCancel` | - | Closes modal and clears editing state |
| `getInitialFormData` | - | Transforms opportunity data for form defaults |

### Drag and Drop Handlers (KanbanBoard)

| Handler | Event | Description |
|---------|-------|-------------|
| `handleDragStart` | `DragStartEvent` | Captures active opportunity for overlay |
| `handleDragOver` | `DragOverEvent` | Updates local state during drag, handles column and card drops |
| `handleDragEnd` | `DragEndEvent` | Commits stage change via API mutation |
| `handleDragCancel` | - | Reverts to original state |

### Utility Functions

| Function | Purpose |
|----------|---------|
| `getOpportunitiesByStage(stage)` | Filters opportunities by stage ID |
| `getTotalValueByStage(stage)` | Calculates sum of values for a stage |
| `findOpportunityById(id)` | Locates opportunity in local state |

---

## Hooks Used

### Data Fetching Hooks

| Hook | Source | Purpose |
|------|--------|---------|
| `useOpportunities` | `../../hooks` | Fetches paginated opportunities list |
| `usePipelineStages` | `../../hooks` | Fetches pipeline stage configuration |
| `useContacts` | `../../hooks` | Fetches contacts for form dropdown (page_size: 100) |
| `useCompanies` | `../../hooks` | Fetches companies for form dropdown (page_size: 100) |

### Mutation Hooks

| Hook | Purpose |
|------|---------|
| `useMoveOpportunity` | Moves opportunity to new pipeline stage |
| `useCreateOpportunity` | Creates new opportunity |
| `useUpdateOpportunity` | Updates existing opportunity |

### React Hooks

| Hook | Component | Purpose |
|------|-----------|---------|
| `useState` | OpportunitiesPage, KanbanBoard | Local state management |
| `useCallback` | KanbanBoard | Memoized filter functions |
| `useForm` | OpportunityForm | Form state management (react-hook-form) |

### Drag and Drop Hooks (dnd-kit)

| Hook | Component | Purpose |
|------|-----------|---------|
| `useSensors` | KanbanBoard | Configures drag activation |
| `useSensor` | KanbanBoard | Sets up PointerSensor with distance constraint |
| `useSortable` | KanbanCard | Makes cards draggable and sortable |
| `useDroppable` | KanbanColumn | Makes columns drop targets |

---

## API Calls

### Endpoints

| Endpoint | Method | Hook | Description |
|----------|--------|------|-------------|
| `/api/opportunities` | GET | `useOpportunities` | List opportunities with filters |
| `/api/opportunities` | POST | `useCreateOpportunity` | Create new opportunity |
| `/api/opportunities/:id` | PATCH | `useUpdateOpportunity` | Update opportunity |
| `/api/opportunities/:id/move` | POST | `useMoveOpportunity` | Move to new stage |
| `/api/opportunities/stages` | GET | `usePipelineStages` | List pipeline stages |

### Query Keys

```typescript
opportunityKeys = {
  all: ['opportunities'],
  lists: () => [...opportunityKeys.all, 'list'],
  detail: (id) => [...opportunityKeys.all, 'detail', id],
};

pipelineKeys = {
  all: ['pipeline'],
  stages: (activeOnly?) => [...pipelineKeys.all, 'stages', { activeOnly }],
  kanban: (ownerId?) => [...pipelineKeys.all, 'kanban', { ownerId }],
};
```

### Cache Invalidation

On opportunity create/update/move:
- `opportunityKeys.lists()`
- `pipelineKeys.kanban()`
- `pipelineKeys.summary()`

---

## Form Fields and Validation

### OpportunityFormData Interface

```typescript
interface OpportunityFormData {
  name: string;           // Required
  value: number;          // Required, min: 0
  stage: string;          // Required
  probability?: number;   // 0-100
  expectedCloseDate?: string;
  contactId?: string;
  companyId?: string;
  description?: string;
  notes?: string;
}
```

### Validation Rules

| Field | Rule | Error Message |
|-------|------|---------------|
| `name` | Required | "Opportunity name is required" |
| `value` | Required, min: 0 | "Value is required" / "Value must be positive" |
| `stage` | Required | "Stage is required" |
| `probability` | min: 0, max: 100 | "Probability must be at least 0" / "Probability cannot exceed 100" |

### Form Sections

1. **Opportunity Details**
   - Opportunity Name (text, full width)
   - Value (number)
   - Expected Close Date (date picker)

2. **Pipeline Stage**
   - Stage (dropdown select)
   - Win Probability % (number)
   - Visual stage progress indicator

3. **Related Records**
   - Primary Contact (dropdown)
   - Company (dropdown)

4. **Description & Notes**
   - Description (textarea, 3 rows)
   - Internal Notes (textarea, 3 rows)

---

## Kanban Configuration

### Pipeline Stages (Default)

| ID | Title | Color | Default Probability |
|----|-------|-------|---------------------|
| `qualification` | Qualification | Blue | 20% |
| `needs_analysis` | Needs Analysis | Yellow | 40% |
| `proposal` | Proposal | Purple | 60% |
| `negotiation` | Negotiation | Orange | 80% |
| `closed_won` | Closed Won | Green | 100% |
| `closed_lost` | Closed Lost | Red | 0% |

### Stage Color Classes

```typescript
const colorClasses = {
  blue: 'bg-blue-500',
  yellow: 'bg-yellow-500',
  purple: 'bg-purple-500',
  orange: 'bg-orange-500',
  green: 'bg-green-500',
  red: 'bg-red-500',
  gray: 'bg-gray-500',
};
```

### KanbanStage Interface

```typescript
interface KanbanStage {
  id: string;
  title: string;
  color: string;
}
```

---

## Kanban Card Structure

### Opportunity Interface (Kanban)

```typescript
interface Opportunity {
  id: string;
  name: string;
  value: number;
  stage: string;
  probability: number;
  expectedCloseDate?: string;
  contactName?: string;
  companyName?: string;
}
```

### Card Display

1. **Header Section**
   - Opportunity name (line-clamp-2)
   - Company name (if available)

2. **Value Section**
   - Formatted currency value (large font)
   - Probability percentage

3. **Footer Section** (border-top)
   - Contact name with user icon
   - Expected close date with calendar icon
   - Overdue dates shown in red

### Card Interactions

- **Drag**: Click and hold, 8px activation distance
- **Click**: Opens edit modal
- **Visual feedback**:
  - `cursor-grab` / `cursor-grabbing`
  - Shadow on hover
  - Opacity reduction during drag
  - 3-degree rotation on drag overlay

---

## Pipeline Summary

### Dashboard Metrics

| Metric | Calculation |
|--------|-------------|
| Total Pipeline Value | Sum of values for open opportunities |
| Weighted Pipeline Value | Sum of (value * probability) for open opportunities |
| Open Opportunities | Count of opportunities not in closed_won/closed_lost |

### Filter Logic

```typescript
const openOpportunities = opportunities.filter(
  (o) => !['closed_won', 'closed_lost'].includes(o.stage)
);
```

---

## Drag and Drop Implementation

### Libraries Used

- `@dnd-kit/core` - Core drag and drop functionality
- `@dnd-kit/sortable` - Sortable list support
- `@dnd-kit/utilities` - CSS transform utilities

### Configuration

```typescript
const sensors = useSensors(
  useSensor(PointerSensor, {
    activationConstraint: {
      distance: 8,  // Minimum drag distance
    },
  })
);
```

### Collision Detection

- Uses `closestCorners` algorithm for drop targeting

### Data Attributes

```typescript
// Column droppable data
{ type: 'column', stage: stageId }

// Card sortable data
{ type: 'opportunity', opportunity }
```

---

## File Structure

```
frontend/src/features/opportunities/
├── OpportunitiesPage.tsx          # Main page component
└── components/
    ├── KanbanBoard/
    │   ├── KanbanBoard.tsx        # Board container with DndContext
    │   ├── KanbanColumn.tsx       # Droppable stage columns
    │   └── KanbanCard.tsx         # Sortable opportunity cards
    └── OpportunityForm.tsx        # Create/edit form component
```

---

## Dependencies

### External Libraries

| Library | Version | Purpose |
|---------|---------|---------|
| `@dnd-kit/core` | - | Drag and drop core |
| `@dnd-kit/sortable` | - | Sortable contexts |
| `@dnd-kit/utilities` | - | CSS utilities |
| `react-hook-form` | - | Form state management |
| `@tanstack/react-query` | - | Server state management |
| `clsx` | - | Conditional class names |
| `@heroicons/react` | - | Icon components |

### Internal Dependencies

- `../../components/ui` - UI components (Button, Spinner, Modal)
- `../../components/forms` - Form components
- `../../hooks` - Data hooks
- `../../utils` - Formatters (currency, date, percentage)
- `../../types` - TypeScript interfaces
