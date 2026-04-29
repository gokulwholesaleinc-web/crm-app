# Contact/Company Forms Audit

## Summary

The Contact and Company forms share an intent but diverge significantly in implementation: ContactForm uses the `FormInput`/`FormTextarea` shared primitives while CompanyForm uses raw `Input`/`Select` UI components — two different component families with subtly different styling, focus ring tokens, and label-generation logic. The biggest headline issue is that ContactForm silently discards most of the fields it renders (address, salesCode, notes, zipCode, country) — they appear in the UI but are never sent to the API on create or update. Both forms lack `autocomplete` attributes on every field. Duplicate-warning dismissal destroys the entered data on both forms if the user clicks "View" to inspect the duplicate. The company form is presented as a scrolling flat list inside a modal sized `lg` (max-w-lg ≈ 512 px), which is extremely cramped for 20+ fields.

---

## Inconsistencies between Contact and Company forms

| Area | ContactForm | CompanyForm |
|---|---|---|
| **Component library used** | `FormInput`, `FormTextarea` (shared/forms) | Raw `Input`, `Select`, `FormTextarea` (ui/) |
| **Label generation** | Explicit `name` prop; id = name | id derived from label string via `.toLowerCase().replace(/\s+/g, '-')` — fragile |
| **Focus ring CSS** | `focus:ring-2 sm:focus:ring-1` (inconsistent) | `focus:ring-2` / `focus-visible:ring-2` (consistent) |
| **Required field marker** | First name, last name, email get `*` via `required` prop | Only company name required; no `*` shown on selects |
| **autocomplete attrs** | None | None |
| **spellCheck on email** | Missing | Present on email, LinkedIn, Twitter |
| **Placeholders** | Some fields have no placeholder (City, State, Country, ZIP) | All fields have placeholders |
| **Phone inputmode** | Missing | Missing |
| **Submit label** | Passed as prop from parent | Hard-coded inside CompanyForm |
| **Unsaved-changes guard** | Guards both `isDirty` AND `companyId` state | Guards only `isDirty` |
| **Fields rendered but not sent to API** | address, city, state, zipCode, country, salesCode, notes — all silently dropped | All fields sent correctly |
| **Edit pre-fill completeness** | Only 6 of 13 form fields mapped back | All persisted fields mapped |
| **Email validation** | Validated with pattern + error message | No validation, no error wired |
| **Dark-mode support** | FormInput has dark classes | CompanyForm section headers missing `dark:text-gray-300` |

---

## Findings

### [CRITICAL] ContactForm fields silently dropped on submit — data loss

- **File:** `frontend/src/features/contacts/ContactsPage.tsx:84-92` (create), `:97-104` (update), `frontend/src/features/contacts/ContactDetailPage.tsx:78-86`
- **Problem:** ContactForm renders address, city, state, zipCode, country, salesCode, and notes. All three submit paths only include `first_name`, `last_name`, `email`, `phone`, `job_title`, `company_id`. The remaining fields are thrown away silently.
- **Why it matters:** A user fills in a contact's address and hits Save. The UI closes successfully. The data is gone with no error or indication.
- **Fix:** Extend `createData` and `updateData` in all three submit paths to include `address_line1` (from `address`), `city`, `state`, `postal_code` (from `zipCode`), `country`, `sales_code` (from `salesCode`), and `description` (from `notes`).

---

### [CRITICAL] Edit pre-fill incomplete — saved address and notes never shown

- **File:** `frontend/src/features/contacts/ContactsPage.tsx:120-131`, `frontend/src/features/contacts/ContactDetailPage.tsx:89-98`
- **Problem:** Both `getInitialFormData()` implementations only map `firstName`, `lastName`, `email`, `phone`, `jobTitle`, `company_id`. Even if address data existed on the server, it would not appear in the edit form. Any save after editing blanks those fields.
- **Why it matters:** Compound with the save bug: every edit of an existing contact silently wipes address and notes unless the user re-types them.
- **Fix:** Add all `ContactBase` fields: `address: contact.address_line1 || ''`, `city`, `state`, `zipCode: contact.postal_code || ''`, `country`, `salesCode: contact.sales_code || ''`, `notes: contact.description || ''`. Extract into a shared `contactToFormData` utility called from both pages.

---

### [HIGH] Duplicate warning "View" destroys entered form data

- **File:** `frontend/src/features/contacts/ContactsPage.tsx:142-147`, `frontend/src/features/companies/CompaniesPage.tsx` (equivalent handler)
- **Problem:** When a duplicate is detected and the user clicks "View", `handleViewDuplicate` calls `setPendingFormData(null)` and `setShowForm(false)` before navigating. On Back the form is blank. The Cancel handler on the duplicate modal also clears `pendingFormData`.
- **Why it matters:** User fills a long form, gets a duplicate warning, inspects the duplicate, decides it's different, hits Back — must re-enter everything.
- **Fix:** Do not clear `pendingFormData` in `handleViewDuplicate`. Open the duplicate in a new tab (`window.open`) or preserve state and restore the form from `pendingFormData` when the user returns.

---

### [HIGH] No `autocomplete` attributes on any field in either form

- **File:** `frontend/src/features/contacts/components/ContactForm.tsx` (all FormInput calls), `frontend/src/features/companies/components/CompanyForm.tsx` (all Input calls)
- **Problem:** Zero `autocomplete` attributes across 25+ fields.
- **Why it matters:** CLAUDE.md Forms: "Inputs need `autocomplete` and meaningful `name` attributes." Breaks browser autofill, particularly on mobile.
- **Fix:** Add `autoComplete` at each call site — `autoComplete="given-name"` / `"family-name"`, `"email"`, `"tel"`, `"address-line1"`, `"postal-code"`, `"country"`, `"organization"`, `"url"` on the website field, etc. The shared components pass `...props` through so no primitive changes needed.

---

### [HIGH] `spellCheck={false}` missing on ContactForm email and salesCode

- **File:** `frontend/src/features/contacts/components/ContactForm.tsx:88-97` (email), `:125-128` (salesCode)
- **Problem:** ContactForm email and salesCode fields do not set `spellCheck={false}`. CompanyForm correctly sets it on email (line 230), LinkedIn (line 335), and Twitter (line 341).
- **Why it matters:** CLAUDE.md: "Disable spell-check on emails, codes, usernames (`spellCheck={false}`)."
- **Fix:** Add `spellCheck={false}` to the email and salesCode FormInput calls in ContactForm.

---

### [HIGH] Phone fields missing `inputMode="tel"` in both forms

- **File:** `frontend/src/features/contacts/components/ContactForm.tsx:98-101`, `frontend/src/features/companies/components/CompanyForm.tsx:247`
- **Problem:** Both phone fields set `type="tel"` but omit `inputMode`. On Android Chrome, `type="tel"` alone does not reliably trigger the numeric dial-pad keyboard; `inputMode="tel"` is needed.
- **Why it matters:** CLAUDE.md: "Use semantic `type` values … with matching `inputmode`."
- **Fix:** Add `inputMode="tel"` to both phone inputs.

---

### [HIGH] Company email field has no validation and no error displayed

- **File:** `frontend/src/features/companies/components/CompanyForm.tsx:225-232`
- **Problem:** `register('email')` has no validation rules and `errors.email?.message` is never passed to the `Input error` prop. A malformed email is silently accepted.
- **Why it matters:** ContactForm rejects bad emails; CompanyForm does not. This is the most visible inconsistency a user would encounter.
- **Fix:** Add `{ pattern: { value: /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i, message: 'Invalid email' } }` to the register call and wire `error={errors.email?.message}`.

---

### [HIGH] Annual revenue and employee count use `type="number"` without `inputMode` or `min`

- **File:** `frontend/src/features/companies/components/CompanyForm.tsx:289-299`
- **Problem:** `type="number"` shows a spinner widget on desktop and the wrong keyboard on mobile. No `min="0"` prevents negative values. No `inputMode="numeric"`.
- **Why it matters:** CLAUDE.md: "Use semantic `type` values … with matching `inputmode`." Negative revenue is nonsensical.
- **Fix:** Add `inputMode="numeric"` and `min="0"` to both fields.

---

### [MEDIUM] ContactForm renders nested card sections inside a modal — extreme scroll depth

- **File:** `frontend/src/features/contacts/ContactsPage.tsx:466-476`, `frontend/src/features/contacts/components/ContactForm.tsx:68-195`
- **Problem:** ContactForm wraps its four sections in `bg-white shadow rounded-lg p-6` cards inside a `size="lg"` modal. On mobile the modal is full-screen. The card headers add ~50 px of non-field height each; total scroll depth far exceeds a comfortable modal.
- **Why it matters:** CLAUDE.md: "Modal sizing on mobile" and "text overflow inside fields" are in-scope guidelines.
- **Fix:** Remove the inner shadow card wrappers when rendered inside a Modal. Use flat `border-t` section dividers instead.

---

### [MEDIUM] DuplicateWarningModal has no `aria-live` region for screen readers

- **File:** `frontend/src/components/shared/DuplicateWarningModal.tsx:30-35`
- **Problem:** When the modal opens after an async duplicate check, screen-reader users hear the Dialog title but not the count or duplicate list. No `aria-live="polite"` region.
- **Why it matters:** CLAUDE.md: "Async updates (toasts, validation) need `aria-live='polite'`."
- **Fix:** Wrap the count paragraph in `<div aria-live="polite">`.

---

### [MEDIUM] `Input` component generates fragile label-derived IDs — risk of duplicates

- **File:** `frontend/src/components/ui/Input.tsx:21`
- **Problem:** `id || label?.toLowerCase().replace(/\s+/g, '-')` produces duplicate IDs when two instances render the same label (e.g., two "City" fields visible at once). This breaks `htmlFor` label association for screen readers.
- **Why it matters:** CLAUDE.md: "Form controls need `<label>` or `aria-label`."
- **Fix:** Require an explicit `id` prop or use `useId()` as the fallback (as `BillingTermsField.tsx` correctly does).

---

### [MEDIUM] `FormTextarea` missing dark-mode border and background classes

- **File:** `frontend/src/components/forms/FormTextarea.tsx:47-49`
- **Problem:** Non-error state is `border-gray-300 text-gray-900` with no `dark:` variants. `FormInput` at line 41-43 includes `dark:border-gray-600 dark:text-gray-100 dark:bg-gray-700`. The Notes textarea has a light border on dark backgrounds.
- **Why it matters:** Visual regression in dark mode; inconsistent with sibling primitives.
- **Fix:** Add `dark:border-gray-600 dark:text-gray-100 dark:bg-gray-700` to the non-error branch in FormTextarea.

---

### [MEDIUM] Company status `Select` has no required rule or error wired

- **File:** `frontend/src/features/companies/components/CompanyForm.tsx:203-209`
- **Problem:** Status is a required business field but the `Controller` has no `rules` prop and `errors.status?.message` is not passed to `Select`.
- **Why it matters:** Inconsistent with ContactForm which surfaces required field errors on name fields.
- **Fix:** Add `rules={{ required: 'Status is required' }}` to the Controller and pass `error={errors.status?.message}` to Select.

---

### [LOW] Duplicate `getInitialFormData` implementations — two maintenance points

- **File:** `frontend/src/features/contacts/ContactsPage.tsx:120-131`, `frontend/src/features/contacts/ContactDetailPage.tsx:89-98`
- **Problem:** Identical mapping logic duplicated in two files. If someone fixes one, they will miss the other — this already happened with the incomplete mapping.
- **Why it matters:** Causes the exact class of bug found in the CRITICAL findings above.
- **Fix:** Extract `contactToFormData(contact: Contact): Partial<ContactFormData>` into a shared utility, call from both pages.

---

### [LOW] CompanyCard uses `<div role="button">` instead of `<button>`

- **File:** `frontend/src/features/companies/CompaniesPage.tsx:57-70`
- **Problem:** `<div role="button" tabIndex={0} onClick>` pattern instead of a semantic `<button>`.
- **Why it matters:** CLAUDE.md: "Use `<button>` for actions, `<a>`/`<Link>` for navigation — never `<div onClick>`." The `<div>` lacks native button behavior (activation on Space, type submission, etc.).
- **Fix:** Convert outer wrapper to `<article>` or `<li>` with an internal primary-action `<button>` for navigation.

---

### [LOW] Company form section headers missing `dark:text-gray-300`

- **File:** `frontend/src/features/companies/components/CompanyForm.tsx:278, 308, 319, 331, 348`
- **Problem:** All five `<h4>` section headers use `text-gray-700` with no dark variant. ContactForm uses `dark:text-gray-100` on its equivalent headings.
- **Why it matters:** Cosmetic regression in dark mode.
- **Fix:** Add `dark:text-gray-300` to all five `<h4>` elements.

---

## Top 5 fixes ranked

1. **[CRITICAL] ContactForm silent data loss on submit** — address, city, state, zipCode, country, salesCode, and notes are rendered but never sent to the API. Fix all three submit handlers in ContactsPage and ContactDetailPage.

2. **[CRITICAL] Edit pre-fill discards previously saved data** — `getInitialFormData()` in both pages maps only 6 of 13 form fields; every edit wipes server-side address/notes. Extract a shared `contactToFormData` utility and map all fields.

3. **[HIGH] Duplicate warning "View" destroys entered form data** — `pendingFormData` is cleared before navigating to the duplicate; users who return must re-enter the full form. Open the duplicate in a new tab or preserve state.

4. **[HIGH] Zero `autocomplete` attributes across both forms** — 25+ fields with no autofill hints. Add `autoComplete` at each call site.

5. **[HIGH] Company email field has no validation and no error display** — malformed emails accepted silently, unlike the contact form which rejects them.
