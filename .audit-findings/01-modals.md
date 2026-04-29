# Modal/Dialog System Audit

## Summary

The shared `Modal` primitive (`components/ui/Modal.tsx`) is well-built: it delegates to Headless UI `Dialog` (v1.7), which provides Esc-to-close, focus trap, focus restore, and body scroll lock automatically. `ConfirmDialog` correctly wraps `Modal` and inherits all of those behaviors. The four custom `fixed inset-0` rolls bypass Headless UI entirely, meaning none of them get a focus trap, body scroll lock, Esc-to-close, or focus restore for free — and three of the four also lack `role="dialog"` / `aria-modal`. The most severe user-visible bugs are: (1) body scrolls freely behind three of the four custom modals, (2) keyboard users cannot be trapped inside any of the custom modals and can tab into the background page, and (3) `PublicQuoteView`'s "Reject" button silently fails if the user has never opened the e-sign modal because the error is only displayed inside a modal that is not open.

---

## Findings

### [CRITICAL] Custom modals have no focus trap — keyboard users can tab into background

- **File:** `frontend/src/features/admin/UserManagement.tsx:300`, `frontend/src/features/admin/UserManagement.tsx:415`, `frontend/src/features/dashboard/DashboardPage.tsx:138`, `frontend/src/features/campaigns/components/AddMembersModal.tsx:93`
- **Problem:** All four custom `fixed inset-0` modals are plain `<div>` elements. There is no `FocusTrap`, no Headless UI `Dialog`, and no `tabindex` management. Tab key cycles through the entire document, including interactive elements behind the backdrop.
- **Why it matters:** Screen reader and keyboard users can tab out of the modal into the obscured page and interact with elements they cannot see. This is a WCAG 2.1 Level A failure (SC 1.3.1, 4.1.2).
- **Fix:** Replace each custom roll with `<Modal>` (or at minimum wrap the inner panel in a Headless UI `Dialog`). If keeping custom, add a focus-trap library (e.g., `focus-trap-react`) and `tabindex="-1"` on the panel.

---

### [CRITICAL] Body scroll not locked behind three custom modals

- **File:** `frontend/src/features/admin/UserManagement.tsx:300`, `frontend/src/features/admin/UserManagement.tsx:415`, `frontend/src/features/dashboard/DashboardPage.tsx:138`
- **Problem:** These three custom modals render as in-tree `<div>` elements with no portal and no body scroll lock. Headless UI locks body scroll only when the `Dialog` component is rendered; plain divs do not. The `Modal` primitive uses Headless UI `Dialog` on line 45 and therefore locks scroll correctly. Only `AddMembersModal` partially avoids this because its outer `fixed inset-0 overflow-y-auto` container absorbs some scroll, but the underlying body is still scrollable.
- **Why it matters:** The page scrolls while the modal is open. Users can scroll the background content, which is disorienting and causes layout thrashing behind the overlay.
- **Fix:** Use `<Modal>` (which delegates to Headless UI `Dialog`), or manually add/remove `document.body.style.overflow = 'hidden'` in a `useEffect` cleanup pair on mount/unmount.

---

### [CRITICAL] Reject quote button silently swallows error when e-sign modal is closed

- **File:** `frontend/src/features/quotes/PublicQuoteView.tsx:158-183`, `frontend/src/features/quotes/PublicQuoteView.tsx:570-572`
- **Problem:** `handleReject` reads `signerEmail` state (line 160), which is only populated by the e-sign modal input (line 610). If the user clicks "Reject" without first opening the e-sign modal, `signerEmail` is empty, so `setEsignError(...)` is called (line 164) — but `esignError` is only rendered inside `{showEsignModal && ...}` (line 570). The error is set but invisible; the user sees nothing and the reject action is silently dropped.
- **Why it matters:** Customers clicking "Reject" for the first time get no feedback and believe the action failed or was ignored. They have no way to recover without trial-and-error.
- **Fix:** Either open the e-sign modal on Reject (with a "reject" mode flag), or add a separate visible email input in the "Your Response" section so the error can be displayed adjacent to it.

---

### [HIGH] ConfirmDialog title has no `aria-labelledby` connection to Dialog

- **File:** `frontend/src/components/ui/ConfirmDialog.tsx:54-72`
- **Problem:** `ConfirmDialog` wraps `<Modal>` but does not pass the `title` prop. Instead it renders its own `<h3>` (line 71). `Modal` only renders `<Dialog.Title>` when `title` is provided (Modal.tsx line 89). Without `Dialog.Title`, Headless UI's `Dialog` has no auto-generated `aria-labelledby` pointing at the heading. Screen readers announce the dialog without a name.
- **Why it matters:** Screen reader users hear "dialog" with no label when a confirmation prompt opens — they have no context about what they are being asked to confirm.
- **Fix:** Pass `title={title}` to `<Modal>` in `ConfirmDialog` and remove the custom `<h3>`. This lets Headless UI wire `aria-labelledby` automatically via `Dialog.Title`.

---

### [HIGH] `AddMembersModal` has no `role="dialog"`, `aria-modal`, or accessible name

- **File:** `frontend/src/features/campaigns/components/AddMembersModal.tsx:93-101`
- **Problem:** The outermost `<div className="fixed inset-0 z-50 overflow-y-auto">` has no `role`, no `aria-modal`, and no `aria-labelledby`. The visible `<h2>` on line 102 ("Add Campaign Members") has no `id`. Compare with the `AddWidgetModal` in `DashboardPage.tsx` which at least adds `role="dialog"` and `aria-modal="true"` (line 140-141).
- **Why it matters:** Screen readers treat the modal as a region of the page rather than a dialog. There is no announcement that a dialog has opened, and no accessible name.
- **Fix:** Add `role="dialog" aria-modal="true" aria-labelledby="add-members-title"` to the outer container. Add `id="add-members-title"` to the `<h2>` on line 102.

---

### [HIGH] `UserManagement` Edit and Delete modals have no `role="dialog"`, `aria-modal`, or accessible name

- **File:** `frontend/src/features/admin/UserManagement.tsx:299-304`, `frontend/src/features/admin/UserManagement.tsx:413-418`
- **Problem:** Both custom modals are plain `<div>` elements. Neither has `role="dialog"`, `aria-modal`, `aria-labelledby`, or any programmatic label. The `<h3>` headings ("Edit User" line 307, "Delete User" line 427) have no `id` for referencing. This contrasts with the `AddWidgetModal` (DashboardPage.tsx:140) which has `role="dialog"` and `aria-modal`.
- **Why it matters:** Screen reader users cannot determine a dialog has opened. Announcement of a modal context is missing entirely.
- **Fix:** Add `role="dialog" aria-modal="true" aria-labelledby="edit-user-title"` (and `id="edit-user-title"` to the h3) for the Edit modal, and equivalently for the Delete modal.

---

### [HIGH] No Esc-to-close on any of the four custom modals

- **File:** `frontend/src/features/admin/UserManagement.tsx:300`, `frontend/src/features/admin/UserManagement.tsx:415`, `frontend/src/features/dashboard/DashboardPage.tsx:138`, `frontend/src/features/campaigns/components/AddMembersModal.tsx:93`
- **Problem:** None of the four custom modals attach a `keydown` handler listening for `Escape`. Headless UI `Dialog` (used by `Modal`) provides this automatically. The shared `Modal` primitive closes on Esc; these four do not.
- **Why it matters:** The expected keyboard interaction for any dialog (ARIA Authoring Practices) is that Esc closes it. Users who habitually press Esc to dismiss modals find it does nothing.
- **Fix:** Add `onKeyDown={(e) => e.key === 'Escape' && onClose()}` to the outermost element of each custom modal. Better: replace with `<Modal>` which inherits this from Headless UI.

---

### [MEDIUM] `AddMembersModal` has two nested `fixed inset-0` divs causing double scroll context

- **File:** `frontend/src/features/campaigns/components/AddMembersModal.tsx:93`, `frontend/src/features/campaigns/components/AddMembersModal.tsx:96`
- **Problem:** The outer div is `fixed inset-0 z-50 overflow-y-auto` and the inner overlay is also `fixed inset-0 bg-black bg-opacity-25`. The outer creates a scroll container that is also fixed full-screen; the inner creates a second fixed-positioned overlay on top. This is redundant and can produce double scrollbars on some viewports.
- **Why it matters:** On iOS Safari and certain Android browsers, `overflow-y-auto` on a `fixed` container is unreliable. The overlay and content div compete, potentially causing content to be clipped or producing a double scrollbar.
- **Fix:** Remove `overflow-y-auto` from the outer div. Keep only the inner content div scrollable (`flex-1 overflow-y-auto`). The pattern matches `Modal.tsx` lines 62-63 which uses `fixed inset-0 overflow-y-auto overscroll-contain` on the scroll container, not the overlay.

---

### [MEDIUM] No focus restore on close for custom modals

- **File:** `frontend/src/features/admin/UserManagement.tsx:300`, `frontend/src/features/admin/UserManagement.tsx:415`, `frontend/src/features/dashboard/DashboardPage.tsx:138`, `frontend/src/features/campaigns/components/AddMembersModal.tsx:93`
- **Problem:** Headless UI `Dialog` (used by `Modal`) automatically returns focus to the element that triggered the dialog when it closes. The four custom divs do not. No `ref` is captured before opening, and no `.focus()` call occurs on close.
- **Why it matters:** After dismissing a modal, keyboard users find their focus dropped to the top of the document rather than returned to the triggering button.
- **Fix:** Capture the triggering element in a `ref` before opening (`triggerRef.current = document.activeElement`), then call `triggerRef.current?.focus()` in the `onClose` handler.

---

### [MEDIUM] `DashboardPage` `AddWidgetModal` uses `aria-label` redundantly alongside an in-modal `<h3>`

- **File:** `frontend/src/features/dashboard/DashboardPage.tsx:142`, `frontend/src/features/dashboard/DashboardPage.tsx:146`
- **Problem:** The dialog outer div has `aria-label="Add report widget"` (line 142) while the panel contains `<h3>Add Report Widget</h3>` (line 146) with no `id`. When both `aria-label` and a visible heading are present, `aria-label` shadows the visible text, decoupling the announced name from the rendered heading.
- **Why it matters:** If the heading text changes, the announced label silently diverges from what is visible.
- **Fix:** Remove `aria-label` from the outer div. Add `id="add-widget-title"` to the `<h3>` and `aria-labelledby="add-widget-title"` to the `role="dialog"` div.

---

### [MEDIUM] `PublicQuoteView` e-sign modal has no Esc-to-close, no overlay-click-to-close, and no body scroll lock

- **File:** `frontend/src/features/quotes/PublicQuoteView.tsx:554-557`
- **Problem:** The e-sign modal has correct `role`, `aria-modal`, and `aria-labelledby` attributes. However, it has no overlay click handler and no `onKeyDown` for Escape. Body scroll is also not locked.
- **Why it matters:** The only external-facing modal in the app (customer-visible on public quote links) cannot be dismissed with keyboard or by clicking outside it.
- **Fix:** Add `onClick={(e) => { if (e.target === e.currentTarget) setShowEsignModal(false); }}` to the outer div. Add `onKeyDown={(e) => e.key === 'Escape' && setShowEsignModal(false)}`. Add `useEffect` to set/clear `document.body.style.overflow = 'hidden'` while `showEsignModal` is true.

---

### [MEDIUM] `ConfirmDialog` title `<h3>` is semantically disconnected from Headless UI Dialog

- **File:** `frontend/src/components/ui/ConfirmDialog.tsx:71`
- **Problem:** `ConfirmDialog` renders an `<h3>` directly in the modal body without using `Dialog.Title`. Headless UI queries for `Dialog.Title` internally to generate the `aria-labelledby` attribute on the dialog element. Because `ConfirmDialog` does not pass `title` to `<Modal>`, neither `Dialog.Title` nor `aria-labelledby` are emitted. The `<h3>` is visually present but not programmatically connected to the dialog element.
- **Why it matters:** Captures the specific component-level root cause for the HIGH finding above; the `<h3>` level is also questionable hierarchy inside what is already a dialog heading context.
- **Fix:** Pass `title={title}` to `<Modal>` and remove the manual `<h3>` in `ConfirmDialog`.

---

### [LOW] `overscroll-contain` missing on all four custom modals

- **File:** `frontend/src/features/admin/UserManagement.tsx:300`, `frontend/src/features/admin/UserManagement.tsx:415`, `frontend/src/features/dashboard/DashboardPage.tsx:138`, `frontend/src/features/campaigns/components/AddMembersModal.tsx:93`
- **Problem:** `Modal.tsx` applies `overscroll-contain` to the scroll container (line 62), preventing scroll chaining to the page when the modal content reaches the top or bottom. None of the four custom modals apply this.
- **Why it matters:** On mobile, scrolling past the end of modal content causes the page behind the overlay to scroll (rubber-band / scroll chaining). Disorienting on iOS and Android.
- **Fix:** Add `overscroll-contain` to the scrollable container inside each custom modal.

---

### [LOW] `AddMembersModal` overlay uses deprecated `bg-opacity-25` syntax and lighter opacity than other modals

- **File:** `frontend/src/features/campaigns/components/AddMembersModal.tsx:97`
- **Problem:** The overlay uses Tailwind v2 syntax `bg-black bg-opacity-25` while all other modals use the Tailwind v3 shorthand `bg-black/50` or `bg-black/25`. The opacity is also 25% vs 50% used by others, making the overlay visually lighter.
- **Why it matters:** Minor visual inconsistency; background content is less suppressed behind this modal.
- **Fix:** Change `bg-black bg-opacity-25` to `bg-black/50` to match other overlays.

---

### [LOW] `EmailComposeModal` submit button lacks explicit `disabled` prop during send

- **File:** `frontend/src/components/email/EmailComposeModal.tsx:228`
- **Problem:** The Submit button uses `isLoading={sendEmailMutation.isPending}` but has no explicit `disabled={sendEmailMutation.isPending}`. If the `Button` component does not internally disable on `isLoading`, rapid clicking can enqueue multiple send requests.
- **Why it matters:** Double submission risk; inconsistent with the pattern in `ConfirmDialog.tsx:97` which explicitly sets both `isLoading` and `disabled`.
- **Fix:** Add `disabled={sendEmailMutation.isPending}` explicitly to the Submit button.

---

## Top 5 Fixes Ranked

1. **Replace all four custom `fixed inset-0` modals with `<Modal>`** — one change fixes focus trap, Esc-to-close, body scroll lock, focus restore, ARIA semantics, and `overscroll-contain` simultaneously across `UserManagement` (Edit + Delete), `DashboardPage` (AddWidget), and `AddMembersModal`.

2. **Fix `ConfirmDialog`: pass `title` prop to `<Modal>` and remove the custom `<h3>`** — closes the `aria-labelledby` gap on the most widely used confirmation primitive across the entire app.

3. **Fix the silent Reject bug in `PublicQuoteView`** — the error from `handleReject` is unreachable when the e-sign modal is closed; customers are blocked with zero feedback.

4. **Add `role="dialog"`, `aria-modal="true"`, and `aria-labelledby` to `AddMembersModal`** — highest-traffic custom modal with zero screen reader semantics.

5. **Add Esc-to-close, overlay-click-to-close, and body scroll lock to `PublicQuoteView`'s e-sign modal** — the only external-facing (customer-visible) modal in the app; it already has correct ARIA attributes but is not keyboard-dismissible.
