# UI Primitives Audit

## Summary

The primitive layer is largely solid — React 19 ref-as-prop is used correctly everywhere (no `forwardRef`), accessible ID derivation is consistent across `Input`/`Select`/`FormInput`/`FormSelect`, and `Modal` correctly delegates focus trap + scroll lock to Headless UI. The main failure modes are: (1) `Input`, `FormInput`, `FormTextarea`, and `DateRangePicker` mix `focus:ring-*` and `focus-visible:ring-*` in the same rule, diverging from `Button`/`Select`; (2) `ConfirmDialog` never enforces focus on cancel for the destructive variant, and its mobile layout inverts DOM order making confirm focus first; (3) `Spinner` and `Skeleton` have `aria-hidden` but no `aria-busy`/`aria-live` contract for loading containers; (4) `SelectOption` is a duplicate export from both `ui/index.ts` and `forms/index.ts`; (5) ~12 raw `<input>`/`<select>` elements in `ContractsList`, `BillingTermsField`, and `SharePanel` bypass the primitive layer, losing error a11y, focus styles, and mobile touch sizing.

---

## API Consistency Table

| Component | open prop | close prop | onChange convention | ref handling | a11y completeness |
|---|---|---|---|---|---|
| Modal | `isOpen: boolean` | `onClose: () => void` | n/a | prop `ref` (React 19) | Good — Headless UI Dialog handles focus trap, Esc, scroll lock; Dialog.Title provides aria-labelledby |
| ConfirmDialog | `isOpen: boolean` (via Modal) | `onClose: () => void` | n/a | none needed | Partial — no autoFocus on cancel for destructive variant; mobile DOM order inversion |
| Input | n/a | n/a | native onChange via spread | prop `ref` | Partial — aria-invalid, aria-describedby, id↔label OK; focus:ring vs focus-visible:ring mismatch |
| Select (ui) | n/a | n/a | native onChange via spread | prop `ref` | Good — matches Input pattern; uses focus-visible consistently |
| FormInput | n/a | n/a | native onChange + register spread | prop `ref` | Partial — same focus:ring issue as Input |
| FormSelect | n/a | n/a | native onChange + register spread | prop `ref` | Good — uses focus consistently with FormInput |
| FormTextarea | n/a | n/a | native onChange + register spread | prop `ref` | Partial — missing dark: on label and helperText; same focus:ring issue |
| SearchableSelect | n/a | n/a | `onChange: (value: number | null) => void` | none (Combobox internal) | Partial — error paragraph missing id/role="alert"; no aria-describedby link |
| Table | n/a | n/a | `onSort: (column: string) => void` | none needed | Partial — scope="col" on th; no caption; sortable th missing aria-sort; no keyboard handler |
| PaginationBar | n/a | n/a | `onPageChange: (page: number) => void` | none needed | Good — aria-label on nav, aria-current="page" on active page |
| DateRangePicker | n/a | n/a | `onChange: (range, preset) => void` | none needed | Partial — role="group" + aria-label good; date inputs have sr-only labels; focus:ring mismatch |
| Avatar | n/a | n/a | n/a | none needed | Partial — fallback div has aria-label but not role="img" |
| Badge / StatusBadge | n/a | n/a | n/a | none needed | Acceptable — decorative; dot has aria-hidden |
| EmptyState | n/a | n/a | action onClick | none needed | Missing aria-live — no announcement when async empty states resolve |
| Skeleton | n/a | n/a | n/a | none needed | aria-hidden on each item; no aria-busy on loading container |
| Spinner | n/a | n/a | n/a | none needed | aria-hidden correct for inline use; no role="status" for standalone use |
| DuplicateWarningModal | `isOpen` | `onClose` | — | none needed | Missing aria-describedby linking modal title to body text |
| EmailComposeModal | `isOpen` | `onClose` | — | none needed | Good — all inputs labeled; spellCheck={false} on email fields |
| BillingTermsField | n/a | n/a | `onChange: (next) => void` | none needed | Good — fieldset+legend, useId; cadence/amount selects missing focus-visible and aria-invalid |

---

## Findings

### [HIGH] Input, FormInput, FormTextarea, DateRangePicker mix `focus:ring` with `focus-visible:outline-none`

- **File:** `frontend/src/components/ui/Input.tsx:42-43`, `frontend/src/components/forms/FormInput.tsx:51`, `frontend/src/components/forms/FormTextarea.tsx:53`, `frontend/src/components/ui/DateRangePicker.tsx:112,122`
- **Problem:** All four components use `'focus-visible:outline-none focus:ring-2 focus:ring-offset-0'`. The outline suppresser is scoped to `focus-visible` but the ring applier is plain `focus`, so the blue ring appears on mouse click. `Button` and `Select` correctly use `focus-visible:ring-2` throughout.
- **Why it matters:** Mouse users see a flash ring on every click in Input but not in adjacent Button/Select elements. Inconsistency across primitives is a visual regression risk whenever field types are mixed in a form.
- **Fix:** Change `focus:ring-2` → `focus-visible:ring-2` and `focus:border-*` → `focus-visible:border-*` in all four files.

---

### [HIGH] ConfirmDialog: no enforced cancel focus; mobile DOM order makes confirm focus first

- **File:** `frontend/src/components/ui/ConfirmDialog.tsx:76-98`
- **Problem:** No `autoFocus` on the cancel button. The button block uses `flex-col-reverse sm:flex-row sm:justify-end`, which reverses DOM order on mobile — the confirm button is last in DOM order on desktop but first on mobile. Headless UI Dialog focuses the first focusable element, so mobile users pressing Enter immediately will trigger the destructive action.
- **Why it matters:** Destructive dialogs must default focus to the safe (cancel) path per WCAG 3.2.2 and general UX convention. The layout inversion also means DOM order and visual order differ, violating WCAG 1.3.2.
- **Fix:** Add `autoFocus` to the cancel `<Button>`. Normalise button DOM order to always be `[cancel, confirm]`; use `flex-row-reverse` on desktop only so DOM order stays [cancel, confirm] everywhere.

---

### [HIGH] Spinner and Skeleton have no `aria-busy`/`aria-live` contract — screen readers get no loading signal

- **File:** `frontend/src/components/ui/Spinner.tsx:1-29`, `frontend/src/components/ui/Skeleton.tsx:1-15`
- **Problem:** Both components carry `aria-hidden="true"`, which is correct when they are decorative. However, every consumer (ActivitiesTab, SharePanel, ContractsList, AttachmentList, etc.) renders a bare Spinner or Skeleton as the sole content of a loading region with no `aria-busy="true"` on the container and no `aria-live="polite"` region to announce completion.
- **Why it matters:** Screen reader users receive zero feedback that content is loading or has finished. Violates WCAG 4.1.3 (Status Messages).
- **Fix:** Add a `LoadingRegion` wrapper or document the canonical pattern: the loading container must carry `aria-busy={isLoading}` and a sibling `aria-live="polite"` region. Alternatively expose a `label` prop on Spinner that renders a `sr-only` `role="status"` element for standalone use.

---

### [HIGH] `SelectOption` type exported from both `ui/index.ts` and `forms/index.ts` — name collision

- **File:** `frontend/src/components/ui/index.ts:11`, `frontend/src/components/forms/index.ts:5`
- **Problem:** Both barrel files export a type named `SelectOption`. Any consumer that imports from both barrels in the same file gets a name conflict; any file that imports from the wrong barrel silently gets a structurally-identical-but-distinct type.
- **Why it matters:** Silent structural match masks an import-source bug. If either type diverges, callers get a type error deep in a form. Knip/dead-code tools also cannot detect the duplication.
- **Fix:** Keep `SelectOption` only in `ui/Select.tsx`. Change `FormSelect.tsx` to `import type { SelectOption } from '../ui/Select'` and remove its own declaration. Re-export from `forms/index.ts` as `export type { SelectOption } from '../ui/Select'`.

---

### [MEDIUM] Raw `<input>`/`<select>` elements in ContractsList, BillingTermsField, and SharePanel bypass primitive layer

- **File:** `frontend/src/components/shared/ContractsList.tsx:117-143`, `frontend/src/components/forms/BillingTermsField.tsx:167-226`, `frontend/src/components/shared/SharePanel.tsx:75-100`
- **Problem:** ~12 raw elements with hard-coded Tailwind focus/border classes that partially diverge from primitives: missing `focus-visible`, missing `dark:disabled:*`, no `aria-invalid`, no `aria-describedby`, and `py-2.5 sm:py-2` mobile touch sizing absent. The `type="number"` input in ContractsList has no `inputMode="decimal"`.
- **Why it matters:** Style changes to the primitive focus ring or disabled state will not propagate here. Field-level errors cannot be announced to screen readers. Mobile touch targets are smaller than the 44px WCAG 2.5.5 minimum on some inputs.
- **Fix:** Replace raw elements with `<Input>`, `<Select>`, `<FormInput>`, `<FormSelect>` from the primitive layer.

---

### [MEDIUM] Table sortable `<th>` missing `aria-sort` and keyboard activation

- **File:** `frontend/src/components/ui/Table.tsx:61-81`
- **Problem:** Sortable `th` elements have `onClick` but no `aria-sort` attribute and no `onKeyDown` handler. The `th` is not a `<button>`, so keyboard users cannot activate sort with Enter/Space.
- **Why it matters:** Screen readers cannot announce sort state (WCAG 1.3.1). Keyboard-only users cannot sort columns (WCAG 2.1.1).
- **Fix:** Add `aria-sort={isActive ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}` to sortable `th`. Add `tabIndex={0}` and `onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onSort?.(column.key); }}`, or wrap the header text in a `<button>` inside the `th`.

---

### [MEDIUM] Modal passes inline `() => {}` NOOP — breaks memoization

- **File:** `frontend/src/components/ui/Modal.tsx:48`
- **Problem:** `onClose={closeOnOverlayClick ? onClose : () => {}}` creates a new function object on every render.
- **Why it matters:** Per CLAUDE.md — inline non-primitive defaults break memoization. If Dialog or any wrapper ever uses referential equality on the close handler, this will cause unnecessary re-renders.
- **Fix:** Hoist to module scope: `const NOOP = () => {};` and use `onClose={closeOnOverlayClick ? onClose : NOOP}`.

---

### [MEDIUM] `SearchableSelect` error paragraph missing `id` and `role="alert"` — aria-describedby cannot reference it

- **File:** `frontend/src/components/ui/SearchableSelect.tsx:131-133`
- **Problem:** The error `<p>` has no `id`. Unlike every other form primitive (`Input`, `Select`, `FormInput`, `FormSelect`) which generate `${id}-error` and wire `aria-describedby`, `SearchableSelect` renders a plain `<p>` with no linkage.
- **Why it matters:** Screen readers will not announce the error when focus is on the combobox input. Breaks the a11y contract every other form primitive provides.
- **Fix:** Add `id={comboboxId ? \`${comboboxId}-error\` : undefined}` and `role="alert"` to the error `<p>`. Add `aria-describedby={error && comboboxId ? \`${comboboxId}-error\` : undefined}` to `Combobox.Input`.

---

### [MEDIUM] `Avatar` fallback `<div>` has `aria-label` but no `role="img"`

- **File:** `frontend/src/components/ui/Avatar.tsx:93-101`
- **Problem:** `aria-label` on a `<div>` without an explicit role has no semantic effect — screen readers will not announce it.
- **Why it matters:** User avatars in lists (AuditTimeline, shared-with lists) are invisible to screen readers.
- **Fix:** Add `role="img"` to the fallback `<div>`.

---

### [LOW] `FormTextarea` label and helperText missing dark-mode text classes

- **File:** `frontend/src/components/forms/FormTextarea.tsx:47,72`
- **Problem:** Label uses `text-gray-700` without `dark:text-gray-300`. HelperText uses `text-gray-500` without `dark:text-gray-400`. `FormInput` and `FormSelect` include both.
- **Why it matters:** On dark theme, textarea labels and helper text render near-invisible.
- **Fix:** Add `dark:text-gray-300` to the label class, `dark:text-gray-400` to the helper text class.

---

### [LOW] `ConfirmDialog.handleConfirm` is a pointless passthrough wrapper

- **File:** `frontend/src/components/ui/ConfirmDialog.tsx:49-51`
- **Problem:** `const handleConfirm = () => { onConfirm(); };` adds no logic. If `onConfirm` is memoized by the caller, this extra closure breaks the reference chain.
- **Fix:** Replace `onClick={handleConfirm}` with `onClick={onConfirm}` and remove the wrapper.

---

### [LOW] `AttachmentList` and `DocumentsTab` duplicate `formatDate` and `handleDownload` logic verbatim

- **File:** `frontend/src/components/shared/AttachmentList.tsx:37-42,92-108`, `frontend/src/components/shared/DocumentsTab.tsx:41-46,85-102`
- **Problem:** Identical `formatDate` helpers and identical `handleDownload` functions (fetch → blob → link-click) copied between both files.
- **Why it matters:** Auth token changes or bug fixes must be applied in two places.
- **Fix:** Extract to `frontend/src/utils/attachmentUtils.ts` (or a shared `useDownloadAttachment` hook) and import in both.

---

### [LOW] No `prefers-reduced-motion` guard on Modal/ConfirmDialog transitions

- **File:** `frontend/src/components/ui/Modal.tsx:55-82`
- **Problem:** Scale + fade animations use bare `duration-300`/`duration-200` classes with no `motion-safe:` guard.
- **Why it matters:** Users with vestibular disorders who set `prefers-reduced-motion: reduce` still see animations.
- **Fix:** Wrap animation classes with `motion-safe:` Tailwind variants, or add `motion-reduce:transition-none` overrides.

---

## Top 5 Fixes Ranked

1. **[HIGH] `focus:ring` → `focus-visible:ring` in Input, FormInput, FormTextarea, DateRangePicker** — One-line fix per file; eliminates mouse-click ring flash that diverges from Button/Select across every form in the app.

2. **[HIGH] `SelectOption` name collision — consolidate to single declaration in `ui/Select.tsx`** — Silent type duplication; becomes a runtime import bug the moment either type diverges.

3. **[HIGH] ConfirmDialog: add `autoFocus` to cancel, fix mobile DOM order inversion** — Destructive dialogs currently focus confirm first on mobile; data-destructive UX risk.

4. **[HIGH] Add `aria-busy`/`aria-live` contract for Spinner/Skeleton loading containers** — Zero screen reader feedback on async tab content across the entire app.

5. **[MEDIUM] Replace raw `<input>`/`<select>` in ContractsList, BillingTermsField, SharePanel with primitives** — ~12 elements bypassing error a11y, focus styles, and mobile touch sizing.
