# Authentication Pages Documentation

This document provides detailed documentation for all authentication pages in the CRM application.

---

## Table of Contents

1. [LoginPage](#loginpage)
2. [RegisterPage](#registerpage)

---

## LoginPage

**File Path:** `/frontend/src/features/auth/LoginPage.tsx`

**Route Path:** `/login`

### Overview

The LoginPage component provides user authentication functionality, allowing existing users to sign in to the CRM application using their email and password credentials.

### UI Components

| Component | Source | Props Used | Purpose |
|-----------|--------|------------|---------|
| `Button` | `../../components/ui/Button` | `type="submit"`, `fullWidth`, `isLoading` | Submit button for the login form |
| `Link` | `react-router-dom` | `to="/register"`, `to="/forgot-password"` | Navigation links to register and forgot password pages |
| `input` | Native HTML | `type="email"`, `type="password"`, `type="checkbox"` | Form input fields |

### Layout Structure

```
div (min-h-screen, centered flex container)
  div (max-w-md card container)
    div (header)
      h2 - "Sign in to your account"
      p - Link to register page
    form
      Error alert (conditional)
      div (form inputs)
        email input
        password input
      div (remember me + forgot password)
        checkbox - Remember me
        Link - Forgot password
      Button - Sign in
```

### Hooks Used

| Hook | Source | Purpose |
|------|--------|---------|
| `useState` | `react` | Manages `isLoading` and `error` states |
| `useForm` | `react-hook-form` | Manages form state, validation, and submission |
| `useNavigate` | `react-router-dom` | Programmatic navigation after successful login |
| `useAuthStore` | `../../store/authStore` | Access to global authentication state and `login` action |

### State Variables

| State | Type | Initial Value | Description |
|-------|------|---------------|-------------|
| `isLoading` | `boolean` | `false` | Indicates if login request is in progress |
| `error` | `string \| null` | `null` | Stores error message from failed login attempts |

### Functions/Handlers

#### `onSubmit(data: LoginRequest)`

**Type:** Async form submission handler

**Triggered By:** Form submission via `handleSubmit(onSubmit)`

**Parameters:**
- `data: LoginRequest` - Object containing `email` and `password`

**Flow:**
1. Set `isLoading` to `true` and clear any existing errors
2. Call `authApi.login(data)` to authenticate with the backend
3. Call `authApi.getMe()` to fetch the user profile
4. Call `storeLogin(user, tokenResult.access_token)` to update auth store
5. Navigate to home page (`/`)
6. On error: Extract and display error message
7. Finally: Set `isLoading` to `false`

```typescript
const onSubmit = async (data: LoginRequest) => {
  setIsLoading(true);
  setError(null);

  try {
    const tokenResult = await authApi.login(data);
    const user = await authApi.getMe();
    storeLogin(user, tokenResult.access_token);
    navigate('/');
  } catch (err: unknown) {
    // Error handling
  } finally {
    setIsLoading(false);
  }
};
```

### API Calls

| API Function | Endpoint | Method | Request Body | Response |
|--------------|----------|--------|--------------|----------|
| `authApi.login` | `/api/auth/login/json` | POST | `{ email: string, password: string }` | `Token { access_token: string, token_type: string }` |
| `authApi.getMe` | `/api/auth/me` | GET | None | `User` object |

### Form Fields and Validation

| Field | Type | Validation Rules | Error Messages |
|-------|------|------------------|----------------|
| `email` | `email` | Required, Pattern: `/^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i` | "Email is required", "Invalid email address" |
| `password` | `password` | Required | "Password is required" |
| `remember-me` | `checkbox` | None (not connected to form state) | N/A |

**Form Default Values:**
```typescript
{
  email: '',
  password: ''
}
```

### Navigation Flows

| Action | Destination | Condition |
|--------|-------------|-----------|
| Successful login | `/` (Home/Dashboard) | After authentication completes |
| Click "create a new account" | `/register` | User clicks link |
| Click "Forgot your password?" | `/forgot-password` | User clicks link |

### Error Handling

The component handles errors by:
1. Checking if error is an instance of `Error` and extracting the message
2. Checking if error has a `detail` property (API error format)
3. Falling back to "An error occurred" for unknown errors

Errors are displayed in a red alert box above the form fields.

---

## RegisterPage

**File Path:** `/frontend/src/features/auth/RegisterPage.tsx`

**Route Path:** `/register`

### Overview

The RegisterPage component allows new users to create an account in the CRM application. It collects user information including name, email, and password with confirmation.

### UI Components

| Component | Source | Props Used | Purpose |
|-----------|--------|------------|---------|
| `Button` | `../../components/ui/Button` | `type="submit"`, `fullWidth`, `isLoading` | Submit button for the registration form |
| `Link` | `react-router-dom` | `to="/login"`, `to="/terms"`, `to="/privacy"` | Navigation links |
| `input` | Native HTML | `type="text"`, `type="email"`, `type="password"`, `type="checkbox"` | Form input fields |

### Layout Structure

```
div (min-h-screen, centered flex container)
  div (max-w-md card container)
    div (header)
      h2 - "Create your account"
      p - Link to login page
    form
      Error alert (conditional)
      div (form inputs)
        div (grid for name fields)
          firstName input
          lastName input
        email input
        password input
        confirmPassword input
      div (terms checkbox)
        checkbox - Terms agreement
        Links to Terms of Service and Privacy Policy
      Button - Create account
```

### Hooks Used

| Hook | Source | Purpose |
|------|--------|---------|
| `useState` | `react` | Manages `isLoading` and `error` states |
| `useForm` | `react-hook-form` | Manages form state, validation, and submission |
| `useNavigate` | `react-router-dom` | Programmatic navigation after successful registration |

### State Variables

| State | Type | Initial Value | Description |
|-------|------|---------------|-------------|
| `isLoading` | `boolean` | `false` | Indicates if registration request is in progress |
| `error` | `string \| null` | `null` | Stores error message from failed registration attempts |

### Form Data Interface

```typescript
interface RegisterFormData {
  firstName: string;
  lastName: string;
  email: string;
  password: string;
  confirmPassword: string;
}
```

### Functions/Handlers

#### `onSubmit(data: RegisterFormData)`

**Type:** Async form submission handler

**Triggered By:** Form submission via `handleSubmit(onSubmit)`

**Parameters:**
- `data: RegisterFormData` - Object containing all registration fields

**Flow:**
1. Set `isLoading` to `true` and clear any existing errors
2. Call `authApi.register()` with transformed data:
   - Combines `firstName` and `lastName` into `full_name`
   - Passes `email` and `password`
3. Navigate to `/login` with success message in state
4. On error: Extract and display error message
5. Finally: Set `isLoading` to `false`

```typescript
const onSubmit = async (data: RegisterFormData) => {
  setIsLoading(true);
  setError(null);

  try {
    await authApi.register({
      email: data.email,
      password: data.password,
      full_name: `${data.firstName} ${data.lastName}`.trim(),
    });

    navigate('/login', {
      state: { message: 'Registration successful. Please sign in.' },
    });
  } catch (err) {
    // Error handling
  } finally {
    setIsLoading(false);
  }
};
```

#### `watch('password')`

**Type:** Form watch function

**Purpose:** Watches the password field value for use in confirmPassword validation

```typescript
const password = watch('password');
```

### API Calls

| API Function | Endpoint | Method | Request Body | Response |
|--------------|----------|--------|--------------|----------|
| `authApi.register` | `/api/auth/register` | POST | `UserCreate { email: string, full_name: string, password: string }` | `User` object |

### Form Fields and Validation

| Field | Type | Validation Rules | Error Messages |
|-------|------|------------------|----------------|
| `firstName` | `text` | Required | "First name is required" |
| `lastName` | `text` | Required | "Last name is required" |
| `email` | `email` | Required, Pattern: `/^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i` | "Email is required", "Invalid email address" |
| `password` | `password` | Required | "Password is required" |
| `confirmPassword` | `password` | Required, Must match password | "Please confirm your password", "Passwords do not match" |
| `terms` | `checkbox` | Required (HTML native) | Browser default required message |

**Form Default Values:**
```typescript
{
  firstName: '',
  lastName: '',
  email: '',
  password: '',
  confirmPassword: ''
}
```

**Password Confirmation Validation:**
```typescript
{
  required: 'Please confirm your password',
  validate: (value) => value === password || 'Passwords do not match'
}
```

### Navigation Flows

| Action | Destination | State Passed | Condition |
|--------|-------------|--------------|-----------|
| Successful registration | `/login` | `{ message: 'Registration successful. Please sign in.' }` | After registration completes |
| Click "Sign in" | `/login` | None | User clicks link |
| Click "Terms of Service" | `/terms` | None | User clicks link |
| Click "Privacy Policy" | `/privacy` | None | User clicks link |

### Error Handling

The component handles errors by:
1. Checking if error is an instance of `Error` and extracting the message
2. Checking for Axios-style error response with `response.data.detail`
3. Falling back to "An error occurred" for unknown errors

Errors are displayed in a red alert box above the form fields.

---

## Shared Dependencies

### Button Component

**Path:** `/frontend/src/components/ui/Button.tsx`

**Props Interface:**
```typescript
interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  fullWidth?: boolean;
}
```

### Auth Store (Zustand)

**Path:** `/frontend/src/store/authStore.ts`

**State:**
```typescript
interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}
```

**Actions Used:**
- `login(user: User, token: string)` - Sets user, token, and isAuthenticated

### Auth API

**Path:** `/frontend/src/api/auth.ts`

**Functions Used:**
- `login(credentials: LoginRequest)` - Authenticates user and returns token
- `register(userData: UserCreate)` - Creates new user account
- `getMe()` - Fetches current user profile

### Types

**Path:** `/frontend/src/types/index.ts`

**Types Used:**
- `LoginRequest` - `{ email: string, password: string }`
- `UserCreate` - `{ email: string, full_name: string, password: string, phone?: string, job_title?: string }`
- `Token` - `{ access_token: string, token_type: string }`
- `User` - Full user object with id, email, full_name, etc.

---

## Styling

Both pages use Tailwind CSS with the following common patterns:

### Container Styling
- `min-h-screen` - Full viewport height
- `flex items-center justify-center` - Centered content
- `bg-gray-50` - Light gray background
- `max-w-md w-full` - Constrained width form container

### Form Input Styling
- `appearance-none` - Reset browser styles
- `relative block w-full` - Full width inputs
- `px-3 py-2` - Consistent padding
- `border border-gray-300` - Subtle border
- `rounded-md` / `rounded-t-md` / `rounded-b-md` - Rounded corners
- `focus:ring-primary-500 focus:border-primary-500` - Focus states

### Error Styling
- `rounded-md bg-red-50 p-4` - Error container
- `text-sm text-red-600` - Inline validation errors
- `text-sm font-medium text-red-800` - Error alert text

### Link Styling
- `text-primary-600 hover:text-primary-500` - Primary colored links
- `font-medium` - Slightly bolder link text
