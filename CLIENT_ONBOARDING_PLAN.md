# Client Onboarding — Planning Doc (v2.6, implementation-spec)

**Status:** Design / pre-build. No code yet.
**Owner:** Lorenzo (LinkCreative)
**Author:** Harsh + Claude — v2.1→…→**v2.6** (fifth audit, all findings verified against live code 2026-05-29). Supersedes the docs-only v0.
**Codebase basis:** file:line inline. **Line numbers drift — re-grep before building.**

### Changelog v2.5 → v2.6 (fifth audit — all 13 findings confirmed)
- **P1** Completed packets no longer leak the download link pre-gate — the access-token-only GET returns **"completed — check your email"** only; the download landing link is returned **only with a valid session** or via the email (§5.2 matrix, §5.3).
- **P1** Phase B uses an **atomic per-doc stamp lease** (`stamp_lease_at` conditional UPDATE) + conditional `attachment_id` set + **orphan cleanup** if a concurrent worker wins — two reclaims can't both stamp/attach (§4.3, §5.2).
- **P1** `active` status reconciled: writes (PATCH/signature/claim) allow **`active|opened|in_progress`**; `opened` is set on the **first verified document view**. Transition defined; matrix updated (§4.2, §5.2).
- **P1** Completion download is **proxied through our route** (not an R2 redirect) so `Cache-Control: no-store` + `Referrer-Policy: no-referrer` are actually applied — the R2 presign passes only Bucket/Key (verified, `object_storage.py:62`) and can't set them on a redirect (§5.3).
- **P1** No-contact trigger failure writes a **durable proposal Activity row** (the `Proposal` model has no field for a flag, `models.py:147`) — not a best-effort notification (§9).
- **P1** **`abandoned`** is now a modeled terminal state; `completion_failed` → `abandoned` after the retention window, retry forbidden thereafter (§4.2, §12).
- **P2** Signature redraw takes **`base_signature_version`** (409 on mismatch) — last-write-wins removed (§5.2).
- **P2** **Token-entropy requirement restored:** all raw tokens are `secrets.token_urlsafe(32)` (load-bearing for unsalted hashes + bearer links) (§6).
- **P2** `/verify` throttling is **per token + IP** with reset-on-resend + staff unlock (per-packet-only attempts would let an attacker lock the real signer out) (§5.2).
- **P2** Resend of an expired/scrubbed packet **starts fresh** (new token, client re-enters); refused once `abandoned/revoked/completed` (§5.1).
- **P2** The Postgres lock-path integration test is **mandatory** (the "or compiled-SQL assertion" escape removed — SQLite can't prove `FOR UPDATE`) (§13).
- **P2** Completion/invite emails are linked via **`EmailQueue.entity_type='onboarding_packets'`** at row creation (durable on the queue side) and **resends are idempotent** (check for an existing non-failed row for that packet+purpose) — a lost ref can't cause duplicate sends (`queue_email` sends before the request commit) (§4.2, §9).
- **P3** "completed-incomplete" replaced with "stuck `completing` or `completion_failed`" (§5.2).

---

## 1. What Lorenzo asked for
Trigger on e-sign; tokenized link; fillable PDFs via the existing signature-embed system (labeled/described boxes burned in); one document at a time, edit before finishing; completed PDFs under the contact's **Attachments** tab; a **template library** (universal + per-service), **manually selected** per client. Named field kinds: **signature, date, text (EIN), address.** Initials/checkbox/radio/e-sign-ceremony/auto-trigger are deferred (`feedback_lorenzo_prefers_simple`).

## 2. One paragraph
Lorenzo builds an **Onboarding Template Library** once. He **selects templates and hits Send**; a branded email carries a **tokenized link**. The client **verifies their email**, walks each document **one at a time**, fills/draws boxes, **edits before finishing**, submits. On submit each doc is **stamped**, written as an **Attachment on the contact**, the client gets a **secure expiring link to a page listing their copies**, the owner is emailed, and a contact-timeline entry is written. Auto-send-on-e-sign is **Phase 3**; manual Send is the whole product.

## 3. Reuse vs net-new
Reusable: the pdf.js picker, coord contract + `_coords_for_stamper`, `proposal_signing_documents` + `_SignatureCoords`, public-page skeleton, SHA-256 view ledger, branded email/Gmail/auto-activity, `SignatureCanvas`, pdf.js CSP/MIME. **Net-new / gotchas:** only 2 field kinds; no client fill UI; stamper centers on one shared signature PNG, hard-raises if empty, **doesn't flatten AcroForms**; **public accept doesn't emit `PROPOSAL_ACCEPTED`** (only admin, `router.py:2000`); server PDFs never become Attachments + `upload_file` multipart-only; `ProposalTemplate` text-only; `ProposalSigningDocument` freezes when signed; **`get_download_url` R2-only (None for disk; JSON 503s disk, `router.py:121`) and its presign sets only Bucket/Key (`object_storage.py:62`)**; **`get_db` commits after the route returns (`database.py:81-86`)**; **`queue_email` can leave mail `throttled`/`retry`; `process_retries` only retries `retry`**; **`Proposal` has no onboarding field (`models.py:147`)**; **tests use in-memory SQLite (`conftest.py`)**.

---

## 4. Data model (4 tables + 1 join table, no Proposal additive column)

JSONB uses the `_SignatureCoords`-style TypeDecorator (no in-place mutation tracking — §4.3).

### 4.1 `onboarding_templates` (team library)
`id`; `name`; `description`; `service_tag` (nullable controlled slug; null=universal); `owner_id` (FK users SET NULL, indexed) + `created_by_id` (both on create; writes gated by `check_ownership`, `core/router_utils.py:131`); `pdf_path` (storage ref §4.8) + `pdf_version` (Int default 1 — **re-upload increments, writes a new versioned object, AND clears `field_definitions`**); `field_definitions` (JSONB, **validated at save** §7); `requires_esign` (default false); `is_active` (soft-retire); timestamps.

### 4.2 `onboarding_packets`
- `id`; `contact_id` (FK contacts, **NOT NULL**); `company_id`/`proposal_id` (nullable)
- `token_hash` (unique) — SHA-256 of the raw access token (§6); lookup-by-hash + constant-time compare; `token_expires_at` (+30 d).
- `download_token_hash` (nullable, unique) + `download_token_expires_at` (≈7 d) — minted at completion (§5.3).
- **`status` (lifecycle): `active → opened → in_progress → completing → completed`; plus `expired`, `revoked`, `completion_failed`, `abandoned`.** Link is live at `active` (set on commit), independent of email delivery. `opened` is set on the **first verified document view**.
- `completing_since` (nullable) — claim timestamp; stuck `completing` past a timeout (≈5 min) is reclaimable (§5.2).
- `recipient_email`, `recipient_name` — server-side only; **never echoed**.
- `signer_signature_image` (`LargeBinary`, nullable, ≤200 KB PNG) — drawn once, reused; **`signature_version` (Int, default 0)** bumped on each redraw.
- Signer-identity: `signer_ip`, `signer_user_agent`, `signer_timezone`, `completed_at`.
- **Email delivery linkage:** invite + the two completion notices are **rows in `EmailQueue` tagged `entity_type='onboarding_packets', entity_id=<id>`** (+ a `purpose` distinguishable via template/subject) — the link lives on the queue row, committed when the row is. Live delivery status (queued/retry/throttled/sent/failed) is read by querying those rows; resend is **idempotent** (skip if a non-failed row for that purpose exists). No packet email-ref columns (a lost ref can't cause dupes).
- `verify_attempts`/`verify_locked_until` are **not** packet columns — `/verify` throttling is per **token+IP** (§5.2).
- `created_by_id`, `queued_at`, `first_opened_at`, `revoked_at`, `revoked_by_id`, `abandoned_at`.

### 4.3 `onboarding_packet_documents`
`id`; `packet_id` (FK CASCADE); `display_order`; `source_template_id` (nullable); `original_filename`; `pdf_path` (**per-packet physical copy** §4.8); `field_definitions` (frozen copy); `field_values` (JSONB, mutable until claim — reassign whole dict / `flag_modified` / `MutableDict`); **`field_values_version`** (bumped per PATCH); `requires_esign` (copied) + **per-doc ESIGN evidence** (`esign_disclosure_snapshot`, `esign_disclosure_version`, `consented_at`); **`stamp_lease_at`** (nullable — Phase-B atomic lease, §5.2); `attachment_id` (nullable FK — completion fence); `filled_pdf_error`; `completed_at`.

### 4.4 Field-definition schema
```jsonc
{ "id":"f_ein",            // unique within doc, slug-safe (422 on collision)
  "kind":"text",           // v1: signature | date | text | address
  "label":"Federal EIN","description":"...","required":true,
  "prefill":null,          // "contact.name"|"company.name" only; post-gate; "contact.email" disallowed
  "page":1,"x":72,"y":144,"w":180,"h":24 }   // PDF points, bottom-left; in-bounds-validated at save
```
`signature` holds no value (refs packet signature). `date`: ISO `YYYY-MM-DD`, reformatted `%m-%d-%Y` at stamp, no tz. Deferred (Q-Forms, not free): initials, checkbox, radio/select(`options[]`), conditional, validation/pattern.

### 4.5 Completed PDFs on the contact
`category='onboarding'`, `entityType='contacts'`. Shows in **both** the Attachments tab (`AttachmentList`, correct `?as_json` download) and the Documents "All" view. The Documents-tab download is a pre-existing blob-path bug (`DocumentsTab.tsx:128`); Lorenzo's Attachments tab works. Client delivery is via §5.3, not these tabs.

### 4.6 `onboarding_packet_document_views`
Clone of `ProposalSigningDocumentView`: `id`, `packet_document_id` (FK CASCADE), `token_hash` (String 64), `viewed_at`, `ip_address`, `user_agent`; `UniqueConstraint(packet_document_id, token_hash)`; SAVEPOINT-idempotent. **Gates completion.** Rows written **only after** byte deliverability confirmed (§5.2).

### 4.7 `proposal_onboarding_selections` (join table, Phase 3)
`id` PK; `proposal_id` (FK CASCADE); `template_id` (FK); `display_order`; `UniqueConstraint(proposal_id, template_id)` + `UniqueConstraint(proposal_id, display_order)`. Per proposal = per bundle option (winner). Trigger skips `is_active=false`.

### 4.8 Storage abstraction (full)
One module: **write / read-bytes / serve (proxy bytes; R2 via `download_object_bytes`, disk via file read) / delete / exists**, chosen by `_use_object_storage()` (`upload_file_bytes` is R2-only and raises without creds, `object_storage.py:114`). Used by template upload/preview, per-packet copy, public PDF streaming, stamping source reads, `create_from_bytes` (§10), and the §5.3 download. Keeps disk/dev working everywhere.

### Migration
`049_onboarding.py`, `down_revision='048_proposal_acceptance_evidence'`, id ≤32 chars, `alembic heads` before merge.

---

## 5. Backend endpoints

### 5.1 Staff (authenticated)
Team library: `list` global, writes `check_ownership`. **Packet routes call `require_entity_access`/data-scope on `contact_id`** (`entity_access.py:119`).
- Templates: `POST …/templates` + `…/{id}/pdf` ; `GET …/templates` / `…/{id}` ; `PATCH …/templates/{id}` ; `GET …/templates/{id}/pdf` ; `POST …/templates/{id}/retire`
- Packets: `POST …/packets` (refuse if no contact; access-checked) ; `GET …/packets?contact_id=` ; `GET …/packets/{id}`
- **Resend/revoke rules:** `resend` allowed for `active|opened|in_progress|expired` → mints a **fresh** access token, resets expiry, queues a new invite; if the packet was scrubbed (expired), it **starts fresh** (client re-enters — templates are blank). **Refused for `completed|revoked|completing|abandoned`** (for `completion_failed` use retry-completion). `revoke` allowed for any non-terminal → `revoked` (clears both tokens).
- `POST …/packets/{id}/retry-completion` — for `completion_failed` or stuck `completing` past timeout; per-doc idempotent. **Refused once `abandoned`** (staff create a new packet).
- `POST …/packets/{id}/resend-completion-notice` — idempotent re-send of the client link and/or owner email.
- `POST …/packets/{id}/purge-pii` + bulk stale-sweep — nulls `field_values` + `signer_signature_image` (§12).

### 5.2 Public (token only, rate-limited)
Onboarding client sends the **session token in `X-Onboarding-Session`** (added to `main.py` `allow_headers`). **No cookies.**

**Email gate + session.** `POST …/public/{token}/verify` `{email}` → constant-time match vs `recipient_email`. **Throttle per token+IP** (e.g. backoff after 5 wrong/IP; a high per-token ceiling so one attacker can't trivially lock the real signer; **reset on a successful verify or on staff resend**; staff unlock = resend/revoke). Always return a **generic** result. On success → a short-lived signed **bearer session token** (HMAC over `{packet_id, token_hash, signer_email, exp}`, ~30–60 min; nonce from `secrets.token_urlsafe(32)`), held in memory, sent in `X-Onboarding-Session`. **Document routes are packet-scoped** (`doc.packet_id == session.packet_id`).

- `GET …/public/{token}` — **pre-gate:** branding + "N documents" + email prompt only. **Post-gate (valid session):** field definitions + `field_values` (+ versions) + resolved `prefill`. For `completed`, the pre-gate returns **"completed — check your email"** only; the §5.3 landing link is returned **only post-gate** (or via the email) so the access token alone can't fetch PII after completion.
- `POST …/public/{token}/verify` — as above.
- `GET …/documents/{doc_id}/pdf` — (session) confirm the source object **exists/streams first, then** record the view row (`proposals/router.py:1100` pattern). First view sets `opened`/`first_opened_at` (transition from `active`).
- `PATCH …/documents/{doc_id}` — (session) `{field_values:{id:val}, base_version}`; merge per id; **409 if `base_version != field_values_version`**; bump version. Allowed only while `status IN ('active','opened','in_progress')`.
- `POST …/public/{token}/signature` — (session) set/redraw; payload `{ base_signature_version }`; **409 on mismatch**; bumps `signature_version`. Allowed only while `status IN ('active','opened','in_progress')`.
- `POST …/complete` — (session) **3-phase, no transaction held across I/O:**
  - **Phase A (short txn, row lock):** `SELECT … FOR UPDATE` packet (+docs); validate signer, **every document viewed** (§4.6), all `required` filled, **every value fits its box** (else **422, no truncation**, status unchanged); **claim:** `UPDATE … SET status='completing', completing_since=now() WHERE status IN ('active','opened','in_progress') AND signature_version=:sv AND <each doc field_values_version unchanged>`; `rowcount==0` → 409; **commit** (lock released). PATCH/signature now rejected (status `completing`), so values are frozen.
  - **Phase B (no lock, atomic per-doc):** for each doc, **atomically lease**: `UPDATE packet_documents SET stamp_lease_at=now() WHERE id=:doc AND attachment_id IS NULL AND (stamp_lease_at IS NULL OR stamp_lease_at < now()-lease_timeout) RETURNING id`; only a returned row stamps. Stamp → `create_from_bytes` → set `attachment_id` via `UPDATE … SET attachment_id=:a WHERE id=:doc AND attachment_id IS NULL`; **if 0 rows (a concurrent reclaim won), delete the orphan object just written.** Infra error → short txn sets `completion_failed`; stop.
  - **Phase C (short txn):** when all docs have `attachment_id` → `status='completed'`, `completed_at`, mint `download_token`; commit. **Then** (post-commit) send owner email + client link (idempotent, §9).
  - **Reclaim:** `retry-completion` (staff/lazy) re-runs Phase B/C for a packet stuck `completing` or `completion_failed` — safe via the lease + `attachment_id` fence.

**Body cap:** reject **missing/over `Content-Length`** AND stream-count before parsing; field-count cap; 200 KB+PNG-magic per signature; 2–4 KB per text/address.

**Status × public-route matrix:**

| status | GET pre-gate | verify | pdf/PATCH/signature | complete |
|---|---|---|---|---|
| active / opened / in_progress | OK | OK | OK (session) | OK (session) |
| completing | read-only | — | 409 | 409 (in progress) |
| completed | "completed — check your email" (link only post-gate) | — | 409 | 409 idempotent |
| completion_failed | "we're finishing" | OK | 409 | staff retry only |
| abandoned | 410 (data purged; staff must re-send) | 410 | 410 | 410 |
| expired / revoked | 410 | 410 | 410 | 410 |

*(Invite-email delivery state lives on the linked `EmailQueue` rows, shown to staff; it never appears here.)*

### 5.3 Completion download (no login) — proxied, not redirected
- `GET /api/onboarding/download/{download_token}` — landing/list: look up by `download_token_hash` + expiry; return completed-doc titles + per-doc sub-URLs. The single link the email/success screen uses.
- `GET /api/onboarding/download/{download_token}/documents/{doc_id}` — assert the doc belongs to the packet and is `completed`; **proxy the bytes** through this route via §4.8 (R2 `download_object_bytes` or disk read) — **not** a redirect to a presigned URL, because the R2 presign can't set response headers (`object_storage.py:62`) and a redirect would leak the token via `Referer`.
- Both responses set **`Cache-Control: no-store`**, **`Referrer-Policy: no-referrer`**, `Content-Type: application/pdf`, `Content-Disposition`. Rate-limited. Revoking the packet clears `download_token_hash`. (Trade-off: proxying uses app bandwidth — fine for onboarding-sized PDFs; the alternative is presign with `ResponseCacheControl`/`ResponseContentDisposition` overrides, R2-only.)

## 6. Token security
All raw tokens — **access, download, and the verify-session nonce — are `secrets.token_urlsafe(32)`** (high-entropy; load-bearing for unsalted SHA-256 + bearer use). `token_hash`/`download_token_hash` = SHA-256(raw); raw never persisted; lookup by hash + constant-time compare; expiry on all routes. **Raw token never logged** (app/proxy/exception logs redact/hash the path); §5.3 proxying + `Referrer-Policy: no-referrer` covers the browser side.

## 7. PDF stamping
New entry point `stamp_document(source_pdf, fields, signature_png=None)`; conditional empty-signature guard. Generalize date overlay → `_build_text_overlay` (text/date single-line; address multi-line capped; signature image from packet). **Fail closed on overflow:** raise → `completion_failed` (never silently truncate; user-fixable overflow already 422'd at §5.2 Phase A). **Coordinate validation at template save** (§4.1). **Flatten precisely:** drop `/AcroForm` + only `/Subtype /Widget` annotations (not all `/Annots`); test asserts no `/Widget`/`/AcroForm`. Coords via `_coords_for_stamper`; bottom-left y-flip; optional unfilled skip; date reformat. Helvetica/Courier/Times only (non-Latin → TTF; defer/flag). On `asyncio.to_thread`. No-mock tests per kind + no-sig + overflow-raises + no-`/Widget`/`/AcroForm`.

## 8. Frontend
- **Extract** `pdfCoordsToBox`/`boxToPdfCoords`/`RENDER_SCALE` from `SignatureFieldPicker.tsx` into a shared module (today local; `PlacementKind`=`signature|date`); widen kinds.
- Template editor (picker + per-box editor, type-aware `canSave`); library page; selection+send UI (→ join table, per option).
- **Public fill page (`/onboarding/:token`):** clone the skeleton **but** (a) send the session token in `X-Onboarding-Session` (no cookie), (b) **no token in `canonicalUrl`/OG**, (c) `referrerPolicy="no-referrer"` on branding/external assets + `Referrer-Policy: no-referrer`. Flow: email-gate → step-through one doc at a time → pdf.js canvas + editable inputs (shared coord util; signature drawn once, reused, with `base_signature_version`) → save draft with `base_version` → required + viewed validation before Submit → success screen (poll) + download link. Mobile overlay = trickiest piece (Playwright/manual, Phase 2). Errors per the §5.2 matrix.

## 9. Trigger (auto-send on e-sign) — Phase 3
**Inline in BOTH accept paths, not the event bus** (public accept doesn't emit `PROPOSAL_ACCEPTED`; admin does, `router.py:2000`; `events.emit` swallows handler errors). Factor `create_packet_and_send(proposal)`, inline in both, each `try/except`+`logger.exception` (never raise — public accept is wrapped in `value_error_as_400`).
- **Transaction ordering:** `get_db` commits after the route returns (`database.py:81-86`). **Commit the packet (+ token) before queuing any email**, then send — never inside an uncommitted txn (rollback → dead link). Packet is `active` immediately after that commit.
- **Contact rule:** fire only with a linked contact; otherwise **no packet** + a **durable proposal `Activity` row** recording the onboarding-trigger failure (the `Proposal` model has no flag field, `models.py:147`; an Activity is durable and queryable, unlike a best-effort notification that can silently fail).
- **Invite delivery decoupled:** `queue_email` may return `pending`/`throttled`/`retry` (`process_retries` only retries `retry` — throttled isn't auto-retried). The packet carries **no** `invite_failed`/`sent_at` lifecycle state; the invite is an `EmailQueue` row tagged `entity_type='onboarding_packets'` (purpose=invite). Staff see live delivery status; the link works regardless. Resend is idempotent.
- **Completion delivery:** secure expiring **link** to §5.3 (not emailed PII attachments — `EmailQueue` has no attachments column, verified; emailing EIN/W-9 is a PII risk). Two notices (client link, owner email) are separate tagged `EmailQueue` rows; **resend checks for an existing non-failed row** for that purpose so a lost ref / mid-send crash can't cause duplicate sends.
- **Owner notification (decided):** always-on email to the owner (bypasses the fail-closed matrix, like the signer copy).

## 10. Completion → contact Attachments
`AttachmentService.create_from_bytes(...)` — **owns the single write** via §4.8 (disk fallback), returns the Attachment; replicates `upload_file` defense-in-depth; **25 MB cap, not the 10 MB `MAX_UPLOAD_SIZE`**; accepts `uploaded_by=NULL`/system. Called inside Phase B with the lease + conditional-`attachment_id` fence (§5.2). Delivery via §5.3. Timeline `Activity(entity_type='contacts')` for sent/opened/completed.

## 11. ESIGN — opt-in, per-document
Signer-identity match always on. Ceremony opt-in per template (`requires_esign`); evidence per document (§4.3); certificate page only on signature-bearing docs. **Don't reuse `proposal_esign_disclosure`** ("the proposal above" — wrong for W-9); author an onboarding-specific disclosure SSOT + version, reviewed by Lorenzo/counsel.

## 12. PII
Never log `field_values`/raw token (§6). **Scrub `field_values` + `signer_signature_image`** on all terminal/dead states: `/complete` (after the filled PDF is confirmed), `revoke`, lazy `expired`, staff purge, **and `completion_failed` → `abandoned` after a retention window** (e.g. 7 d): the packet is scrubbed + marked `abandoned` (retry forbidden thereafter; staff create a new packet). **Limitation:** a packet nobody reopens won't lazily expire-scrub — a scheduled job is the only complete fix and **needs explicit permission** (interim: staff purge + a list-time sweep). Read-gate values behind the session. Certificate only on signature docs.

## 13. Naming, wiring, tests
- `backend/src/onboarding/`, `frontend/src/features/onboarding/`, `049_onboarding.py`, branch `onboarding/features`.
- **Wiring:** `include_router(onboarding_router)` in `main.py`; add `X-Onboarding-Session` to CORS `allow_headers`; import onboarding models in `tests/conftest.py`; Alembic env imports the models.
- **Tests (no-mock, ≥1/endpoint/method) — ≈30–40 backend + 1 MANDATORY Postgres integration:** template CRUD + coord-bounds 422 + re-upload-clears; packet create/list access-checked; verify gate (valid/wrong/**token+IP lockout**/expired session); packet-scoped doc access; lost-update `base_version` & `base_signature_version` 409; **per-doc lease prevents double-attach** (the orphan-cleanup path); require-viewed gate; overflow **rejected (not truncated)**; each terminal state incl. **`abandoned`**; abuse caps; duplicate field-id 422; `field_values` mutation round-trip; stamper per kind + no-sig + overflow-raises + no-`/Widget`/`/AcroForm`; `create_from_bytes` with disk fallback; §5.3 download **proxies** R2 **and** disk + sets `Cache-Control`/`Referrer-Policy`; expiry/revoke/`completion_failed`-SLA scrub (values + signature); resend-after-scrub starts fresh; idempotent completion-notice resend. **Concurrency/`FOR UPDATE`:** SQLite (`conftest.py`) can't prove row locks — a **Postgres integration test for the claim/lease path is mandatory** (no compiled-SQL substitute). **No-mock Gmail:** assert `EmailQueue` row + status, never a live send. Mobile overlay → Playwright/manual.
- Trio before each merge. KISS. No stray MD files. Ask before any new service (only candidate: the scrub cron, §12).

## 14. Effort & phasing
**Phase 1 (~2.5–3 wk):** field model + coord validation + shared coord util + picker-as-editor + per-field stamper (multi-line, overflow-raise, widget-flatten) + `onboarding_templates` + team CRUD + storage abstraction; no-mock tests. *(+3–5 d if Q-Forms has radio/checkbox.)*
**Phase 2 (~3.5–4.5 wk):** packets + docs (+per-packet copy, per-doc ESIGN, signature+version, view ledger, lease) ; email-gate + step-through fill page (~1.5 wk) ; bearer session + token+IP throttle ; 3-phase `/complete` (require-viewed, no-truncation, atomic lease, reclaim) ; `create_from_bytes` + §5.3 proxied landing+download ; contact Attachment ; abuse caps ; owner email + completion link + timeline + **mandatory Postgres lock test**. *Shippable.*
**Phase 3 (~1–1.5 wk):** join table, invite email (commit-before-send), `create_packet_and_send` inline in both accept paths, EmailQueue-tagged delivery + idempotent resend, no-contact durable Activity, resend/revoke.

**Total ≈7–9 wk all; ≈6–7.5 wk for Phases 1+2 (manual send).** + ~1 day trio/phase. **Ship 1+2 first.**

## 15. Confirmed from the meeting
Manual select → Send (auto later); Universal + per-service; lands in the Attachments tab (`AttachmentList`, no FE change); edit-until-submit.

## 16. Decisions & open questions
**Decided defaults (confirm only if you disagree):** signature drawn once + reused; not "complete" until the PDF generates (staff re-run on infra failure); completion delivery = secure expiring link (not attachments); every document must be viewed before completion; ESIGN ceremony default OFF (per-template opt-in); owner notice always-on; `contact_id` NOT NULL; `completion_failed` → `abandoned` + scrub after ~7 d.

**Genuinely open:**
- **Q-Forms (highest):** AcroForm vs scan? field count + radio/checkbox/tables? prefill name/company?
- **Q-Expiry:** 30-day access link / 7-day download link, resendable? Confirm or pick.
- *(Internal: Q-OfflineAccept, Q-Clone, scrub-cron permission §12.)*

---

*Ready for Phase 1 once Q-Forms is answered. Docs-only plan retired.*
