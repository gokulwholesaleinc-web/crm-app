# Proposals + Quotes Audit

## Summary

- **CRITICAL:** 2
- **HIGH:** 4
- **MEDIUM:** 6
- **LOW:** 5

Total: 17 findings across 9 files.

---

## Proposals vs Quotes — divergence

- **Send flow — resend capability:** Proposals correctly allow resend from `draft | sent | viewed`; quotes hard-gate `canSend = isDraft` only. Once a quote is sent the CRM user can't re-trigger the email without hacking the backend.
- **Edit lock:** Proposals gate edit on `draft | sent | viewed` (unlocks for resend scenarios). Quotes correctly gate edit on `isDraft` only — tighter and better.
- **Public sign UX:** Proposals inline the name/email fields directly in the "Your Response" section — one screen, accessible, no extra modal. Quotes put those fields behind a modal triggered by "Accept Quote" only; the "Reject Quote" button calls `handleReject` which silently reads `signerEmail` state that is only populated if the user opened the accept modal first. This is a functional bug (CRITICAL — see Finding #1).
- **Error a11y:** Proposals use `role="alert" aria-live="polite"` on `signError`. Quotes' esign modal error div has no ARIA live region.
- **Currency formatting in totals preview:** Proposals don't have an in-form live total (not needed — freetext pricing). Quotes show a live totals block but format numbers as raw `.toFixed(2)` without currency symbol or `Intl.NumberFormat`, creating user confusion.
- **Logo `<img>` — CLS:** PublicProposalView logo `<img>` has `height` but NO `width` attribute, causing CLS. PublicQuoteView correctly sets both `width` and `height`.
- **Download filename:** QuoteDetail's PDF download names the file `quote-${number}.html` while the button says "Download PDF". ProposalDetail doesn't expose a PDF download button at all (the hook exists but is unused in the detail page).
- **Filter/pagination URL sync:** Both list pages initialize `searchQuery` from `?search=` but never write back to the URL when the user changes the filter or status. Status filter and page number are lost on refresh/share. Both are equally broken.
- **Billing card:** ProposalBillingCard is self-contained and well-structured. Quotes have no equivalent billing sidebar card; billing info is shown inline in the Details sidebar block.

---

## Findings

### [CRITICAL] Reject button in PublicQuoteView silently fails when accept modal was never opened

- **File:** `frontend/src/features/quotes/PublicQuoteView.tsx:158-183`
- **Problem:** `handleReject` reads `signerEmail` state (line 160). That state is only populated when the user types in the e-sign modal, which is opened by the Accept button. A customer who wants to reject without having opened the accept modal first gets the error "Please enter your email address to reject this quote" — but there is no visible email field outside the modal. The error surfaces in `esignError`, which is only rendered inside `showEsignModal && ...`, so the error message is invisible to the user.
- **Why it matters:** Customers who try to decline a quote hit an invisible, unrecoverable error. They may click Accept by mistake just to get the email field and then abort — corrupting quote status.
- **Fix:** Either (a) show email + name fields inline in the "Your Response" section like PublicProposalView does, and remove the separate modal; or (b) open the e-sign modal for both accept and reject, adjusting copy and only requiring name for accept.

---

### [CRITICAL] PDF download filename is `.html` not `.pdf`

- **File:** `frontend/src/features/quotes/QuoteDetail.tsx:104`
- **Problem:** `a.download = \`quote-${quote.quote_number}.html\`` — the button label says "Download PDF" but the file is saved with a `.html` extension. The `downloadQuotePDF` API call hits `/api/quotes/{id}/pdf?download=true`, expected to return a PDF blob. The wrong extension causes the OS to open it in a browser as HTML.
- **Why it matters:** Customer-facing PDF is broken for every user who uses the download button.
- **Fix:** Change to `\`quote-${quote.quote_number}.pdf\``.

---

### [HIGH] Quote canSend blocks resend after first send

- **File:** `frontend/src/features/quotes/QuoteDetail.tsx:206`
- **Problem:** `const canSend = isDraft` — once a quote is sent (status moves to `sent`), the Send button disappears and the CRM user has no way to re-trigger the email. Proposals explicitly allow resend from `sent | viewed` states with a "Resend" label.
- **Why it matters:** CRM operators cannot fix delivery failures without backend API access.
- **Fix:** Adopt the proposal pattern: `canSend = ['draft', 'sent', 'viewed'].includes(quote.status)` and change label to "Resend" when not draft.

---

### [HIGH] esignError in PublicQuoteView e-sign modal has no ARIA live region

- **File:** `frontend/src/features/quotes/PublicQuoteView.tsx:570-573`
- **Problem:** The error `<div>` inside the e-sign modal has no `role="alert"` or `aria-live="polite"`. Screen readers won't announce the error when it appears dynamically. PublicProposalView does this correctly (`role="alert" aria-live="polite"` at line 499).
- **Why it matters:** This is a customer-facing unauthenticated surface. Screen reader users signing a quote will not be notified of validation errors.
- **Fix:** Add `role="alert" aria-live="polite"` to the error `<div>` at line 572.

---

### [HIGH] PublicProposalView logo `<img>` missing `width` attribute — causes CLS

- **File:** `frontend/src/features/proposals/PublicProposalView.tsx:265-271`
- **Problem:** The logo `<img>` has `height={30}` set but no `width` attribute. Browsers need both to reserve layout space and avoid cumulative layout shift (CLS). PublicQuoteView (line 278) correctly sets `width={36} height={36}`.
- **Why it matters:** CLS degrades Core Web Vitals on the customer-facing public proposal page.
- **Fix:** Add `width={180}` (matching `maxWidth: 180`) or use `width="auto"` with explicit height.

---

### [HIGH] Quote totals preview shows raw numbers without currency

- **File:** `frontend/src/features/quotes/QuoteForm.tsx:533-549`
- **Problem:** The live totals block uses `.toFixed(2)` (e.g., `1234.00`) instead of `Intl.NumberFormat` with the selected currency. When the currency changes from USD to EUR the preview numbers show no symbol, making the preview misleading. CLAUDE.md explicitly flags hardcoded number formats as an anti-pattern.
- **Why it matters:** A user adding line items in EUR sees the same numeric string as USD — no visual signal of currency.
- **Fix:** Format using `new Intl.NumberFormat(undefined, { style: 'currency', currency: formData.currency }).format(value)` for subtotal, discount, tax, and total fields.

---

### [MEDIUM] SendInvoiceModal hardcodes "$" in amount label

- **File:** `frontend/src/features/payments/components/SendInvoiceModal.tsx:148`
- **Problem:** `<label>Amount ($)</label>` — hardcodes USD currency symbol. The modal has no currency selector; if the tenant operates in another currency the label is wrong. CLAUDE.md flags hardcoded currency formats as an anti-pattern.
- **Why it matters:** Incorrect label causes operator confusion when billing non-USD customers.
- **Fix:** Remove the parenthetical `($)` from the label, or add a currency select and format the label dynamically.

---

### [MEDIUM] Bundle dropdown in QuoteDetail has no click-outside close or keyboard dismiss

- **File:** `frontend/src/features/quotes/QuoteDetail.tsx:279-320`
- **Problem:** `showBundleDropdown` is toggled by clicking "Add Bundle". There is no `useEffect` to close it on click-outside, no `onBlur`, and no Escape key handler. The QuoteForm has this wired correctly with `bundleMenuRef` + `document.addEventListener('mousedown', ...)` (QuoteForm.tsx lines 153-160).
- **Why it matters:** Users can accidentally leave the bundle dropdown open and click unintentionally; keyboard users have no way to dismiss it.
- **Fix:** Add a click-outside handler using a ref (matching the QuoteForm pattern) and an `onKeyDown` Escape handler.

---

### [MEDIUM] Filter and pagination state not synced to URL in list pages

- **File:** `frontend/src/features/proposals/ProposalsPage.tsx:31,35` / `frontend/src/features/quotes/QuotesPage.tsx:28,30`
- **Problem:** Both pages read the initial `search` value from `?search=` but never write back. Changing the status filter, page number, or page size is not reflected in the URL. A shared or bookmarked URL always shows "All Statuses, page 1". CLAUDE.md states: "URL should reflect state (filters, tabs, pagination) in query parameters."
- **Why it matters:** Users can't share filtered views, bookmark results, or use the browser back button to restore state after navigating to a detail page.
- **Fix:** Use `setSearchParams` to keep `search`, `status`, and `page` in sync with URL state.

---

### [MEDIUM] ProposalForm uses non-lazy `useState` for large initial object

- **File:** `frontend/src/features/proposals/ProposalForm.tsx:23`
- **Problem:** `useState({ title: ..., content: ..., ... })` — the object literal is constructed on every render call before React discards it after the first mount. QuoteForm correctly uses `useState(() => ({ ... }))`. CLAUDE.md explicitly requires lazy state initialization.
- **Why it matters:** Minor GC pressure from recreating an 8+ field object literal on every re-render call.
- **Fix:** Change `useState({ ... })` to `useState(() => ({ ... }))` for the `formData` state.

---

### [MEDIUM] PublicQuoteView logo `<img>` forces square dimensions, distorting wide logos

- **File:** `frontend/src/features/quotes/PublicQuoteView.tsx:278-283`
- **Problem:** `width={36} height={36}` with `maxHeight: 36`. A landscape logo gets forced into a 36x36 box. PublicProposalView handles this better (`height: 30, width: 'auto', maxWidth: 180`).
- **Why it matters:** Branded logos for customers appear visually distorted on the public quote view.
- **Fix:** Remove the hard `width` attribute and use `style={{ height: 36, width: 'auto', maxWidth: 200 }}`, keeping `height={36}` for CLS.

---

### [MEDIUM] AIProposalGenerator hardcodes "$" in opportunity option labels

- **File:** `frontend/src/features/proposals/AIProposalGenerator.tsx:24`
- **Problem:** `label += \` ($${opp.amount.toLocaleString()})\`` — hardcodes USD. `opp.amount` could be in any currency and `toLocaleString()` without options doesn't include currency formatting. CLAUDE.md flags hardcoded number formats.
- **Why it matters:** Opportunity amounts in EUR/GBP display with "$" prefix — misleading.
- **Fix:** Use `new Intl.NumberFormat(undefined, { style: 'currency', currency: opp.currency ?? 'USD' }).format(opp.amount)`.

---

### [LOW] Bundles toggle button in QuotesPage missing `aria-expanded`

- **File:** `frontend/src/features/quotes/QuotesPage.tsx:104-108`
- **Problem:** The "Bundles" Button that toggles the BundleManager panel has no `aria-expanded={showBundles}` attribute. Screen readers cannot tell users whether the panel is expanded or collapsed.
- **Why it matters:** WCAG 2.1 SC 4.1.2 — disclosure widgets must communicate state.
- **Fix:** Add `aria-expanded={showBundles}` to the Bundles Button.

---

### [LOW] QuoteDetail bundle dropdown "Add Bundle" missing `aria-expanded` / `aria-haspopup`

- **File:** `frontend/src/features/quotes/QuoteDetail.tsx:279-284`
- **Problem:** The inline `<button>` toggling `showBundleDropdown` has no `aria-expanded` or `aria-haspopup="listbox"` attributes. It's styled as a text link but is functionally a disclosure button.
- **Why it matters:** AT users don't know the button reveals a menu.
- **Fix:** Add `aria-expanded={showBundleDropdown} aria-haspopup="listbox"`.

---

### [LOW] Send mutation error handlers swallow backend detail messages

- **File:** `frontend/src/hooks/useProposals.ts:77-88` / `frontend/src/hooks/useQuotes.ts:54-63`
- **Problem:** Both send mutation `onSuccess` handlers invalidate queries but there is no `onError` handler. The detail page `handleSend` catch blocks call `showError('Failed to send proposal')` without extracting `err?.response?.data?.detail`. If the backend returns "No email address on file for contact", that detail is silently swallowed.
- **Why it matters:** CRM operators see a generic toast instead of actionable error text.
- **Fix:** In the catch blocks in ProposalDetail and QuoteDetail, extract and surface `(err as AxiosError)?.response?.data?.detail`.

---

### [LOW] `useDownloadProposalPDF` is a plain async function, not a mutation hook

- **File:** `frontend/src/hooks/useProposals.ts:93-105`
- **Problem:** Returns a plain async function instead of a `useMutation` result. The quote equivalent (`useDownloadQuotePDF`) correctly uses `useMutation`, giving the caller `isPending`/`isError` state. The proposal hook has no loading state.
- **Why it matters:** Any UI that calls `useDownloadProposalPDF` can't show a spinner or disable the button during download.
- **Fix:** Convert to `useMutation` matching `useDownloadQuotePDF`.

---

## Top 5 fixes ranked

1. **[CRITICAL] PublicQuoteView reject flow silently fails** — customers cannot decline quotes without first opening the accept modal; fix: inline signer fields or handle reject in the same modal (`PublicQuoteView.tsx:158`).
2. **[CRITICAL] PDF download saves as `.html`** — every "Download PDF" click produces an HTML file; fix: change `.html` to `.pdf` (`QuoteDetail.tsx:104`).
3. **[HIGH] Quote canSend blocks resend** — operators cannot resend quotes after first send; fix: adopt proposal `canSend` pattern (`QuoteDetail.tsx:206`).
4. **[HIGH] esignError has no aria-live in e-sign modal** — screen reader users on the public quote page receive no error feedback; fix: add `role="alert" aria-live="polite"` (`PublicQuoteView.tsx:572`).
5. **[HIGH] Quote totals preview uses `.toFixed` not `Intl.NumberFormat`** — currency-free preview misleads multi-currency operators; fix: wrap totals in `Intl.NumberFormat` with `formData.currency` (`QuoteForm.tsx:533-549`).
