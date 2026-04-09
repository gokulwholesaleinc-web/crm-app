/**
 * Proposal Types
 */

import type { PaginatedResponse } from './common';

export interface ProposalBase {
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
  status?: string;
  cover_letter?: string | null;
  executive_summary?: string | null;
  scope_of_work?: string | null;
  pricing_section?: string | null;
  timeline?: string | null;
  terms?: string | null;
  valid_until?: string | null;
  owner_id?: number | null;
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
  created_at: string;
  updated_at: string;
  contact?: { id: number; full_name: string } | null;
  company?: { id: number; name: string } | null;
  opportunity?: { id: number; name: string } | null;
  quote?: { id: number; quote_number: string; title: string; total: number } | null;
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
