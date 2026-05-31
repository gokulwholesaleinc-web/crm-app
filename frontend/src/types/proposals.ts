/**
 * Proposal Types
 */

import type { PaginatedResponse } from './common';

export type PaymentType = 'one_time' | 'subscription';
export type RecurringInterval = 'month' | 'year';

/** Saved placement of the signer's signature box on the master contract PDF.
 *  Coordinates are PDF points with origin = bottom-left of the page;
 *  ``page`` is 1-indexed. The backend converts to 0-indexed for the
 *  stamper. NULL on the proposal falls back to the auto-box (bottom of
 *  the last page) at sign time. */
export interface SignatureFieldCoords {
  page: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

export type SignatureFieldCoordsValue =
  | SignatureFieldCoords
  | SignatureFieldCoords[];

export interface ProposalSigningDocument {
  id: number;
  proposal_id: number;
  original_filename: string;
  file_size: number;
  content_type: string;
  /** Legacy rows may contain one box; multi-placement rows use array order
   * as stamping order. */
  signature_field_coords?: SignatureFieldCoordsValue | null;
  date_field_coords?: SignatureFieldCoordsValue | null;
  signed_pdf_path?: string | null;
  signed_pdf_error?: string | null;
  display_order: number;
  created_at: string;
  updated_at: string;
}

export interface ProposalLegacyBillingFields {
  payment_type: PaymentType;
  /** Stripe-native unit. 'month' + count=3 = quarterly, count=6 = bi-yearly. */
  recurring_interval?: RecurringInterval | null;
  recurring_interval_count?: number | null;
  amount?: string | number | null;
  currency: string;
}

export interface ProposalBase {
  title: string;
  content?: string | null;
  contact_id?: number | null;
  company_id?: number | null;
  quote_id?: number | null;
  status?: string;
  cover_letter?: string | null;
  executive_summary?: string | null;
  scope_of_work?: string | null;
  pricing_section?: string | null;
  timeline?: string | null;
  terms?: string | null;
  valid_until?: string | null;
  /** Optional override for who is authorized to sign via the public link.
   * When unset, the linked contact's email is used. */
  designated_signer_email?: string | null;
  owner_id?: number | null;
  /** Saved signature-box placement on the master contract. NULL =
   * stamper falls back to the auto-box on the last page. Legacy rows may
   * contain one box; new saves contain a list. */
  signature_field_coords?: SignatureFieldCoordsValue | null;
  /** Saved date placement on the master contract. The signer date is
   * stamped in MM-DD-YYYY using the signer's local timezone. */
  date_field_coords?: SignatureFieldCoordsValue | null;
}

export interface ProposalCreate extends ProposalBase {}

export interface ProposalUpdate {
  title?: string;
  content?: string | null;
  contact_id?: number | null;
  company_id?: number | null;
  quote_id?: number | null;
  cover_letter?: string | null;
  executive_summary?: string | null;
  scope_of_work?: string | null;
  pricing_section?: string | null;
  timeline?: string | null;
  terms?: string | null;
  valid_until?: string | null;
  designated_signer_email?: string | null;
  owner_id?: number | null;
  /** Visual signature-box placement on the master contract. Pass an
   * object/list to set, ``null`` to clear back to the auto-box default. */
  signature_field_coords?: SignatureFieldCoordsValue | null;
  /** Visual date placement on the master contract. Pass an object to set,
   * ``null`` to clear. */
  date_field_coords?: SignatureFieldCoordsValue | null;
}

export interface ProposalView {
  id: number;
  proposal_id: number;
  viewed_at: string;
  ip_address?: string | null;
  user_agent?: string | null;
}

export interface ProposalBundleBrief {
  id: number;
  bundle_number: string;
  public_token?: string | null;
  title: string;
  description?: string | null;
  status: string;
  selected_proposal_id?: number | null;
  selected_at?: string | null;
  sent_at?: string | null;
  accepted_at?: string | null;
  contact?: { id: number; full_name: string; email?: string | null } | null;
  company?: { id: number; name: string } | null;
  // Number of options in the bundle — exposed by the brief so the list
  // page can render the "N options" badge without loading every sibling.
  proposals_count?: number;
}

export interface ProposalBundle extends ProposalBundleBrief {
  proposals: Proposal[];
  created_at: string;
  updated_at: string;
  created_by?: { id: number; full_name: string; email?: string | null } | null;
  owner?: { id: number; full_name: string; email?: string | null } | null;
}

export interface ProposalBundleCreate {
  title: string;
  description?: string | null;
  proposal_ids: number[];
}

export interface ProposalBundleUpdate {
  title?: string | null;
  description?: string | null;
  proposal_ids?: number[] | null;
  // `null` is meaningful here — it clears every option's "Recommended"
  // badge. Omit the field entirely to leave the recommendation untouched.
  // (Set `extractApiErrorDetail` consumers expect the wire shape to allow
  // explicit null, not undefined-only.)
  recommended_proposal_id?: number | null;
}

export interface Proposal extends ProposalBase, ProposalLegacyBillingFields {
  id: number;
  proposal_number: string;
  /** Unguessable token used for the public /accept link. Nullable only
   * for pre-migration rows; all new proposals get one on create. */
  public_token?: string | null;
  view_count: number;
  last_viewed_at?: string | null;
  sent_at?: string | null;
  viewed_at?: string | null;
  accepted_at?: string | null;
  rejected_at?: string | null;
  signer_name?: string | null;
  signer_email?: string | null;
  signer_ip?: string | null;
  signer_user_agent?: string | null;
  signed_at?: string | null;
  /** Durable ESIGN acceptance evidence captured at sign-to-confirm. */
  agreed_to_terms_at?: string | null;
  terms_and_conditions_snapshot?: string | null;
  esign_disclosure_snapshot?: string | null;
  esign_disclosure_version?: string | null;
  acceptance_method?: string | null;
  rejection_reason?: string | null;
  stripe_invoice_id?: string | null;
  stripe_subscription_id?: string | null;
  stripe_checkout_session_id?: string | null;
  stripe_payment_url?: string | null;
  invoice_sent_at?: string | null;
  paid_at?: string | null;
  billing_error?: string | null;
  /** R2 key of the optional master service agreement PDF. */
  master_contract_pdf_path?: string | null;
  /** R2 key of the stamped + audit-appended signed PDF. */
  signed_pdf_path?: string | null;
  /** Most-recent stamp/upload failure. Drives the re-stamp banner on /proposals/:id. */
  signed_pdf_error?: string | null;
  /** PDFs that require explicit signature/date placement before send. */
  signing_documents?: ProposalSigningDocument[];
  proposal_bundle_id?: number | null;
  bundle_sort_order?: number;
  bundle_is_recommended?: boolean;
  bundle?: ProposalBundleBrief | null;
  /** Per-view audit log. Populated on every public-link GET. */
  views?: ProposalView[];
  created_at: string;
  updated_at: string;
  contact?: { id: number; full_name: string; email?: string | null } | null;
  company?: { id: number; name: string } | null;
  // ``quote`` relation removed 2026-05-14 — quotes feature retired.
  // ``quote_id`` column still present on the proposal for legacy lookups.
  /** User who clicked "Create Proposal". Immutable. Rendered in admin list+detail. */
  created_by?: { id: number; full_name: string; email?: string | null } | null;
  /** User the proposal is currently assigned to. Defaults to created_by but can be reassigned. */
  owner?: { id: number; full_name: string; email?: string | null } | null;
}

export type ProposalListResponse = PaginatedResponse<Proposal>;

export interface ProposalFilters {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  contact_id?: number;
  company_id?: number;
  quote_id?: number;
  order_by?: string;
  order_dir?: 'asc' | 'desc';
  // Default backend behavior hides bundle sub-options (sort_order > 0)
  // from /proposals so a bundle parent surfaces as one row. Admin tools
  // that need to find/share individual sub-options pass `true` to flip
  // the filter off.
  include_bundle_options?: boolean;
}

export interface ProposalTemplate {
  id: number;
  name: string;
  description?: string | null;
  body: string;
  legal_terms?: string | null;
  category?: string | null;
  is_default: boolean;
  owner_id?: number | null;
  created_at: string;
  updated_at: string;
}

export interface ProposalTemplateCreate {
  name: string;
  body: string;
  description?: string | null;
  legal_terms?: string | null;
  category?: string | null;
  is_default?: boolean;
}

export interface ProposalTemplateUpdate {
  name?: string | null;
  body?: string | null;
  description?: string | null;
  legal_terms?: string | null;
  category?: string | null;
  is_default?: boolean | null;
}

export interface CreateFromTemplateRequest {
  template_id: number;
  contact_id: number;
  company_id?: number | null;
  custom_variables?: Record<string, string>;
}

export interface ProposalAttachment {
  id: number;
  original_filename: string;
  file_size: number;
  content_type?: string | null;
  created_at?: string | null;
}

export interface ProposalAttachmentPublic {
  id: number;
  filename: string;
  original_filename?: string;
  file_size: number;
  viewed: boolean;
}
