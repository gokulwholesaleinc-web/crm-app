# Global UX / Layout / Theming Audit

## Summary

Audited: `index.html`, `main.tsx`, `App.tsx`, `routes/index.tsx`, `routes/PrivateRoute.tsx`,
`components/layout/Layout.tsx`, `components/layout/Sidebar.tsx`, `components/layout/Header.tsx`,
`components/layout/MobileSidebar.tsx`, `components/layout/navigation.config.ts`,
`components/ErrorBoundary.tsx`, `components/notifications/NotificationBell.tsx`,
`store/authStore.ts`, `store/uiStore.ts`, `providers/TenantProvider.tsx`,
`hooks/useTheme.ts`, `hooks/useAuth.ts`, `hooks/useAuthQuery.ts`, `hooks/useNotifications.ts`,
`hooks/useUnsavedChangesWarning.ts`, `hooks/usePageTitle.ts`, `api/client.ts`,
`utils/toast.ts`, `config/queryConfig.ts`, `index.css`.

**Severity counts:**

| Severity | Count |
|----------|-------|
| CRITICAL | 3     |
| HIGH     | 4     |
| MEDIUM   | 5     |
| LOW      | 4     |

**Total findings: 16**

---

## Findings

### [CRITICAL] Theme State Split — Two Independent Sources of Truth

- **File:** `store/uiStore.ts:37` and `hooks/useTheme.ts:1`
- **Problem:** `uiStore` stores a `theme` field (`'light' | 'dark' | 'system'`) persisted under `crm-ui-storage`. `useTheme` has its own separate state, reads/writes `crm-theme` in localStorage, and is what `ThemeInitializer` and `Header` actually use. The `uiStore.setTheme` action is never called by any component. The two stores can silently diverge — if anything reads `uiStore().theme` it will always return the initial `'system'` value regardless of user selection.
- **Why it matters:** Dead state in a persisted store grows silently. Also `'system'` is not a valid value in `useTheme`'s `Theme` type (`'light' | 'dark'`), so the types are misaligned.
- **Fix:** Delete `theme` and `setTheme` from `uiStore` entirely. Let `useTheme` remain the single source of truth.

---

### [CRITICAL] Toaster aria-live Wrapper Conflicts with react-hot-toast's Own Live Region

- **File:** `App.tsx:88-104`
- **Problem:** `<Toaster>` is wrapped in `<div aria-live="polite" aria-atomic="true">`. react-hot-toast already renders its own internal `<ol aria-live="polite">` live region. The outer wrapper causes double-announcement on screen readers, and `aria-atomic="true"` on the wrapper can suppress individual item announcements and read the entire list on any change.
- **Why it matters:** Screen reader users hear every toast announced twice. CLAUDE.md: "Async updates (toasts, validation) need `aria-live='polite'`" — the intent is correct but the implementation creates the problem.
- **Fix:** Remove the outer `<div aria-live="polite" aria-atomic="true">` wrapper entirely. Trust react-hot-toast's built-in accessibility.

---

### [CRITICAL] No `<meta name="color-scheme">` in index.html

- **File:** `index.html` (missing tag)
- **Problem:** The inline script sets `document.documentElement.style.colorScheme = 'dark'` correctly when dark is inferred from localStorage. But `<meta name="color-scheme" content="light dark">` is entirely absent from `<head>`. Without it, the browser's native UI elements (scrollbars, form controls, `<select>` dropdowns) render in light mode on the first paint, even when the app theme is dark.
- **Why it matters:** Per CLAUDE.md: "Set `color-scheme: dark` on `<html>` for dark themes." The inline style does apply it after JS runs, but native controls remain light until then.
- **Fix:** Add `<meta name="color-scheme" content="light dark">` to `<head>`. The inline script can remain as the post-JS authoritative override.

---

### [HIGH] `/profile` Route Linked but Not Defined — Silent Redirect Loop

- **File:** `components/layout/Header.tsx:143`, `routes/index.tsx`
- **Problem:** The user dropdown has `<Link to="/profile">Your Profile</Link>`. No `/profile` route exists. The catch-all `<Route path="*" element={<Navigate to="/" replace />}` silently redirects users to the dashboard when they click "Your Profile", with no error or explanation.
- **Why it matters:** Broken navigation item visible to every logged-in user. The user experiences confusing silent failure — they click a link and end up on the dashboard with no feedback.
- **Fix:** Either add a `/profile` route (probably a tab in `/settings`, where `EditProfileModal` already exists), or change the link to `to="/settings"`.

---

### [HIGH] `usePageTitle` Hardcodes "CRM App" — Overwrites Tenant Branding

- **File:** `hooks/usePageTitle.ts:5`
- **Problem:** `usePageTitle` sets `` document.title = `${title} - CRM App` ``. The `TenantProvider` separately sets `` document.title = `${config.company_name} - CRM` `` when branding loads. If a page calls `usePageTitle` after tenant branding loads, it overwrites the company name with the hardcoded "CRM App" string. Whichever hook runs last wins.
- **Why it matters:** Tenants using white-label branding see their company name replaced by "CRM App" as each page mounts.
- **Fix:** Inside `usePageTitle`, read `tenant?.company_name` from `useTenant()` and compose: `` `${title} - ${companyName || 'CRM'}` ``.

---

### [HIGH] Notification Panel Missing `aria-expanded`, `aria-haspopup`, Focus Trap, and Live Announcement

- **File:** `components/notifications/NotificationBell.tsx:106-137`
- **Problem:** The bell button has `aria-label="View notifications"` but no `aria-haspopup` or `aria-expanded`. The dropdown panel div has no `role="dialog"`, and focus is not trapped or moved into the panel when it opens. When notifications update via polling, the new count is not announced.
- **Why it matters:** Keyboard users cannot access the notification list. Screen reader users receive no feedback when notifications arrive. CLAUDE.md: "Async updates (toasts, validation) need `aria-live='polite'`."
- **Fix:** Add `aria-haspopup="true"` and `aria-expanded={isOpen}` to the bell button. Add `role="dialog"` and `aria-label="Notifications"` to the panel. Move focus into the panel on open. Trap focus within it. Add a `aria-live="polite"` span for unread count changes.

---

### [HIGH] `localStorage` Read in Axios Interceptor on Every Request — No Module-Level Cache

- **File:** `api/client.ts:51-55`
- **Problem:** The request interceptor reads `localStorage.getItem(TENANT_SLUG_KEY)` synchronously on every single API request. The tenant slug is static within a session — it only changes on login/logout. Per CLAUDE.md: "Cache localStorage/sessionStorage reads in a module-level Map."
- **Why it matters:** On pages with many parallel queries (dashboard, list pages), this fires `localStorage.getItem` 10–20+ times simultaneously with no caching.
- **Fix:** Cache the slug in a module-level variable and update it only when the `tenant-slug-changed` event fires.

---

### [MEDIUM] `uiStore` Contains Dead State — `toasts`, `modals`, `globalLoading`, `commandPaletteOpen` All Unused

- **File:** `store/uiStore.ts:20-50`
- **Problem:** The app uses react-hot-toast (via `utils/toast.ts` and `<Toaster>` in `App.tsx`) exclusively for toasts. The `addToast`, `removeToast`, `clearToasts`, `openModal`, `closeModal`, `closeAllModals`, `setGlobalLoading`, `toggleCommandPalette`, `setCommandPaletteOpen` actions and their state fields in `uiStore` have no consumers. The `commandPaletteOpen` state exists but no command palette component exists in the codebase.
- **Why it matters:** Dead state in a global store is confusion debt. Future developers will trust these fields are used.
- **Fix:** Audit all consumers of `uiStore`. Remove unused fields and actions. If command palette is planned, add it when implemented.

---

### [MEDIUM] `MobileSidebar` Does Not Restore Focus to Trigger Button on Close

- **File:** `components/layout/MobileSidebar.tsx:47-56`
- **Problem:** When the mobile sidebar closes (via Escape, overlay click, or nav link click), focus is not returned to the hamburger button that opened it. The user loses their focus position, violating WCAG 2.1 SC 2.4.3 (Focus Order).
- **Why it matters:** Keyboard and screen reader users who open the nav drawer then press Escape find focus disappearing to `<body>`.
- **Fix:** Pass a `triggerRef` to `MobileSidebar` (or use a callback). In `Layout.tsx`, create `const menuButtonRef = useRef<HTMLButtonElement>(null)` on the hamburger button and call `menuButtonRef.current?.focus()` in `onClose`.

---

### [MEDIUM] Skip Link Uses `:focus` Not `:focus-visible`

- **File:** `index.css:236`
- **Problem:** `.skip-link:focus { top: 0; }` uses `:focus` rather than `:focus-visible`. Per CLAUDE.md: "Use `:focus-visible` over `:focus` to avoid focus ring on click." On mouse click the skip link briefly appears before the browser moves focus, causing a visible flash.
- **Why it matters:** Cosmetic but explicitly called out in CLAUDE.md guidelines.
- **Fix:** Change `.skip-link:focus` to `.skip-link:focus-visible`. Also consider animating `transform: translateY` instead of `top` for compositor efficiency (CLAUDE.md: "Animate only `transform` and `opacity`").

---

### [MEDIUM] `Header.tsx` Search Input Has No `autocomplete` Attribute

- **File:** `components/layout/Header.tsx:70-83`
- **Problem:** The desktop search input (`type="search"`) lacks `autocomplete="off"` or a meaningful `autocomplete` value. CLAUDE.md: "Inputs need `autocomplete` and meaningful `name` attributes." The input also lacks a `name` attribute.
- **Why it matters:** Browser autofill may inject stale search terms. Minor but per-guideline non-compliance.
- **Fix:** Add `autocomplete="off"` and `name="search"` to both the desktop and mobile search inputs.

---

### [MEDIUM] `TenantProvider` Injects Unsanitized `custom_css` via `textContent`

- **File:** `providers/TenantProvider.tsx:111-120`
- **Problem:** `style.textContent = config.custom_css` injects arbitrary CSS from the server. While `textContent` on a `<style>` element cannot inject JS, a compromised backend could inject CSS that overlays phishing UI or performs CSS-based data exfiltration (e.g., `input[value^="tok"]` background-image tricks).
- **Why it matters:** The threat vector requires a compromised admin or backend. Acceptable risk for a self-hosted CRM, but worth documenting.
- **Fix:** Document the trust boundary explicitly. Consider a CSP `style-src` nonce for injected styles if this surface grows.

---

### [LOW] `useNotifications` Polling Uses `staleTime: 10s, gcTime: 60s` With Additional `refetchInterval: 5min` — Inconsistent Config

- **File:** `hooks/useNotifications.ts:21-26` and `config/queryConfig.ts`
- **Problem:** `useNotifications` uses `CACHE_TIMES.REALTIME` (`staleTime: 10s`) but `useUnreadCount` sets an additional `refetchInterval: 5 * 60 * 1000` (5 minutes). The `REALTIME` cache time implies near-constant freshness but the explicit poll interval is 5 minutes — these intentions conflict. Notifications list will refetch on window focus every 10s after becoming stale, but the count only polls every 5 minutes.
- **Why it matters:** The unread count badge may be stale for up to 5 minutes while the list panel stays fresh. Minor UX inconsistency.
- **Fix:** Make `refetchInterval` consistent: either poll both at the same interval, or remove `CACHE_TIMES.REALTIME` from `useNotifications` and use a shared `refetchInterval`.

---

### [LOW] `NotificationBell` Registers Two `document` Event Listeners Without Combining Them

- **File:** `components/notifications/NotificationBell.tsx:65-84`
- **Problem:** Two separate `useEffect` blocks register `mousedown` and `keydown` listeners on `document`. CLAUDE.md: "Deduplicate global event listeners — N component instances should share 1 listener." Currently N=1 (singleton component), so no real problem, but the pattern could multiply.
- **Why it matters:** Informational — no current impact.
- **Fix:** Merge into a single `useEffect` registering both listeners. Low priority.

---

### [LOW] `Sidebar` Edit Mode Customization Not Persisted Across Sessions

- **File:** `components/layout/Sidebar.tsx:197-205`
- **Problem:** The drag-reorder persists nav item order to localStorage correctly. But `editMode` state is local (`useState(false)`). If the user is mid-edit and navigates away, edit mode is lost. This is minor UX.
- **Why it matters:** Very low impact; the user simply needs to re-enter edit mode.
- **Fix:** Not strictly necessary — acceptable as-is given the transient nature of edit mode.

---

## Top 5 Fixes Ranked

1. **[CRITICAL] Remove double `aria-live` wrapper around `<Toaster>`** (`App.tsx:88`) — Screen readers double-announce every toast today. Delete the wrapping div (one-line fix).

2. **[CRITICAL] Delete duplicate `theme` state from `uiStore`** (`store/uiStore.ts:37`) — Two out-of-sync theme sources; `uiStore.theme` is always `'system'` regardless of actual selection. Types are misaligned between the two.

3. **[CRITICAL] Add `<meta name="color-scheme" content="light dark">` to `index.html`** — Native browser controls (scrollbars, selects, date pickers) render light even in dark mode until JS executes.

4. **[HIGH] Fix broken `/profile` route** (`Header.tsx:143`) — Every logged-in user who clicks "Your Profile" silently lands on the dashboard. Either add a profile page or point the link to `/settings`.

5. **[HIGH] Fix `usePageTitle` to use tenant company name** (`hooks/usePageTitle.ts:5`) — White-label tenants see "CRM App" overwrite their branded document title on every page mount.
