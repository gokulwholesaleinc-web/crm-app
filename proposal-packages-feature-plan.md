# Proposal Packages + Customer Package Selection Plan

Date: 2026-05-20  
Status: Planning only. No app implementation has started.  
Revision: 3, updated after technical review and polish pass.

## Goal

Enable one client-facing proposal link to present multiple selectable packages/options to the customer. The customer must pick exactly one package before signing. The signed proposal, staff proposal detail, activity/audit trail, signed PDF/email, and any later payment handoff must preserve which package was selected.

## Current State Confirmed In Code

- Active proposal flow lives in `backend/src/proposals/*` and `frontend/src/features/proposals/*`.
- Staff creates one `Proposal`, uploads optional attachments/signing PDFs, places signature/date boxes, then sends a public link.
- Customer opens `/proposals/public/:token`, reviews one proposal body, opens all required documents, then signs through `SignToConfirmModal`.
- Current proposal pricing is free text in `Proposal.pricing_section`; it is not selectable.
- The old `quotes` router is intentionally unmounted as of 2026-05-14. Its `Quote`, `QuoteLineItem`, `ProductBundle`, and `ProductBundleItem` tables remain for legacy data only and should not be revived for this feature.
- Proposal DB columns `payment_type`, `recurring_interval`, `recurring_interval_count`, `amount`, and `currency` still exist in `backend/src/proposals/models.py` for legacy payment compatibility.
- Current `ProposalCreate` and `ProposalUpdate` schemas do not accept those legacy billing fields. `ProposalBillingFields` is response-only via `ProposalResponse`; public legacy payment fields are still present for old awaiting-payment/paid links.
- `ProposalBase` and `ProposalUpdate` still expose legacy `quote_id` even though the quotes router is unmounted. This is out of scope for package selection, but should be tracked as adjacent cleanup.
- `Payment` has no first-class `proposal_id` or `selected_package_id`, but `backend/src/payments/webhook_processor.py` has implicit legacy proposal payment paths:
  - invoice-paid lookup by `Proposal.stripe_invoice_id`
  - checkout-session lookup by Stripe session metadata `proposal_id`
  - subscription renewal lookup by `Proposal.stripe_subscription_id`
  - refund cascade lookup by payment Stripe invoice/session ids back to proposal
- Existing Stripe catalog tables are `products` and `prices` in `backend/src/payments/models.py`. Package item links to these tables must be optional and informational in MVP.
- Current latest migration file is `backend/alembic/versions/045_proposal_date_fields_doc_views.py`; its Alembic `revision` is `045_proposal_date_placement`. The next migration should use `down_revision = "045_proposal_date_placement"` after confirming with `alembic heads`.

## Decisions For MVP

1. Package selection is required only when a proposal has active packages.
2. Existing/text-only proposals keep working without package selection.
3. Package line items are included in MVP, because the data model needs them for totals, signed snapshots, PDF rendering, and future payment handoff.
4. Package definitions are editable only while the proposal is `draft`; once sent, they are locked, and changes require duplicating into a new draft and reissuing a public link.
5. Do not automatically create a payment link or charge the customer at signature time in MVP.
6. Do not drop legacy proposal billing columns in MVP.
7. Treat legacy proposal billing columns as read-only compatibility data and do not reintroduce them to `ProposalCreate`, `ProposalUpdate`, or the staff package UI.
8. Do not add `selected_package_at`; package selection is persisted atomically with signature acceptance, and `signed_at` plus snapshot `captured_at` cover timing.
9. Selected package snapshot, not live package rows or Stripe catalog rows, is the legal source of truth after signing.
10. Tax inputs are not in MVP. Store `tax_amount` as `0.00` for now and keep the column available for a later tax/payment handoff phase.
11. Stripe product/price imports are not MVP. Product/price links stay optional and informational now; any import workflow belongs in Phase 2 or later.
12. Default customer-facing label is "Packages". Lorenzo can rename this before launch without changing the underlying data model.

## Product Sign-Off Required

The draft-only package edit rule needs Lorenzo's explicit approval before implementation. It is technically safer because customers cannot see package options change under an already-sent link, but it means a customer-requested "add one more option" after send requires duplicating the proposal into a new draft and reissuing a new public link.

## Non-Goals For MVP

- Do not resurrect the retired quotes UI/router.
- Do not replace the Payments module.
- Do not auto-create Stripe invoices/subscriptions on public signature acceptance.
- Do not require package options for proposals that have no active packages.
- Do not build reusable package templates yet.
- Do not require staff to have a populated Stripe product catalog before using proposal packages.

## Recommended Data Model

Use first-class proposal package tables under the active proposals module. Money columns must use `Numeric(12, 2)` to match existing proposal/payment money fields and avoid floating-point drift.

### `proposal_packages`

- `id`
- `proposal_id` FK to `proposals.id`, `ON DELETE CASCADE`, nullable false
- `name`, non-empty
- `description`, nullable text
- `currency`, `String(3)`, uppercase ISO code
- `payment_type`, `String(20)`, `one_time` or `subscription`
- `recurring_interval`, nullable `month` or `year`
- `recurring_interval_count`, nullable integer
- `subtotal`, `Numeric(12, 2)`, server-computed
- `discount_amount`, `Numeric(12, 2)`, server-computed or validated package-level discount
- `tax_amount`, `Numeric(12, 2)`, default `0.00` in MVP
- `total`, `Numeric(12, 2)`, server-computed
- `sort_order`, integer
- `is_recommended`, boolean default false
- `is_active`, boolean default true
- audit timestamps / created_by / updated_by where consistent with local patterns

### `proposal_package_items`

- `id`
- `package_id` FK to `proposal_packages.id`, `ON DELETE CASCADE`, nullable false
- `product_id` nullable FK to `products.id`
- `price_id` nullable FK to `prices.id`
- `description`, non-empty customer-facing text
- `quantity`, `Numeric(10, 2)`, must be greater than 0
- `unit_price`, `Numeric(12, 2)`, must be greater than or equal to 0
- `discount_amount`, `Numeric(12, 2)`, must be greater than or equal to 0
- `total`, `Numeric(12, 2)`, server-computed
- `sort_order`, integer

Product/price links are optional. In MVP they are informational only; staff can write a package without Stripe catalog records. Public renderers and signed snapshots must not depend on `product_id`, `price_id`, Stripe ids, or SKU/internal names.

### `proposals` additions

- `selected_package_id` nullable FK to `proposal_packages.id`, `ON DELETE SET NULL`
- `selected_package_snapshot` nullable JSON/JSONB. Implement the column with a SQLAlchemy type that uses JSONB on Postgres and JSON on SQLite tests, for example the same variant pattern used by existing signature-coordinate JSON fields rather than raw JSON everywhere.

Because `proposal_packages.proposal_id` points to `proposals.id` and `proposals.selected_package_id` points back to `proposal_packages.id`, the migration should create package tables first, then add the nullable selected-package FK to proposals. SQLAlchemy relationships must specify `foreign_keys` explicitly to avoid ambiguous join paths.

### DB Constraints And Indexes

- Index `proposal_packages(proposal_id, sort_order, id)`.
- Index `proposal_package_items(package_id, sort_order, id)`.
- Add partial unique index for one recommended package per proposal:

```sql
CREATE UNIQUE INDEX uq_proposal_packages_one_recommended
ON proposal_packages (proposal_id)
WHERE is_recommended = true;
```

- Add check constraints for money/quantity fields where practical:
  - package totals and amounts greater than or equal to 0
  - item quantity greater than 0
  - item unit price and discount greater than or equal to 0
  - recurring interval/count required for subscription packages
- Cross-row "all active packages share one currency" cannot be expressed as a simple CHECK constraint. Enforce it in `ProposalService` inside the package write transaction and cover it with backend tests.
- Public exposure of `sort_order` is intentional: staff-curated package order is customer-visible and controls public card display order. It must not be treated as sensitive.

## `is_active` Semantics

`is_active` is a soft-delete/customer-visibility flag:

- Active packages are shown to the customer and are selectable.
- Inactive packages are hidden from the customer and cannot be selected.
- Staff can deactivate/reactivate packages only while the proposal is `draft`.
- Package deletion in the staff UI should normally set `is_active = false` rather than physically delete, so draft history and audit logs remain understandable.
- Hard delete remains acceptable only before first send and only if the row was never selected.
- After signing, selected snapshot remains the legal record even if live package rows are later hidden, deleted by data cleanup, or changed by a migration.

## Selected Package Snapshot

Persist this JSON shape into `proposals.selected_package_snapshot` inside the same atomic accept update that captures the signature.

Money values should be serialized as fixed-scale strings, not JSON floats.

```json
{
  "package_id": 123,
  "name": "Growth Package",
  "description": "Monthly growth support and implementation.",
  "currency": "USD",
  "payment_type": "subscription",
  "recurring_interval": "month",
  "recurring_interval_count": 1,
  "subtotal": "2500.00",
  "discount_amount": "0.00",
  "tax_amount": "0.00",
  "total": "2500.00",
  "is_recommended": true,
  "captured_at": "2026-05-20T22:15:30Z",
  "items": [
    {
      "description": "Implementation and onboarding",
      "quantity": "1.00",
      "unit_price": "1500.00",
      "discount_amount": "0.00",
      "total": "1500.00"
    },
    {
      "description": "Monthly optimization retainer",
      "quantity": "1.00",
      "unit_price": "1000.00",
      "discount_amount": "0.00",
      "total": "1000.00"
    }
  ]
}
```

No Stripe ids, product ids, price ids, internal SKU names, or staff-only notes should appear in this snapshot.

Set `captured_at` from the same `now = datetime.now(UTC)` instance used for `accepted_at` and `signed_at` in the atomic accept update.

## Package Validity Rules

A package is valid for send and public selection when:

- `is_active` is true.
- `name` is non-empty after trimming.
- `currency` is a 3-letter uppercase ISO code.
- All active packages on the proposal share the same currency.
- `payment_type` is `one_time` or `subscription`.
- Subscription packages have `recurring_interval` and `recurring_interval_count >= 1`.
- One-time packages have no recurring interval/count.
- Package has at least one item.
- Every item has non-empty customer-facing `description`.
- Every item has `quantity > 0`.
- Every item has `unit_price >= 0`.
- Every item has `discount_amount >= 0`.
- Item total is recomputed server-side as `quantity * unit_price - discount_amount`.
- Package subtotal/discount/total are recomputed server-side from items and package-level inputs.
- Package `tax_amount` is `0.00` in MVP.
- Package `total > 0`.
- At most one active package per proposal is recommended.

The server, not the browser, is responsible for totals. The frontend can display previews, but service-layer recomputation is the source of truth.

## Backend Plan

### Models And Migrations

1. Add package models in `backend/src/proposals/models.py`.
2. Add Alembic migration after revision id `045_proposal_date_placement`:
   - current file: `045_proposal_date_fields_doc_views.py`
   - current revision id: `045_proposal_date_placement`
   - confirm with `alembic heads` before writing the migration
3. Create `proposal_packages`.
4. Create `proposal_package_items`.
5. Add `proposals.selected_package_id` with `ON DELETE SET NULL`.
6. Add `proposals.selected_package_snapshot` as JSONB on Postgres and JSON on SQLite test DB.
7. Add indexes and constraints listed above.
8. Keep legacy proposal billing columns in place. Do not drop them in MVP.
9. `downgrade()` should drop `proposals.selected_package_snapshot` and `proposals.selected_package_id`, then `proposal_package_items`, then `proposal_packages`. Selected-snapshot data loss on rollback is acceptable in MVP because no Stripe side effects are created from package selection.

### Schemas

Update `backend/src/proposals/schemas.py` with:

- `ProposalPackageItemCreate`
- `ProposalPackageItemUpdate`
- `ProposalPackageItemResponse`
- `ProposalPackageCreate`
- `ProposalPackageUpdate`
- `ProposalPackageResponse`
- `ProposalPackagePublicResponse`
- `SelectedPackageSnapshot`
- `ProposalAcceptRequest.selected_package_id`
- `ProposalResponse.packages`
- `ProposalResponse.selected_package_id`
- `ProposalResponse.selected_package_snapshot`
- `ProposalPublicResponse.packages`
- `ProposalPublicResponse.selected_package_snapshot` after acceptance

Do not add legacy billing fields back to `ProposalBase`, `ProposalCreate`, or `ProposalUpdate`. Add a regression test that posting `amount`, `payment_type`, or cadence fields to proposal create/update is still rejected.

All public package money fields should be Pydantic `Decimal` fields and serialize to JSON as fixed-scale strings. Do not convert public package money to floats in schemas, API helpers, or frontend fixtures.

Public package response fields must be explicitly filtered:

- package id
- name
- description
- currency
- payment type/cadence
- subtotal/discount/tax_amount/total, with `tax_amount` fixed at `0.00` in MVP
- recommended flag
- display order
- item description/quantity/unit price/discount/total

Do not expose `product_id`, `price_id`, Stripe ids, owner ids, audit ids, internal SKUs, or staff-only metadata.

### Service Layer

Update `backend/src/proposals/service.py`:

1. Eager-load packages and items anywhere proposals are returned to staff or public routes.
2. Add package CRUD helpers.
3. Add `_assert_packages_mutable(proposal)`:
   - allow only `status == "draft"` and `signed_at is None`
   - reject edits after send/view/sign
4. Add service-level package validation/recomputation:
   - normalize money with `Decimal`
   - compute item totals
   - compute package subtotal/discount/total and set package `tax_amount` to `0.00` in MVP
   - enforce one currency across active packages
   - enforce one recommended package, alongside DB partial unique index
5. Add `get_active_packages_for_public(proposal_id)`.
6. Add `build_selected_package_snapshot(package, captured_at)`.
7. Update public accept flow:
   - compute `now = datetime.now(UTC)` once at the top of the accept flow
   - validate proposal status and expiry as today
   - validate document-open gate as today
   - fetch active packages before the atomic update
   - if active packages exist, require `selected_package_id`
   - ensure selected package belongs to proposal and is active
   - build snapshot with `build_selected_package_snapshot(..., captured_at=now)` before the conditional update
   - run one conditional `UPDATE proposals ... WHERE id = :id AND status IN ('sent', 'viewed')`
   - include `selected_package_id` and `selected_package_snapshot` in that same `SET` clause
   - do not persist any package selection outside the winning accept update
   - this validation-then-update flow depends on package definitions being locked after send; if that lock is ever lifted, package state must be re-validated inside the same transaction as the accept update
8. Update duplicate/clone behavior:
   - copy active draft package definitions and line items
   - clear `selected_package_id`
   - clear `selected_package_snapshot`
9. Update `generate_proposal_pdf`:
   - pre-sign customer proposal PDF renders all active package options
   - signed generated PDF renders the selected package snapshot only
10. Update signed-copy email flow:
   - email body mentions selected package when available
   - attachments remain the signed PDFs as today
11. Preserve existing webhook compatibility:
   - do not remove proposal Stripe id fields yet
   - do not break `webhook_processor.py` invoice/session/subscription lookups
   - Phase 2 payment FKs must coexist with and then gradually replace these legacy paths

Atomic accept update should include these new fields:

```python
.values(
    status="accepted",
    accepted_at=now,
    signer_name=signer_name,
    signer_email=normalized_signer_email,
    signer_ip=signer_ip,
    signer_user_agent=signer_user_agent,
    signer_timezone=signer_timezone,
    signed_at=now,
    signature_image=signature_image,
    selected_package_id=selected_package.id if selected_package else None,
    selected_package_snapshot=selected_package_snapshot,
)
```

Validation must happen before this conditional update so invalid package submissions do not consume the one winning accept race.

### Router

Update `backend/src/proposals/router.py`:

- Add staff package endpoints:
  - `GET /api/proposals/{proposal_id}/packages`
  - `POST /api/proposals/{proposal_id}/packages`
  - `PATCH /api/proposals/{proposal_id}/packages/{package_id}`
  - `DELETE /api/proposals/{proposal_id}/packages/{package_id}`
  - optional reorder endpoint if PATCHing sort order is too clunky
- Use the same permission pattern as proposal edit:
  - current code uses `ProposalUpdateUser = require_permission("contacts", "update")` until a first-class proposals permission domain exists
  - check ownership/shared access exactly as proposal edit/detail does
- Update public `GET /api/proposals/public/{token}` to include active public-safe packages.
- Update public `POST /api/proposals/public/{token}/accept` to receive and validate `selected_package_id`.
- Keep existing public attachment/signing-document read gates intact.
- Backend public responses should null legacy public payment fields whenever active packages exist or `selected_package_snapshot` is present, so non-React consumers do not have to rediscover the package-vs-legacy-payment mutex.

### Activity And Audit

- Keep existing audit entity update/create behavior.
- Add an activity/timeline entry when a public accept selects a package, linked to `entity_type="proposals"` and `entity_id=proposal.id`.
- Activity subject should include selected package name and total, for example: `Package selected: Growth Package (USD 2500.00)`.
- Activity should use the proposal owner where possible so the staff timeline makes the selected package visible without opening raw audit logs.
- Include selected package in `proposal_signed` notification metadata if that event payload is expanded.

## Frontend Plan

### Types And API

Update:

- `frontend/src/types/proposals.ts`
- `frontend/src/api/proposals.ts`
- `frontend/src/hooks/useProposals.ts`

Add typed package/item structures, package API methods, and cache invalidation for proposal detail/list when packages change.

Use `Intl.NumberFormat` for all public and staff package currency display. Do not hand-format currency strings.

### Staff UX

Keep `ProposalForm` focused on core proposal metadata and text sections. Package management belongs on `ProposalDetail`.

Recommended staff detail UI:

- Dedicated "Packages" section near existing Pricing/Pricing Notes.
- Repeated package cards with item rows.
- Add/edit/deactivate/reorder package actions only while `proposal.status === "draft"`.
- Disable and explain package controls after send/view/sign.
- One package can be marked recommended.
- Show total/currency/cadence prominently.
- Preserve existing `pricing_section` as "Pricing Notes" or "Additional Pricing Notes".
- After create, the existing navigation to proposal detail remains; staff adds packages there.

No `ProposalForm` changes are planned for MVP.

### Send Checklist

Update `frontend/src/features/proposals/proposalStatus.ts`.

If a proposal has active packages, checklist requires:

- at least one active package
- every active package has non-empty name
- every active package has one shared currency
- every active package has valid payment cadence
- every active package has at least one valid item
- every active package has server-returned `total > 0`
- at most one recommended package
- signing document/date placement checks remain unchanged

If a proposal has no active packages, do not block send for missing packages; preserve text-only proposal behavior.

If a proposal has any package rows but zero active packages, block send. Text-only behavior applies only to proposals with no package rows at all.

### Customer Public View

Update `frontend/src/features/proposals/PublicProposalView.tsx`:

- Render package choices before "Your Response".
- Use real native radio inputs styled as cards where possible.
- Wrap package options in a labeled fieldset/legend or `role="radiogroup"`.
- If custom radio roles are used, implement:
  - `role="radiogroup"`
  - `role="radio"`
  - `aria-checked`
  - tab focus
  - Space/Enter select
  - arrow-key movement between options
- Desktop: responsive package grid.
- Mobile: stacked package cards.
- Show recommended badge when present.
- Show cadence, total, description, and line items.
- Hide the tax row when `tax_amount` is `0.00`; do not show customers a "Tax: $0.00" line in MVP.
- Preserve Pricing Notes as context, visually separate from required package selection.
- Hide the legacy payment block whenever active packages exist or `selected_package_snapshot` is present. Package selection and legacy awaiting-payment checkout must be mutually exclusive in the rendered public page.
- Disable `Sign to Accept` until all required documents are opened and a package is selected when active packages exist.
- Show clear inline status when package selection is missing.
- Pass `selected_package_id` into the accept request.

Update `frontend/src/components/SignToConfirmModal.tsx`:

- Display selected package name and formatted price summary.
- Keep email locked as today.
- Keep ESIGN consent behavior unchanged.
- The parent public view owns `selected_package_id`; modal should not invent package state.

### Staff Post-Acceptance View

Update `frontend/src/features/proposals/ProposalDetail.tsx` and `ProposalAuditCard`:

- Show selected package in details/sidebar/audit area.
- Use `selected_package_snapshot` after signing, not mutable live package rows.
- Package editor remains visible as read-only history after signing.
- A future Phase 2 CTA can offer "Create payment from selected package."

## PDF And Email Integration

There are three relevant rendering layers; avoid duplicating package blocks blindly:

1. `ProposalService.generate_proposal_pdf` builds the branded proposal HTML PDF.
   - Before signing: render all active package options.
   - After signing: render selected package snapshot only.
2. `backend/src/proposals/pdf_stamper.py` stamps uploaded signing PDFs and appends the audit page.
   - Extend `StampInputs` or the audit-page builder to include `selected_package_snapshot`.
   - The appended audit page is the natural place to preserve the selected package on stamped agreement PDFs.
   - Restamp must render cleanly when `selected_package_snapshot is None` for pre-MVP signed proposals; in that case, skip the package block.
3. `backend/src/email/branded_templates.py` renders email bodies.
   - Signed-copy email should mention selected package name and formatted total.

`backend/src/email/pdf_service.py` and `backend/src/email/pdf_render.py` should remain generic rendering utilities unless an existing call path specifically needs package data.

All package-supplied text must be escaped before rendering into HTML-based PDFs and email bodies: package name, package description, and item description. The audit-page PDF renderer should also sanitize control characters before drawing package text.

## Payment Handoff Plan

### Phase 1

- Store selected package only.
- Preserve current legacy proposal payment/webhook behavior.
- Do not automatically create Stripe invoices/subscriptions on signature.
- Staff can manually create payment from the existing Payments module.

### Phase 2

- Add explicit payment linkage:
  - `payments.proposal_id`
  - `payments.selected_package_id`
  - possibly `subscriptions.proposal_id`
  - possibly `subscriptions.selected_package_id`
- Preserve and migrate existing implicit linkage paths:
  - invoice id to `Proposal.stripe_invoice_id`
  - checkout session metadata `proposal_id`
  - subscription id to `Proposal.stripe_subscription_id`
- Add backend helper to create one-time invoice or subscription checkout from selected package snapshot.
- Add staff CTA after acceptance: "Create payment from selected package."
- Backfill/reporting should treat selected package snapshot as historical truth, not live Stripe catalog data.

## Test Plan

### Backend

Add/extend tests under `backend/src/proposals/tests/`:

- Migration/model metadata includes package tables, selected FK, and partial unique recommended index.
- Package schema validation rejects invalid cadence, quantity, money, empty names, empty item descriptions.
- Package writes recompute totals server-side and ignore client-supplied drift.
- Staff can create/update/deactivate/reorder packages while proposal is draft.
- Send rejects a proposal that has package rows but zero active packages.
- Package edits are rejected once proposal is sent/viewed/accepted.
- Public proposal response includes active packages only, in display order, using public-safe fields.
- Public response never exposes `product_id`, `price_id`, Stripe ids, owner ids, or audit fields.
- `ProposalPublicResponse` returns `null` for `payment_type`, `recurring_interval`, `recurring_interval_count`, `amount`, `currency`, `stripe_payment_url`, and `paid_at` when active packages or `selected_package_snapshot` exist.
- Public page hides legacy awaiting-payment checkout whenever active packages or a selected package snapshot are present.
- Accept rejects missing `selected_package_id` when active packages exist.
- Accept rejects package id from another proposal.
- Accept rejects inactive package.
- Accept succeeds without package selection for legacy/text-only proposals.
- Accept persists `selected_package_id` and exact selected package snapshot.
- Concurrent accepts: only one wins, and persisted `selected_package_id` matches the winner's payload.
- Duplicate proposal copies package definitions but clears selected-package fields.
- Generated proposal PDF includes active package options before signing.
- Signed generated PDF includes selected package snapshot.
- Stamped signing-document audit page includes selected package snapshot.
- Stamped signing-document audit page renders cleanly with no package block when `selected_package_snapshot` is `None` for pre-MVP signed proposals and restamp calls.
- Legacy proposal billing fields remain rejected on create/update and read-only on responses.
- Existing webhook processor proposal paid/refund paths still pass.
- Legacy `quote_id` create/update surface remains unchanged unless handled in a separate cleanup ticket.

### Frontend

Update/add tests:

- `frontend/src/features/proposals/PublicProposalView.test.tsx`
  - renders multiple package options
  - uses accessible radio semantics/native radios
  - sign disabled until package selected
  - document gate and package gate both apply
  - selected package id included in accept payload
  - package prices use formatted currency output
  - tax row is hidden when package `tax_amount` is `0.00`
  - legacy payment CTA is hidden when package options or selected package snapshot exist
  - accepted confirmation handles selected package response
- `frontend/src/components/SignToConfirmModal.test.tsx`
  - selected package summary renders
  - submit remains gated by signature and terms
- `frontend/src/features/proposals/proposalStatus.test.ts`
  - package readiness is included in send checklist
  - text-only proposals are not blocked by missing packages
- Add `frontend/src/features/proposals/ProposalDetail.test.tsx` for MVP:
  - packages render in detail
  - package editor locked after send/sign
  - selected snapshot visible after acceptance

### Manual QA

Run with Docker Compose:

1. Create proposal with no packages; verify old flow still works.
2. Create draft proposal with two packages and line items.
3. Verify totals are recomputed by backend.
4. Send proposal; verify package editor locks.
5. Open public link; verify package cards render and are keyboard selectable.
6. Try signing without selecting package; verify client-side and server-side block.
7. Open required documents; select package; sign.
8. Verify staff detail shows accepted status and selected package snapshot.
9. Verify signed generated PDF and stamped signing-document audit page include selected package.
10. Verify signed-copy email mentions selected package.
11. Verify duplicate creates a new draft with package definitions and no selection.

## Rollout Plan

1. Add backend migration, models, schemas, service validation, package APIs, and public response support.
2. Keep package creation UI hidden until public selection and accept-time snapshot are ready.
3. Build staff package management UI.
4. Build public package selection UI and accept-time snapshot/persistence in the same deploy or behind the same feature flag.
5. Add PDF/email/audit rendering.
6. Add backend/frontend tests and run full suites.
7. Manually QA through Docker Compose before deploy.
8. Deploy backend first. Returning `packages: []` is non-breaking for old frontend JSON consumers because unknown fields are ignored by the current runtime.
9. Before deploy, grep old frontend consumers for strict destructuring/selectors around `useProposal` and public proposal fetches. Current code only uses `useProposal` in `ProposalDetail`, but recheck before release.
10. Deploy frontend only after backend accepts and persists `selected_package_id`; do not ship frontend package cards against a backend that silently accepts without snapshot.
11. Monitor public accept errors, package validation errors, and signed PDF generation errors after release.

## Risks And Mitigations

- Risk: Old proposals break because package selection becomes required.
  - Mitigation: Only require selection when active packages exist.
- Risk: Sent proposals change under customers mid-flight.
  - Mitigation: Lock package definitions once proposal status leaves `draft`.
- Risk: Reviving quotes creates architecture drift.
  - Mitigation: Build proposal package tables under active proposals module.
- Risk: Package edited after signature changes legal record.
  - Mitigation: Block edits after send/sign and persist selected snapshot.
- Risk: Customer signs with stale package data.
  - Mitigation: Server validates active package at accept time and snapshots current package in the winning accept update.
- Risk: Two accepts race with different packages.
  - Mitigation: Existing conditional accept update allows only one winner; selected package fields are part of that same update.
- Risk: Payment reporting remains fuzzy.
  - Mitigation: Preserve current implicit webhook paths in Phase 1; add direct proposal/package FKs in Phase 2.
- Risk: Public UI exposes internal Stripe/product data.
  - Mitigation: Use explicit public response schema and selected snapshot without internal ids.
- Risk: Package UI conflicts with legacy awaiting-payment checkout.
  - Mitigation: Public page hides legacy payment CTA whenever package options or selected snapshot exist.
- Risk: Totals drift between browser, DB, PDF, and email.
  - Mitigation: Server recomputes totals and all renderers use server-returned data/snapshot.
- Risk: Mixed-version deploy lets customers sign without persisted package selection.
  - Mitigation: Ship public UI and backend accept persistence together or feature-flag the UI off.

## Open Product Decisions

1. Should inactive draft packages remain visible to staff as collapsed history, or be hidden by default?

## Suggested MVP Scope

Build the first release with:

- Proposal package and package item tables.
- Draft-only staff package CRUD on proposal detail.
- Server-side total recomputation and package validity checks.
- Customer package radio-card selection with accessible keyboard behavior.
- Server-side selected package validation on accept.
- Selected package snapshot stored in the atomic accept update.
- Staff detail/activity/audit display of selected package snapshot.
- Signed generated PDF and stamped signing-document audit page include selected package snapshot.
- Signed-copy email mentions selected package.
- No automatic payment creation yet.

That MVP gives customers the package-choice experience without entangling the signature flow with Stripe side effects or the retired quotes architecture.
