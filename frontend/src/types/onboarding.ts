/**
 * Client Onboarding Types (Phase 1)
 *
 * Mirrors the backend ``onboarding`` module's wire contract (see
 * CLIENT_ONBOARDING_PLAN.md §4.4 and the build-order note §B/§C). Phase 1
 * surfaces the team template library + the field-placement editor only;
 * the public client-fill flow is Phase 2.
 */

/**
 * The four placeable field kinds. This type is onboarding-specific and
 * intentionally wider than the proposals picker's narrow
 * ``'signature' | 'date'`` — keeping them separate stops the proposals UI
 * from ever offering text/address.
 */
export type OnboardingFieldKind = 'signature' | 'date' | 'text' | 'address';

/**
 * Optional auto-fill source for a field's value. Resolution is Phase 2;
 * Phase 1 only stores the choice. ``contact.email`` is intentionally
 * disallowed (§4.4).
 */
export type OnboardingFieldPrefill = 'contact.name' | 'company.name' | null;

/**
 * A single field placed on the template PDF. Coordinates are PDF points
 * with origin = bottom-left of the page; ``page`` is 1-indexed (the
 * backend converts to 0-indexed for the stamper). ``id`` is unique within
 * the document and slug-safe (``^[a-z0-9_]+$``).
 */
export interface OnboardingFieldDefinition {
  id: string;
  kind: OnboardingFieldKind;
  label: string;
  description?: string | null;
  required: boolean;
  prefill: OnboardingFieldPrefill;
  page: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** A team-library onboarding template row. */
export interface OnboardingTemplate {
  id: number;
  name: string;
  description?: string | null;
  /** null = universal template; a service slug scopes it to one service. */
  service_tag?: string | null;
  owner_id?: number | null;
  /**
   * Whether a PDF has been uploaded. The backend deliberately does NOT
   * expose the raw storage path (it would leak the R2 key); it sends this
   * computed boolean instead. Drives upload-vs-replace and whether fields
   * can be edited.
   */
  has_pdf: boolean;
  pdf_version: number;
  field_definitions: OnboardingFieldDefinition[];
  requires_esign: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OnboardingTemplateCreate {
  name: string;
  description?: string | null;
  service_tag?: string | null;
  requires_esign?: boolean;
}

export interface OnboardingTemplateUpdate {
  name?: string | null;
  description?: string | null;
  service_tag?: string | null;
  requires_esign?: boolean | null;
  /** Reassigns the whole list; rejected (422) until a PDF is uploaded. */
  field_definitions?: OnboardingFieldDefinition[] | null;
  /**
   * Optimistic-lock token sent alongside ``field_definitions``. The editor
   * captures the template's ``pdf_version`` when opened; if the PDF was
   * replaced (version bumped) before the field-save lands, the backend
   * rejects with 409 so stale coordinates can't overwrite the new layout.
   */
  pdf_version?: number | null;
}

export interface OnboardingTemplateFilters {
  service_tag?: string;
  include_inactive?: boolean;
}

// ---------------------------------------------------------------------------
// Phase 2 — packets (staff select-and-send + public client-fill flow)
// ---------------------------------------------------------------------------

/**
 * Packet lifecycle status (build-order note §2). ``active``/``opened``/
 * ``in_progress`` are all writable; the rest are read-only or terminal.
 */
export type OnboardingPacketStatus =
  | 'active'
  | 'opened'
  | 'in_progress'
  | 'completing'
  | 'completed'
  | 'expired'
  | 'revoked'
  | 'completion_failed'
  | 'abandoned';

/**
 * Delivery state of a notice/invite email linked to a packet — surfaced to
 * staff only, never on the public matrix (note §2). Mirrors EmailQueue.status.
 */
export type OnboardingPacketDelivery =
  | 'pending'
  | 'sent'
  | 'failed'
  | 'retry'
  | 'throttled';

/** A queued email tagged to a packet (completion notice / owner email). */
export interface OnboardingPacketEmail {
  id: number;
  subject: string;
  status: OnboardingPacketDelivery;
  to_email: string;
  created_at: string;
}

/** Per-document summary in the staff packet detail view (NO field values). */
export interface OnboardingPacketDocumentSummary {
  id: number;
  original_filename: string;
  display_order: number;
  requires_esign: boolean;
  status: string;
  completed_at?: string | null;
}

/**
 * Staff-facing packet row. Carries NO raw token and NO field values; the
 * one-time ``access_url`` is present ONLY on the create (POST /packets)
 * response (note §8) — never re-served by GET.
 */
export interface OnboardingPacket {
  id: number;
  contact_id: number;
  company_id?: number | null;
  status: OnboardingPacketStatus;
  recipient_email_masked?: string | null;
  recipient_name?: string | null;
  document_count: number;
  created_at: string;
  token_expires_at: string;
  completed_at?: string | null;
  first_opened_at?: string | null;
  /** Present only on the POST /packets 201 response — show once, copy, drop. */
  access_url?: string | null;
  emails?: OnboardingPacketEmail[];
}

export interface OnboardingPacketDetail extends OnboardingPacket {
  documents: OnboardingPacketDocumentSummary[];
}

export interface OnboardingPacketCreate {
  contact_id: number;
  recipient_email: string;
  recipient_name?: string | null;
  company_id?: number | null;
  template_ids: number[];
}

// ---------------------------------------------------------------------------
// Phase 3 — proposal → onboarding-template selections (staff curation)
// ---------------------------------------------------------------------------

/**
 * One proposal→onboarding-template selection row (staff view). The ordered
 * list of these drives Phase-3 auto-send: on admin-accept the proposal's
 * selected templates become the packet's documents, in ``display_order``.
 */
export interface OnboardingProposalSelection {
  id: number;
  proposal_id: number;
  template_id: number;
  display_order: number;
}

/** Replace the whole ordered selection list for a proposal. */
export interface OnboardingSelectionSet {
  template_ids: number[];
}

/** Reorder the selections by a permutation of their selection ids. */
export interface OnboardingSelectionReorder {
  ordered_ids: number[];
}

// --- Public client-fill flow (bare axios client, X-Onboarding-Session) ---

export interface OnboardingPublicBranding {
  company_name: string | null;
  logo_url: string | null;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  bg_color_light: string;
  surface_color_light: string;
  footer_text: string | null;
  privacy_policy_url: string | null;
  terms_of_service_url: string | null;
}

/** A document the client steps through and fills on the public page. */
export interface OnboardingPublicDocument {
  id: number;
  original_filename: string;
  field_definitions: OnboardingFieldDefinition[];
  /** Saved values keyed by field id. Reassigned whole on each PATCH (§4.3). */
  field_values: Record<string, string>;
  field_values_version: number;
  requires_esign: boolean;
}

/** A completed document download entry returned by the §5.3 landing endpoint. */
export interface OnboardingDownloadDocument {
  doc_id: number;
  title: string;
  url: string;
}

/**
 * The public packet payload. Pre-gate (no valid session) carries only
 * branding + counts + a status message; post-gate (valid session) adds the
 * documents, signature version, disclosure, and (when completed) downloads.
 */
export interface OnboardingPublicPacket {
  status: OnboardingPacketStatus;
  branding: OnboardingPublicBranding | null;
  document_count: number;
  requires_email_verification: boolean;
  status_message?: string | null;
  // Post-gate only:
  documents?: OnboardingPublicDocument[];
  signature_version?: number;
  esign_disclosure?: string | null;
  esign_disclosure_version?: string | null;
  has_signature?: boolean;
  /** True once every e-sign doc has recorded electronic-records consent. */
  has_consented?: boolean;
  downloads?: OnboardingDownloadDocument[];
}
