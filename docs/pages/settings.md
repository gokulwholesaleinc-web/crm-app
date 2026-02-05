# Settings Page Documentation

## Page Information

| Property | Value |
|----------|-------|
| **Page Name** | SettingsPage |
| **File Path** | `/Users/harshvarma/crm-app/frontend/src/features/settings/SettingsPage.tsx` |
| **Route Path** | `/settings` (inferred from file location) |

## UI Components Used

### Custom Components

| Component | Import Path | Usage |
|-----------|-------------|-------|
| `Card` | `../../components/ui/Card` | Container for profile, account settings, and status sections |
| `CardHeader` | `../../components/ui/Card` | Header with title and description for each card section |
| `CardBody` | `../../components/ui/Card` | Content area within cards |
| `Avatar` | `../../components/ui/Avatar` | Displays user profile picture |
| `Spinner` | `../../components/ui/Spinner` | Loading indicator when data is being fetched |

### Heroicons (External Icons)

| Icon | Import Path | Usage |
|------|-------------|-------|
| `UserCircleIcon` | `@heroicons/react/24/outline` | Edit Profile settings icon |
| `Cog6ToothIcon` | `@heroicons/react/24/outline` | Preferences settings icon |
| `BellIcon` | `@heroicons/react/24/outline` | Notifications settings icon |
| `ShieldCheckIcon` | `@heroicons/react/24/outline` | Security settings icon |

## Functions/Handlers

| Function | Type | Description |
|----------|------|-------------|
| `SettingsPage` | Component Function | Main page component that renders the settings interface |

**Note:** This page is currently display-only with no interactive handlers. All settings sections show "Coming soon" status.

## Hooks Used

| Hook | Source | Purpose |
|------|--------|---------|
| `useAuthStore` | `../../store/authStore` | Zustand store hook to access authenticated user data and loading state |

### Destructured Values from `useAuthStore`:
- `user` - Current authenticated user object
- `isLoading` - Boolean indicating if auth data is being loaded

## API Calls Made

This page does not make direct API calls. It relies on the `useAuthStore` which manages user authentication state. The user data is fetched during the authentication flow and stored in the auth store.

## Data Displayed

### Profile Section
| Field | Source | Format |
|-------|--------|--------|
| Avatar | `user?.avatar_url` | Image via Avatar component |
| Full Name | `user?.full_name` | Text, falls back to "Not set" |
| Email | `user?.email` | Text, falls back to "Not set" |
| Phone | `user?.phone` | Text, falls back to "Not set" |
| Job Title | `user?.job_title` | Text, falls back to "Not set" |
| Member Since | `user?.created_at` | Formatted date (e.g., "February 4, 2026") |

### Account Settings Section (Coming Soon)
- Notifications - Email and push notification preferences
- Security - Password, two-factor authentication, and sessions
- Preferences - Language, timezone, and display settings
- Edit Profile - Personal information and avatar updates

### Account Status Section
| Field | Source | Format |
|-------|--------|--------|
| Status | `user?.is_active` | "Active" (green dot) or "Inactive" (red dot) |
| Role | `user?.is_superuser` | "Administrator" or "User" |
| Last Login | `user?.last_login` | Formatted date with time (e.g., "Feb 4, 2026, 10:30 AM") or "Never" |

## Interactive Elements

| Element | Type | Interaction | Status |
|---------|------|-------------|--------|
| Notifications Setting | Display Row | None (disabled) | Coming soon |
| Security Setting | Display Row | None (disabled) | Coming soon |
| Preferences Setting | Display Row | None (disabled) | Coming soon |
| Edit Profile Setting | Display Row | None (disabled) | Coming soon |

**Note:** Currently, there are no interactive elements on this page. All settings rows display "Coming soon" and are not clickable. The page serves as a read-only view of user profile and account information.

## Component Structure

```
SettingsPage
├── Loading State (Spinner)
└── Main Content
    ├── Page Header
    │   ├── Title: "Settings"
    │   └── Description
    ├── Profile Card
    │   ├── CardHeader
    │   └── CardBody
    │       ├── Avatar
    │       └── User Info Grid
    ├── Account Settings Card
    │   ├── CardHeader
    │   └── CardBody
    │       ├── Notifications Row
    │       ├── Security Row
    │       ├── Preferences Row
    │       └── Edit Profile Row
    └── Account Status Card
        ├── CardHeader
        └── CardBody
            └── Status Grid (3 columns)
                ├── Status
                ├── Role
                └── Last Login
```
