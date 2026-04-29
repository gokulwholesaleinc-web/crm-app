# Campaigns + Sequences + Activities + Calendar Audit

## Summary

Audited 7 campaign files (~2,105 LoC), 2 sequence files (~752 LoC), 7 activity files (~2,328 LoC), 1 calendar page file (~129 LoC), and 2 email component files. The surfaces are largely well-structured with good a11y in most areas. The top issues are: a custom roll-your-own modal in AddMembersModal that bypasses the shared `<Modal>` (no focus trap, no dark-mode overlay, no ARIA roles), a `window.confirm()` for sequence delete (blocks the main thread, unstyled, inconsistent), DOMPurify's blocklist approach that allows `on*` inline event handlers to pass through HTML email bodies (XSS), member IDs displayed as raw integers in the campaign member table with no name lookup, and `toLocaleTimeString`/`toLocaleDateString`/`date-fns format` calls in calendar views that violate the `Intl.DateTimeFormat` requirement from CLAUDE.md.

NOTE: `EmailThread.tsx` was observed to have already been partially patched by a concurrent process (the `FORBID_ATTR` list was narrowed to only 3 on* handlers). The DOMPurify finding below reflects the state at time of audit — the broader allowlist approach is still recommended.

**Severity counts:** CRITICAL: 1 | HIGH: 4 | MEDIUM: 5 | LOW: 4

---

## Findings

### [CRITICAL] DOMPurify config does not block all inline event handlers in EmailThread

- **File:** `frontend/src/components/email/EmailThread.tsx:179–183` (patched narrowly to `onclick`, `onload`, `onerror` — incomplete)
- **Problem:** The sanitizer uses a blocklist for event attributes. The current patch only blocks 3 of the ~30 possible `on*` attributes (`onerror`, `onload`, `onclick`). Attributes like `onmouseover`, `onfocus`, `onblur`, `oninput`, `onsubmit`, `onreset`, `onchange`, `ondblclick`, `onkeydown`, `onkeyup`, `onkeypress`, etc. are still allowed through. A malicious inbound HTML email can trigger scripts on hover, key press, or focus.
- **Why it matters:** Partial XSS. An attacker who sends a crafted email to any address monitored by the CRM can execute JavaScript in the logged-in user's session via unblocked event handlers.
- **Fix:** Switch from a blocklist to an allowlist approach using DOMPurify's `ALLOWED_ATTR` option: `{ ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'class', 'target', 'rel', 'width', 'height'], FORBID_TAGS: ['form', 'script', 'style'] }`. This is fundamentally safer than trying to enumerate every event attribute to block.

---

### [HIGH] AddMembersModal is a custom inset-0 roll bypassing the shared Modal

- **File:** `frontend/src/features/campaigns/components/AddMembersModal.tsx:93–261`
- **Problem:** The modal uses `fixed inset-0 z-50` with a hand-rolled backdrop div and custom close-on-overlay-click, while every other modal in the codebase uses the shared `<Modal>` component. Issues: (1) the overlay has no dark-mode class — `bg-black bg-opacity-25` only; (2) no focus trap, Tab cycles into background content; (3) the panel has no `aria-modal="true"` or `role="dialog"`; (4) on mobile the panel fills full viewport height at intermediate breakpoints.
- **Why it matters:** Missing focus trap is a WCAG 2.1 SC 2.1.2 failure. Screen reader and keyboard users can navigate to background page content behind the open modal.
- **Fix:** Replace the custom implementation with the shared `<Modal>` component (size="xl"), which handles focus trapping, ARIA roles, dark-mode backdrop, and close-on-backdrop-click.

---

### [HIGH] Sequence delete uses `window.confirm()` — inconsistent and inaccessible

- **File:** `frontend/src/features/sequences/SequencesPage.tsx:390–393`
- **Problem:** `window.confirm('Delete this sequence?')` is used directly. Every other destructive action in the codebase (campaign delete, activity delete, member remove) uses `<ConfirmDialog>`. The `window.confirm` dialog: blocks the UI thread, cannot be styled to dark/light theme, and returns focus poorly on dismiss.
- **Why it matters:** Inconsistent UX and accessibility failure on some mobile browsers that suppress confirm dialogs entirely, making delete impossible to trigger.
- **Fix:** Replace with a `useState`-managed `<ConfirmDialog isOpen={...} onConfirm={...} variant="danger" />` matching the pattern in `CampaignsPage` and `ActivitiesPage`.

---

### [HIGH] Campaign member table shows raw IDs, not member names

- **File:** `frontend/src/features/campaigns/CampaignDetailPage.tsx:88–89, 131–133`
- **Problem:** Both `MemberRow` and `MemberCard` render members as `Contact #42` / `Lead #7` — raw database IDs. The `CampaignMember` type does not include resolved name data, and no lookup is performed. "Add Members" modal correctly shows names via `useContacts`/`useLeads`, but once added the detail page loses all identifying information.
- **Why it matters:** Users cannot identify which people are in the campaign. Makes targeted member removal error-prone.
- **Fix:** Either extend the `CampaignMember` backend response to include `full_name` and `email`, or perform a client-side join using the already-imported `useContacts`/`useLeads` hooks keyed via `useMemo(() => new Map(contacts.map(c => [c.id, c])))`.

---

### [HIGH] `toLocaleTimeString` / `toLocaleDateString` / `date-fns format` with hardcoded patterns (CLAUDE.md violation)

- **File:** `frontend/src/features/activities/components/calendar-views/WeekView.tsx:55`, `frontend/src/features/activities/components/calendar-views/DayView.tsx:45`, `frontend/src/features/activities/components/calendar-views/AgendaView.tsx:61–62`, `frontend/src/features/activities/components/ActivityTimeline.tsx:53`
- **Problem:** Multiple calendar-view files call `new Date(...).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })` and `new Date(...).toLocaleDateString(undefined, {...})` directly instead of `Intl.DateTimeFormat`. `ActivityTimeline.tsx:53` uses `date-fns format(date, 'h:mm a')` — a hardcoded 12-hour AM/PM format string. CLAUDE.md explicitly mandates `Intl.DateTimeFormat` for all time/date formatting.
- **Why it matters:** `date-fns format('h:mm a')` always outputs 12-hour regardless of locale. CLAUDE.md rule is violated in 4 files.
- **Fix:** Replace with `new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(date)` throughout. For `ActivityTimeline.tsx:53`, replace `format(new Date(dateString), 'h:mm a')` with `new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(new Date(dateString))`.

---

### [MEDIUM] EnrollModal requires users to type a raw contact ID — no search/picker

- **File:** `frontend/src/features/sequences/SequencesPage.tsx:198–246`
- **Problem:** The "Enroll Contact" inline form has a plain `<input type="number">` for Contact ID. Users must know the internal database ID. No name search, no autocomplete, and no validation message on invalid IDs — the form silently does nothing if `isNaN(id)`.
- **Why it matters:** Completely unusable in production without separate contact ID lookup. This is a major UX gap in the sequences feature.
- **Fix:** Replace the ID input with a contact search select reusing `useContacts` with search, matching the `AddMembersModal` pattern.

---

### [MEDIUM] CampaignStepBuilder sequential move awaits with no error handling

- **File:** `frontend/src/features/campaigns/components/CampaignStepBuilder.tsx:52–53, 60–61`
- **Problem:** `handleMoveUp` and `handleMoveDown` fire two sequential `await onUpdateStep(...)` calls. If the first succeeds and the second fails, the step list ends up in an inconsistent state. No try/catch, no error toast.
- **Why it matters:** Network error on the second swap leaves UI and backend in different orders, silently corrupting the campaign sequence.
- **Fix:** Wrap both calls in a single try/catch and call `showError()` on failure. Ideally the backend exposes an atomic reorder endpoint.

---

### [MEDIUM] ActivityDetailModal uses `toLocaleString()` with no options

- **File:** `frontend/src/features/activities/components/calendar-views/ActivityDetailModal.tsx:48`
- **Problem:** `new Date(activity.scheduled_at).toLocaleString()` called with no arguments produces locale-dependent output that varies by browser and platform. CLAUDE.md requires explicit `Intl.DateTimeFormat` options.
- **Why it matters:** Inconsistent date/time display across browsers. Could show seconds on some platforms, omit time on others.
- **Fix:** Replace with `new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(activity.scheduled_at))`.

---

### [MEDIUM] Timeline view has no pagination — all items load unbounded

- **File:** `frontend/src/features/activities/ActivitiesPage.tsx:114–117`
- **Problem:** `useUserTimeline` is called without `page` or `page_size`. All returned items render at once with no virtualization or "Load more" button. Violates CLAUDE.md rule on large lists (>50 items) requiring virtualization or `content-visibility: auto`.
- **Why it matters:** Performance degradation for active users. No cap on items fetched from the API.
- **Fix:** Add `page`/`page_size` to the timeline endpoint call, and add a "Load more" button or `content-visibility: auto` on list items.

---

### [MEDIUM] AddMembersModal hardcaps at 100 contacts/leads — silently truncates

- **File:** `frontend/src/features/campaigns/components/AddMembersModal.tsx:35–42`
- **Problem:** `useContacts` and `useLeads` are called with `page_size: 100`. If a tenant has >100 contacts, remaining contacts are never shown or pageable. The count display (e.g., "Contacts (97)") misleads users into thinking that's the total.
- **Why it matters:** Campaign member additions will silently miss contacts not in the first 100 results.
- **Fix:** Add a "Load more" button or implement server-side search-first UX where results only appear after the user types, keeping the result set small without a hard cap.

---

### [LOW] SequenceForm has no `useUnsavedChangesWarning` guard

- **File:** `frontend/src/features/sequences/SequencesPage.tsx:56–130`
- **Problem:** `SequenceForm` uses local `useState` but does not call `useUnsavedChangesWarning`. Navigation away mid-edit shows no browser `beforeunload` prompt. Both `CampaignForm` and `ActivityForm` correctly call this hook.
- **Why it matters:** Minor UX inconsistency — sequences are the only form surface without unsaved-changes protection.
- **Fix:** Track dirty state (e.g., compare current values to `sequence` prop) and call `useUnsavedChangesWarning(isDirty)`.

---

### [LOW] EmailComposeModal TO field is `type="email"` — blocks multi-recipient input

- **File:** `frontend/src/components/email/EmailComposeModal.tsx:131`
- **Problem:** The `to` field uses `<input type="email">` which accepts only a single valid email address. CC and BCC are `type="text"`. If a user types multiple TO addresses (comma-separated), browser validation rejects the form. Placeholder does not indicate whether multiple recipients are supported.
- **Why it matters:** Users expecting to send to multiple TO recipients are silently blocked by HTML5 validation.
- **Fix:** Change TO field to `type="text"` and add client-side multi-email validation, matching CC/BCC behavior.

---

### [LOW] Calendar nav button aria-labels lack view-mode context

- **File:** `frontend/src/features/activities/components/CalendarView.tsx:133–149`
- **Problem:** Navigation buttons have static `aria-label="Previous"` / `aria-label="Next"` regardless of the current view mode (year/month/week/day). Screen reader users hear the same label whether navigating by day or year.
- **Why it matters:** Minor a11y issue for screen reader users.
- **Fix:** Use dynamic labels: `` aria-label={`Previous ${viewMode}`} `` / `` aria-label={`Next ${viewMode}`} ``.

---

### [LOW] VolumeStats has no error boundary and is not audited

- **File:** `frontend/src/features/campaigns/components/VolumeStats.tsx`
- **Problem:** `VolumeStats` is rendered in `CampaignsPage` without a Suspense boundary. If the component's data hook has an unhandled error state, the entire campaigns page could unmount.
- **Why it matters:** Low risk, but worth verifying the component has its own error handling.
- **Fix:** Verify `VolumeStats` has loading/error states and wrap with `ErrorBoundary` if it can throw.

---

## Top 5 Fixes Ranked

1. **[CRITICAL] DOMPurify allowlist for `on*` attributes in EmailThread** (`EmailThread.tsx:179`) — Switch from `FORBID_ATTR` blocklist to `ALLOWED_ATTR` allowlist to close the XSS vector from inbound HTML emails.

2. **[HIGH] AddMembersModal bypasses shared Modal — no focus trap or ARIA** (`AddMembersModal.tsx:93`) — Replace with `<Modal>` to fix WCAG 2.1.2 failure and dark-mode overlay gap.

3. **[HIGH] Sequence delete uses `window.confirm()`** (`SequencesPage.tsx:390`) — Replace with `<ConfirmDialog>` for consistency and accessibility.

4. **[HIGH] Campaign member table shows raw IDs instead of names** (`CampaignDetailPage.tsx:88`) — Members are unidentifiable after adding; join name data from contacts/leads API.

5. **[HIGH] Hardcoded time formats in calendar views violate CLAUDE.md** (`WeekView.tsx:55`, `DayView.tsx:45`, `AgendaView.tsx:61`, `ActivityTimeline.tsx:53`) — Replace `toLocaleTimeString` and `date-fns format` patterns with `Intl.DateTimeFormat`.
