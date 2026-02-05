# Contacts Pages Documentation

This document provides detailed documentation for the Contacts feature pages in the CRM application.

---

## Table of Contents

1. [ContactsPage.tsx](#contactspagetsx)
2. [ContactDetailPage.tsx](#contactdetailpagetsx)
3. [ContactForm.tsx (Component)](#contactformtsx-component)

---

## ContactsPage.tsx

**File Path:** `/frontend/src/features/contacts/ContactsPage.tsx`

**Route Path:** `/contacts`

### Overview

The ContactsPage is the main listing page for managing contacts. It provides a paginated table view of all contacts with search functionality, and supports full CRUD operations through modals and confirmation dialogs.

### UI Components Used

| Component | Source | Purpose |
|-----------|--------|---------|
| `Button` | `../../components/ui` | Primary action buttons (Add Contact, Search, Pagination) |
| `Spinner` | `../../components/ui` | Loading indicator during data fetch |
| `Modal` | `../../components/ui` | Container for ContactForm (create/edit) |
| `ConfirmDialog` | `../../components/ui` | Delete confirmation dialog |
| `ContactForm` | `./components/ContactForm` | Form for creating/editing contacts |
| `Link` | `react-router-dom` | Navigation links to contact detail pages |
| `PlusIcon` | `@heroicons/react/24/outline` | Icon for "Add Contact" button |

### State Management

| State Variable | Type | Initial Value | Purpose |
|----------------|------|---------------|---------|
| `searchQuery` | `string` | `''` | Current search input value |
| `currentPage` | `number` | `1` | Current pagination page |
| `showForm` | `boolean` | `false` | Controls form modal visibility |
| `editingContact` | `Contact \| null` | `null` | Contact being edited (null for create mode) |
| `deleteConfirm` | `{ isOpen: boolean; contact: Contact \| null }` | `{ isOpen: false, contact: null }` | Delete confirmation state |
| `pageSize` | `number` | `10` | Items per page (constant) |

### Hooks Used

| Hook | Source | Purpose |
|------|--------|---------|
| `useState` | `react` | Local state management |
| `useEffect` | `react` | Handle URL query parameters for auto-opening form |
| `useSearchParams` | `react-router-dom` | Read/write URL search parameters |
| `useContacts` | `../../hooks` | Fetch paginated contacts list |
| `useCreateContact` | `../../hooks` | Create contact mutation |
| `useUpdateContact` | `../../hooks` | Update contact mutation |
| `useDeleteContact` | `../../hooks` | Delete contact mutation |

### API Calls

| Operation | API Endpoint | Method | Hook |
|-----------|--------------|--------|------|
| List Contacts | `GET /api/contacts` | GET | `useContacts({ page, page_size, search })` |
| Create Contact | `POST /api/contacts` | POST | `useCreateContact().mutateAsync(data)` |
| Update Contact | `PATCH /api/contacts/:id` | PATCH | `useUpdateContact().mutateAsync({ id, data })` |
| Delete Contact | `DELETE /api/contacts/:id` | DELETE | `useDeleteContact().mutateAsync(id)` |

### Functions/Handlers

#### `handleSearch(e: React.FormEvent)`
- **Purpose:** Handles search form submission
- **Behavior:** Prevents default form submission and resets pagination to page 1

#### `handleDeleteClick(contact: Contact)`
- **Purpose:** Opens delete confirmation dialog
- **Behavior:** Sets `deleteConfirm` state with the selected contact

#### `handleDeleteConfirm()`
- **Purpose:** Executes contact deletion
- **Behavior:** Calls delete mutation and closes dialog on success

#### `handleDeleteCancel()`
- **Purpose:** Cancels delete operation
- **Behavior:** Closes delete confirmation dialog

#### `handleEdit(contact: Contact)`
- **Purpose:** Opens edit form for a contact
- **Behavior:** Sets `editingContact` and shows form modal

#### `handleFormSubmit(data: ContactFormData)`
- **Purpose:** Handles form submission for both create and update
- **Behavior:**
  - If `editingContact` is set, calls update mutation
  - Otherwise, calls create mutation with default status 'active'
  - Closes modal on success

#### `handleFormCancel()`
- **Purpose:** Cancels form operation
- **Behavior:** Closes modal and clears editing state

#### `getInitialFormData(): Partial<ContactFormData> | undefined`
- **Purpose:** Transforms contact data to form data format
- **Behavior:** Maps API field names to form field names for edit mode

### URL Query Parameter Handling

The page listens for the `action` query parameter:
- `?action=new` - Auto-opens the create contact form (used when navigating from other pages like company detail)

### Table Columns

| Column | Field | Sortable | Format |
|--------|-------|----------|--------|
| Name | `first_name`, `last_name`, `job_title` | No | Link to detail page, job title as subtitle |
| Email | `email` | No | Plain text or '-' |
| Company | `company.name` | No | Plain text or '-' |
| Phone | `phone` | No | Formatted via `formatPhoneNumber()` |
| Created | `created_at` | No | Formatted via `formatDate()` |
| Actions | - | No | Edit and Delete buttons |

### Table Actions

| Action | Trigger | Behavior |
|--------|---------|----------|
| View Detail | Click on contact name | Navigates to `/contacts/:id` |
| Edit | Click "Edit" button | Opens edit form modal |
| Delete | Click "Delete" button | Opens delete confirmation dialog |

### Pagination

- **Type:** Server-side pagination
- **Page Size:** 10 items per page
- **Controls:** Previous/Next buttons with page indicator
- **Responsive:** Simplified controls on mobile

### Navigation Flows

| From | To | Trigger |
|------|-----|---------|
| ContactsPage | ContactDetailPage | Click on contact name in table |
| ContactsPage | ContactsPage (form open) | URL with `?action=new` |
| External pages | ContactsPage (form open) | Navigate to `/contacts?action=new` |

---

## ContactDetailPage.tsx

**File Path:** `/frontend/src/features/contacts/ContactDetailPage.tsx`

**Route Path:** `/contacts/:id`

### Overview

The ContactDetailPage displays detailed information about a single contact, including a tabbed interface for details, activities, and notes. It supports editing and deleting the contact.

### UI Components Used

| Component | Source | Purpose |
|-----------|--------|---------|
| `Button` | `../../components/ui` | Action buttons (Edit, Delete, Add Note) |
| `Spinner` | `../../components/ui` | Loading indicators |
| `Modal` | `../../components/ui` | Container for edit form |
| `ConfirmDialog` | `../../components/ui` | Delete confirmation dialog |
| `ContactForm` | `./components/ContactForm` | Form for editing contact |
| `Link` | `react-router-dom` | Back navigation link |
| `clsx` | `clsx` | Conditional CSS class joining |

### State Management

| State Variable | Type | Initial Value | Purpose |
|----------------|------|---------------|---------|
| `activeTab` | `TabType ('details' \| 'activities' \| 'notes')` | `'details'` | Current active tab |
| `newNote` | `string` | `''` | New note input value |
| `showEditForm` | `boolean` | `false` | Controls edit form modal visibility |
| `showDeleteConfirm` | `boolean` | `false` | Controls delete confirmation dialog |

### Hooks Used

| Hook | Source | Purpose |
|------|--------|---------|
| `useState` | `react` | Local state management |
| `useParams` | `react-router-dom` | Extract contact ID from URL |
| `useNavigate` | `react-router-dom` | Programmatic navigation |
| `useContact` | `../../hooks` | Fetch single contact data |
| `useDeleteContact` | `../../hooks` | Delete contact mutation |
| `useUpdateContact` | `../../hooks` | Update contact mutation |
| `useTimeline` | `../../hooks/useActivities` | Fetch contact activities timeline |
| `useUIStore` | `../../store/uiStore` | Access UI store for toasts |

### API Calls

| Operation | API Endpoint | Method | Hook |
|-----------|--------------|--------|------|
| Get Contact | `GET /api/contacts/:id` | GET | `useContact(contactId)` |
| Update Contact | `PATCH /api/contacts/:id` | PATCH | `useUpdateContact().mutateAsync({ id, data })` |
| Delete Contact | `DELETE /api/contacts/:id` | DELETE | `useDeleteContact().mutateAsync(id)` |
| Get Timeline | `GET /api/activities/timeline/:entityType/:entityId` | GET | `useTimeline('contact', contactId)` |

### Functions/Handlers

#### `handleEditSubmit(data: ContactFormData)`
- **Purpose:** Handles edit form submission
- **Behavior:** Transforms form data to API format and calls update mutation

#### `getInitialFormData(): Partial<ContactFormData> | undefined`
- **Purpose:** Transforms contact data to form data format
- **Behavior:** Maps API field names to form field names for pre-populating edit form

#### `handleDeleteConfirm()`
- **Purpose:** Executes contact deletion
- **Behavior:** Calls delete mutation and navigates to `/contacts` on success

#### `handleAddNote()`
- **Purpose:** Handles add note action
- **Behavior:** Shows "coming soon" toast notification (feature not yet implemented)

### Tab Structure

| Tab ID | Tab Name | Content |
|--------|----------|---------|
| `details` | Details | Contact information display |
| `activities` | Activities | Timeline of activities related to contact |
| `notes` | Notes | Notes interface (placeholder - coming soon) |

### Details Tab Fields

| Field Label | Data Field | Format |
|-------------|------------|--------|
| Email | `contact.email` | Mailto link |
| Phone | `contact.phone` | Tel link, formatted via `formatPhoneNumber()` |
| Company | `contact.company.name` | Plain text or '-' |
| Job Title | `contact.job_title` | Plain text or '-' |
| Address | `address_line1`, `address_line2`, `city`, `state`, `postal_code`, `country` | Multi-line formatted address |
| Notes | `contact.description` | Plain text or 'No notes' |
| Created | `contact.created_at` | Formatted via `formatDate()` |
| Last Updated | `contact.updated_at` | Formatted via `formatDate()` |

### Activities Tab

- **Data Source:** `useTimeline('contact', contactId)`
- **Conditional Fetching:** Only fetches when tab is active (`shouldFetchActivities`)
- **Display:** List of activities with subject and timestamp
- **Empty State:** "No activities recorded yet."

### Notes Tab

- **Status:** Coming soon (placeholder)
- **UI:** Text area for adding notes with submit button
- **Behavior:** Shows toast notification that feature is coming soon

### Navigation Flows

| From | To | Trigger |
|------|-----|---------|
| ContactDetailPage | ContactsPage | Click back arrow or "Back to contacts" link |
| ContactDetailPage | ContactsPage | After successful delete |

---

## ContactForm.tsx (Component)

**File Path:** `/frontend/src/features/contacts/components/ContactForm.tsx`

### Overview

Reusable form component for creating and editing contacts. Uses react-hook-form for form state management and validation.

### Props Interface

```typescript
interface ContactFormProps {
  initialData?: Partial<ContactFormData>;
  onSubmit: (data: ContactFormData) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
  submitLabel?: string;
}
```

### Form Data Structure

```typescript
interface ContactFormData {
  firstName: string;      // Required
  lastName: string;       // Required
  email: string;          // Required, validated
  phone?: string;         // Optional
  company?: string;       // Optional
  jobTitle?: string;      // Optional
  address?: string;       // Optional
  city?: string;          // Optional
  state?: string;         // Optional
  zipCode?: string;       // Optional
  country?: string;       // Optional
  notes?: string;         // Optional
  tags?: string[];        // Optional (not currently used in form)
}
```

### UI Components Used

| Component | Source | Purpose |
|-----------|--------|---------|
| `Button` | `../../../components/ui/Button` | Cancel and Submit buttons |
| `FormInput` | `../../../components/forms` | Text input fields |
| `FormTextarea` | `../../../components/forms` | Notes textarea |

### Hooks Used

| Hook | Source | Purpose |
|------|--------|---------|
| `useForm` | `react-hook-form` | Form state management and validation |

### Form Sections

#### 1. Basic Information
| Field | Name | Type | Required | Validation |
|-------|------|------|----------|------------|
| First Name | `firstName` | text | Yes | Required |
| Last Name | `lastName` | text | Yes | Required |
| Email | `email` | email | Yes | Required, email pattern regex |
| Phone | `phone` | tel | No | None |

#### 2. Work Information
| Field | Name | Type | Required | Validation |
|-------|------|------|----------|------------|
| Company | `company` | text | No | None |
| Job Title | `jobTitle` | text | No | None |

#### 3. Address Information
| Field | Name | Type | Required | Validation |
|-------|------|------|----------|------------|
| Street Address | `address` | text | No | None |
| City | `city` | text | No | None |
| State / Province | `state` | text | No | None |
| ZIP / Postal Code | `zipCode` | text | No | None |
| Country | `country` | text | No | None |

#### 4. Notes
| Field | Name | Type | Required | Validation |
|-------|------|------|----------|------------|
| Notes | `notes` | textarea | No | None |

### Validation Rules

| Field | Rule | Error Message |
|-------|------|---------------|
| firstName | Required | "First name is required" |
| lastName | Required | "Last name is required" |
| email | Required | "Email is required" |
| email | Pattern: `/^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i` | "Invalid email address" |

### Form Actions

| Action | Button Variant | Behavior |
|--------|---------------|----------|
| Cancel | Secondary | Calls `onCancel()` prop |
| Submit | Primary | Validates form and calls `onSubmit(data)` |

---

## Data Flow Summary

```
ContactsPage
    |
    |-- useContacts() --> GET /api/contacts (list)
    |-- useCreateContact() --> POST /api/contacts (create)
    |-- useUpdateContact() --> PATCH /api/contacts/:id (update)
    |-- useDeleteContact() --> DELETE /api/contacts/:id (delete)
    |
    v
ContactDetailPage
    |
    |-- useContact(id) --> GET /api/contacts/:id (detail)
    |-- useUpdateContact() --> PATCH /api/contacts/:id (update)
    |-- useDeleteContact() --> DELETE /api/contacts/:id (delete)
    |-- useTimeline('contact', id) --> GET /api/activities/timeline/contact/:id (activities)
```

---

## Related Files

| File | Purpose |
|------|---------|
| `/frontend/src/hooks/useContacts.ts` | Contact-related TanStack Query hooks |
| `/frontend/src/hooks/useActivities.ts` | Activity/Timeline TanStack Query hooks |
| `/frontend/src/api/contacts.ts` | Contact API client functions |
| `/frontend/src/types/index.ts` | TypeScript type definitions |
| `/frontend/src/utils/formatters.ts` | Utility functions for formatting dates/phone numbers |
| `/frontend/src/store/uiStore.ts` | Zustand store for UI state (toasts) |
| `/frontend/src/components/ui/` | Shared UI components (Button, Modal, Spinner, ConfirmDialog) |
| `/frontend/src/components/forms/` | Form components (FormInput, FormTextarea) |
