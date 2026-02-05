# Companies Module Documentation

This document provides detailed documentation for the Companies feature pages in the CRM application.

---

## Table of Contents

1. [CompaniesPage](#companiespage)
2. [CompanyDetailPage](#companydetailpage)
3. [CompanyForm Component](#companyform-component)
4. [Shared Types and Interfaces](#shared-types-and-interfaces)

---

## CompaniesPage

### Overview

**File Path:** `/frontend/src/features/companies/CompaniesPage.tsx`

**Route Path:** `/companies`

**Purpose:** Displays a paginated, filterable list of companies in a card-based grid layout with search, filter, and CRUD capabilities.

---

### UI Components Used

| Component | Source | Purpose |
|-----------|--------|---------|
| `Button` | `../../components/ui` | Primary actions (Add Company, Filters toggle, Pagination) |
| `Input` | `../../components/ui` | Search input field |
| `Select` | `../../components/ui` | Filter dropdowns (Status, Industry) |
| `Spinner` | `../../components/ui` | Loading indicator |
| `Modal` | `../../components/ui` | Form modal for create/edit |
| `ConfirmDialog` | `../../components/ui` | Delete confirmation dialog |
| `CompanyForm` | `./components/CompanyForm` | Create/Edit company form |
| `CompanyCard` | Internal component | Individual company card display |

#### Heroicons Used

- `PlusIcon` - Add Company button
- `FunnelIcon` - Filters toggle button
- `MagnifyingGlassIcon` - Search input icon
- `BuildingOffice2Icon` - Company logo placeholder, empty state icon
- `GlobeAltIcon` - Website link icon
- `UsersIcon` - Contact count icon

---

### Functions and Handlers

#### Filter and Search Handlers

| Function | Description | Parameters |
|----------|-------------|------------|
| `updateFilter` | Updates URL search params for filtering | `key: string, value: string` |
| `handleSearch` | Form submit handler for search | `e: React.FormEvent` |

#### CRUD Operations

| Function | Description | Parameters |
|----------|-------------|------------|
| `handleDeleteClick` | Opens delete confirmation dialog | `company: Company` |
| `handleDeleteConfirm` | Executes company deletion | None |
| `handleDeleteCancel` | Closes delete confirmation dialog | None |
| `handleEdit` | Opens edit form modal | `company: Company` |
| `handleFormSubmit` | Handles form submission (create/update) | `data: CompanyCreate \| CompanyUpdate` |
| `handleFormCancel` | Closes form modal | None |

---

### Hooks Used

| Hook | Source | Purpose |
|------|--------|---------|
| `useState` | React | Local state management (showFilters, showForm, editingCompany, searchQuery, deleteConfirm) |
| `useMemo` | React | Memoize filter values from URL params |
| `useSearchParams` | react-router-dom | URL query parameter management |
| `useNavigate` | react-router-dom | Programmatic navigation |
| `useCompanies` | `../../hooks/useCompanies` | Fetch paginated company list |
| `useCreateCompany` | `../../hooks/useCompanies` | Create company mutation |
| `useUpdateCompany` | `../../hooks/useCompanies` | Update company mutation |
| `useDeleteCompany` | `../../hooks/useCompanies` | Delete company mutation |

---

### API Calls

| Operation | Endpoint | Method | Triggered By |
|-----------|----------|--------|--------------|
| List Companies | `GET /api/companies` | GET | `useCompanies(filters)` on component mount/filter change |
| Create Company | `POST /api/companies` | POST | `createCompany.mutateAsync(data)` |
| Update Company | `PATCH /api/companies/:id` | PATCH | `updateCompany.mutateAsync({ id, data })` |
| Delete Company | `DELETE /api/companies/:id` | DELETE | `deleteCompany.mutateAsync(id)` |

---

### Filter Options

#### Status Options

| Value | Label |
|-------|-------|
| `''` | All Status |
| `prospect` | Prospect |
| `customer` | Customer |
| `churned` | Churned |

#### Industry Options

| Value | Label |
|-------|-------|
| `''` | All Industries |
| `technology` | Technology |
| `healthcare` | Healthcare |
| `finance` | Finance |
| `manufacturing` | Manufacturing |
| `retail` | Retail |
| `education` | Education |
| `real_estate` | Real Estate |
| `consulting` | Consulting |
| `media` | Media & Entertainment |
| `other` | Other |

---

### URL Query Parameters (CompanyFilters)

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | number | 1 | Current page number |
| `page_size` | number | 12 | Items per page |
| `search` | string | undefined | Search query |
| `status` | string | undefined | Filter by company status |
| `industry` | string | undefined | Filter by industry |

---

### Local State

| State Variable | Type | Initial Value | Purpose |
|----------------|------|---------------|---------|
| `showFilters` | boolean | `false` | Toggle filter panel visibility |
| `showForm` | boolean | `false` | Toggle form modal visibility |
| `editingCompany` | `Company \| null` | `null` | Company being edited |
| `searchQuery` | string | URL param or `''` | Search input value |
| `deleteConfirm` | `{ isOpen: boolean; company: Company \| null }` | `{ isOpen: false, company: null }` | Delete dialog state |

---

### Navigation Flows

| Action | Destination |
|--------|-------------|
| Click on company card | `/companies/:id` (Company Detail Page) |
| Click "Add Company" | Opens CompanyForm modal |
| Click edit button on card | Opens CompanyForm modal with company data |
| Successful delete | Stays on list, refreshes data |

---

### CompanyCard Component (Internal)

#### Props

```typescript
interface CompanyCardProps {
  company: Company;
  onClick: () => void;
  onEdit: () => void;
  onDelete: () => void;
}
```

#### Displayed Information

- Company logo (or placeholder icon)
- Company name
- Status badge (color-coded)
- Industry
- Website link (clickable, opens in new tab)
- Contact count
- Location (city, country)
- Annual revenue (formatted)
- Tags (up to 3 shown, with "+X more" indicator)

---

## CompanyDetailPage

### Overview

**File Path:** `/frontend/src/features/companies/CompanyDetailPage.tsx`

**Route Path:** `/companies/:id`

**Purpose:** Displays detailed information about a single company, including associated contacts, contact information, business details, social links, and tags.

---

### UI Components Used

| Component | Source | Purpose |
|-----------|--------|---------|
| `Button` | `../../components/ui` | Edit, Delete, Back, Add Contact buttons |
| `Spinner` | `../../components/ui` | Loading indicator |
| `Modal` | `../../components/ui` | Edit form modal |
| `ConfirmDialog` | `../../components/ui` | Delete confirmation dialog |
| `CompanyForm` | `./components/CompanyForm` | Edit company form |
| `DetailItem` | Internal component | Individual detail row display |
| `ContactRow` | Internal component | Contact list item display |
| `Link` | react-router-dom | Navigation links |

#### Heroicons Used

- `ArrowLeftIcon` - Back navigation button
- `BuildingOffice2Icon` - Company logo placeholder
- `GlobeAltIcon` - Website detail icon
- `EnvelopeIcon` - Email detail icon
- `PhoneIcon` - Phone detail icon
- `MapPinIcon` - Address detail icon
- `UsersIcon` - Empty contacts state icon
- `LinkIcon` - Social links icons

---

### Functions and Handlers

#### CRUD Operations

| Function | Description | Parameters |
|----------|-------------|------------|
| `handleDeleteConfirm` | Executes company deletion and navigates back | None |
| `handleFormSubmit` | Handles edit form submission | `data: CompanyUpdate` |

---

### Hooks Used

| Hook | Source | Purpose |
|------|--------|---------|
| `useState` | React | Local state management (showEditForm, showDeleteConfirm) |
| `useParams` | react-router-dom | Extract company ID from URL |
| `useNavigate` | react-router-dom | Programmatic navigation |
| `useCompany` | `../../hooks/useCompanies` | Fetch single company data |
| `useUpdateCompany` | `../../hooks/useCompanies` | Update company mutation |
| `useDeleteCompany` | `../../hooks/useCompanies` | Delete company mutation |
| `useContacts` | `../../hooks/useContacts` | Fetch contacts for this company |

---

### API Calls

| Operation | Endpoint | Method | Triggered By |
|-----------|----------|--------|--------------|
| Get Company | `GET /api/companies/:id` | GET | `useCompany(companyId)` on mount |
| List Company Contacts | `GET /api/contacts?company_id=:id` | GET | `useContacts({ company_id, page_size: 50 })` on mount |
| Update Company | `PATCH /api/companies/:id` | PATCH | `updateCompany.mutateAsync({ id, data })` |
| Delete Company | `DELETE /api/companies/:id` | DELETE | `deleteCompany.mutateAsync(id)` |

---

### Local State

| State Variable | Type | Initial Value | Purpose |
|----------------|------|---------------|---------|
| `showEditForm` | boolean | `false` | Toggle edit form modal visibility |
| `showDeleteConfirm` | boolean | `false` | Toggle delete confirmation dialog |

---

### Page Layout Sections

#### Header Section

- Back button (navigates to `/companies`)
- Company logo (or placeholder)
- Company name
- Status badge
- Industry label
- Edit button
- Delete button

#### Main Content (2/3 width)

1. **About Section** (if description exists)
   - Company description text

2. **Contacts Section**
   - Contact count header
   - "Add Contact" button (navigates to `/contacts?company_id=:id&action=new`)
   - List of associated contacts with:
     - Avatar (or initials)
     - Full name
     - Job title and department
     - Email
     - Phone

#### Sidebar (1/3 width)

1. **Contact Information Card**
   - Website (clickable link)
   - Email (mailto link)
   - Phone (tel link)
   - Full address

2. **Business Details Card**
   - Annual Revenue (formatted currency)
   - Employee Count (formatted number)
   - Company Size

3. **Social Links Card** (if available)
   - LinkedIn URL
   - Twitter Handle

4. **Tags Card** (if tags exist)
   - Tag badges with colors

5. **Record Info Card**
   - Created date
   - Last updated date

---

### Navigation Flows

| Action | Destination |
|--------|-------------|
| Click back button | `/companies` |
| Click "Add Contact" | `/contacts?company_id=:id&action=new` |
| Click on contact row | `/contacts/:contactId` |
| Click Edit button | Opens CompanyForm modal |
| Successful delete | `/companies` |

---

### Internal Components

#### DetailItem Component

```typescript
interface DetailItemProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | null | undefined;
  link?: string;
}
```

Displays a single detail row with icon, label, and value. Optionally renders as a link.

#### ContactRow Component

```typescript
interface ContactRowProps {
  contact: Contact;
}
```

Displays a contact list item with avatar, name, title, and contact info.

---

## CompanyForm Component

### Overview

**File Path:** `/frontend/src/features/companies/components/CompanyForm.tsx`

**Purpose:** Reusable form component for creating and editing companies.

---

### Props

```typescript
interface CompanyFormProps {
  company?: Company;           // Optional existing company for edit mode
  onSubmit: (data: CompanyCreate | CompanyUpdate) => Promise<void>;
  onCancel: () => void;
  isLoading?: boolean;
}
```

---

### Form Fields and Validation

| Field Name | Type | Label | Validation | Placeholder |
|------------|------|-------|------------|-------------|
| `name` | text | Company Name | **Required** | "Enter company name" |
| `status` | select | Status | Required (default: 'prospect') | - |
| `website` | text | Website | Optional | "https://example.com" |
| `email` | email | Email | Optional | "contact@example.com" |
| `industry` | select | Industry | Optional | "Select industry..." |
| `company_size` | select | Company Size | Optional | "Select size..." |
| `phone` | text | Phone | Optional | "+1 (555) 000-0000" |
| `annual_revenue` | number | Annual Revenue | Optional | "0" |
| `employee_count` | number | Employee Count | Optional | "0" |
| `address_line1` | text | Address Line 1 | Optional | "Street address" |
| `address_line2` | text | Address Line 2 | Optional | "Suite, unit, etc. (optional)" |
| `city` | text | City | Optional | "City" |
| `state` | text | State/Province | Optional | "State" |
| `postal_code` | text | Postal Code | Optional | "Postal code" |
| `country` | text | Country | Optional | "Country" |
| `linkedin_url` | text | LinkedIn URL | Optional | "https://linkedin.com/company/..." |
| `twitter_handle` | text | Twitter Handle | Optional | "@companyhandle" |
| `description` | textarea | Description | Optional | "Add notes about the company" |

---

### Form Sections

1. **Basic Info**
   - Company Name, Status
   - Website, Email
   - Industry, Company Size
   - Phone

2. **Business Details**
   - Annual Revenue, Employee Count

3. **Address**
   - Address Line 1
   - Address Line 2
   - City, State
   - Postal Code, Country

4. **Social Links**
   - LinkedIn URL, Twitter Handle

5. **Description**
   - Textarea for notes

---

### Select Options

#### Status Options

| Value | Label |
|-------|-------|
| `prospect` | Prospect |
| `customer` | Customer |
| `churned` | Churned |

#### Company Size Options

| Value | Label |
|-------|-------|
| `''` | Select size... |
| `1-10` | 1-10 employees |
| `11-50` | 11-50 employees |
| `51-200` | 51-200 employees |
| `201-500` | 201-500 employees |
| `501-1000` | 501-1000 employees |
| `1001-5000` | 1001-5000 employees |
| `5001+` | 5001+ employees |

#### Industry Options

| Value | Label |
|-------|-------|
| `''` | Select industry... |
| `technology` | Technology |
| `healthcare` | Healthcare |
| `finance` | Finance |
| `manufacturing` | Manufacturing |
| `retail` | Retail |
| `education` | Education |
| `real_estate` | Real Estate |
| `consulting` | Consulting |
| `media` | Media & Entertainment |
| `other` | Other |

---

### Hooks Used

| Hook | Source | Purpose |
|------|--------|---------|
| `useEffect` | React | Reset form when company prop changes |
| `useForm` | react-hook-form | Form state management |
| `Controller` | react-hook-form | Controlled components for Select inputs |

---

### Form Submission Data Transformation

The `onFormSubmit` function transforms form values before submission:

- Empty strings are converted to `undefined`
- `annual_revenue` and `employee_count` are parsed as integers
- All fields are passed through, with empty optional fields omitted

---

## Shared Types and Interfaces

### Company Type

```typescript
interface Company {
  id: number;
  name: string;
  website?: string | null;
  industry?: string | null;
  company_size?: string | null;
  phone?: string | null;
  email?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  annual_revenue?: number | null;
  employee_count?: number | null;
  linkedin_url?: string | null;
  twitter_handle?: string | null;
  description?: string | null;
  status: string;
  owner_id?: number | null;
  logo_url?: string | null;
  created_at: string;
  updated_at: string;
  tags: TagBrief[];
  contact_count: number;
}
```

### CompanyCreate Type

```typescript
interface CompanyCreate {
  name: string;
  website?: string | null;
  industry?: string | null;
  company_size?: string | null;
  phone?: string | null;
  email?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  annual_revenue?: number | null;
  employee_count?: number | null;
  linkedin_url?: string | null;
  twitter_handle?: string | null;
  description?: string | null;
  status: string;
  owner_id?: number | null;
  tag_ids?: number[] | null;
}
```

### CompanyUpdate Type

```typescript
interface CompanyUpdate extends Partial<CompanyBase> {
  tag_ids?: number[] | null;
}
```

### CompanyFilters Type

```typescript
interface CompanyFilters {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  industry?: string;
  owner_id?: number;
  tag_ids?: string;
}
```

### TagBrief Type

```typescript
interface TagBrief {
  id: number;
  name: string;
  color?: string | null;
}
```

---

## Utility Functions Used

### From `../../utils/statusColors`

| Function | Purpose |
|----------|---------|
| `getStatusColor(status, 'company')` | Returns `{ bg, text }` color classes for status badges |
| `formatStatusLabel(status)` | Formats status string for display (capitalizes, replaces underscores) |

### From `../../utils/formatters`

| Function | Purpose |
|----------|---------|
| `formatCurrency(amount)` | Formats number as currency string |
| `formatDate(date, 'long')` | Formats date string for display |

---

## API Module

**File Path:** `/frontend/src/api/companies.ts`

### Exported Functions

| Function | Endpoint | Method | Description |
|----------|----------|--------|-------------|
| `listCompanies(filters)` | `GET /api/companies` | GET | List companies with pagination and filters |
| `getCompany(id)` | `GET /api/companies/:id` | GET | Get single company by ID |
| `createCompany(data)` | `POST /api/companies` | POST | Create new company |
| `updateCompany(id, data)` | `PATCH /api/companies/:id` | PATCH | Update existing company |
| `deleteCompany(id)` | `DELETE /api/companies/:id` | DELETE | Delete company |

---

## Custom Hooks

**File Path:** `/frontend/src/hooks/useCompanies.ts`

### Exported Hooks

| Hook | Purpose | Return Type |
|------|---------|-------------|
| `useCompanies(filters?)` | Fetch paginated company list | `UseQueryResult<CompanyListResponse>` |
| `useCompany(id)` | Fetch single company | `UseQueryResult<Company>` |
| `useCreateCompany()` | Create company mutation | `UseMutationResult` |
| `useUpdateCompany()` | Update company mutation | `UseMutationResult` |
| `useDeleteCompany()` | Delete company mutation | `UseMutationResult` |
| `useCompanySearch(term, limit?)` | Search companies by name | `UseQueryResult<Company[]>` |

All hooks use TanStack Query for data fetching and caching, following the entity CRUD factory pattern.
