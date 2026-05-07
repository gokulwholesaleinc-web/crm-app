/**
 * Proposal Types
 */

import type { PaginatedResponse } from './common';

export type PaymentType = 'one_time' | 'subscription';
export type RecurringInterval = 'month' | 'year';

export interface ProposalBillingFields {
  payment_type: PaymentType;
  /** Stripe-native unit. 'month' + count=3 = quarterly, count=6 = bi-yearly. */
  recurring_interval?: RecurringInterval | null;
  recurring_interval_count?: number | null;
  amount?: string | number | null;
  currency: string;
}

export interface ProposalBase extends ProposalBillingFields {
  title: string;
  content?: string | null;
  opportunity_id?: number | null;
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
}

export interface ProposalCreate extends ProposalBase {}

export interface ProposalUpdate {
  title?: string;
  content?: string | null;
  opportunity_id?: number | null;
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
  payment_type?: PaymentType;
  recurring_interval?: RecurringInterval | null;
  recurring_interval_count?: number | null;
  amount?: string | number | null;
  currency?: string;
}

export interface ProposalView {
  id: number;
  proposal_id: number;
  viewed_at: string;
  ip_address?: string | null;
  user_agent?: string | null;
}

export interface Proposal extends ProposalBase {
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
  rejection_reason?: string | null;
  stripe_invoice_id?: string | null;
  stripe_subscription_id?: string | null;
  stripe_checkout_session_id?: string | null;
  stripe_payment_url?: string | null;
  invoice_sent_at?: string | null;
  paid_at?: string | null;
  billing_error?: string | null;
  /** Per-view audit log. Populated on every public-link GET. */
  views?: ProposalView[];
  created_at: string;
  updated_at: string;
  contact?: { id: number; full_name: string; email?: string | null } | null;
  company?: { id: number; name: string } | null;
  opportunity?: { id: number; name: string } | null;
  quote?: { id: number; quote_number: string; title: string; total: number } | null;
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
  opportunity_id?: number;
  contact_id?: number;
  company_id?: number;
  quote_id?: number;
  order_by?: string;
  order_dir?: 'asc' | 'desc';
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

export interface AIGenerateProposalRequest {
  opportunity_id: number;
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
  original_filename: string;
  file_size: number;
  viewed: boolean;
}
