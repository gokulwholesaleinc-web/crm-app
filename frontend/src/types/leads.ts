/**
 * Lead Types
 */

import type { PaginatedResponse, TagBrief } from './common';

// Shared Pipeline Stage types. The `PipelineStage` model is shared between
// the lead pipeline and the legacy opportunity pipeline via the
// `pipeline_type` column on the backend.
export interface PipelineStage {
  id: number;
  name: string;
  description?: string | null;
  order: number;
  color: string;
  probability: number;
  is_won: boolean;
  is_lost: boolean;
  is_active: boolean;
  pipeline_type: string;
}

export interface PipelineStageCreate {
  name: string;
  description?: string | null;
  order?: number;
  color?: string;
  probability?: number;
  is_won?: boolean;
  is_lost?: boolean;
  is_active?: boolean;
  pipeline_type?: string;
}

export interface PipelineStageUpdate extends Partial<PipelineStageCreate> {}

export interface LeadSource {
  id: number;
  name: string;
  description?: string | null;
  is_active: boolean;
}

export interface LeadSourceCreate {
  name: string;
  description?: string | null;
  is_active?: boolean;
}

export interface LeadSourceUpdate {
  name?: string;
  description?: string | null;
  is_active?: boolean;
}

export interface LeadBase {
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  mobile?: string | null;
  job_title?: string | null;
  company_name?: string | null;
  website?: string | null;
  industry?: string | null;
  source_id?: number | null;
  source_details?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  description?: string | null;
  requirements?: string | null;
  budget_amount?: number | null;
  budget_currency: string;
  owner_id?: number | null;
  sales_code?: string | null;
}

export interface LeadCreate extends LeadBase {
  status?: string;
  pipeline_stage_id?: number | null;
  tag_ids?: number[] | null;
}

export interface LeadUpdate extends Partial<LeadBase> {
  status?: string;
  pipeline_stage_id?: number | null;
  tag_ids?: number[] | null;
}

export interface Lead extends LeadBase {
  id: number;
  full_name: string;
  status: string;
  score: number;
  score_factors?: string | null;
  pipeline_stage_id?: number | null;
  pipeline_stage?: PipelineStage | null;
  created_at: string;
  updated_at: string;
  source?: LeadSource | null;
  tags: TagBrief[];
  converted_contact_id?: number | null;
  // Legacy nullable FK preserved on the backend for historical data only.
  // UI must not display or submit this field.
  converted_opportunity_id?: number | null;
}

export type LeadListResponse = PaginatedResponse<Lead>;

export interface LeadFilters {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  source_id?: number;
  owner_id?: number;
  min_score?: number;
  tag_ids?: string;
  order_by?: string;
  order_dir?: 'asc' | 'desc';
}

// Lead Conversion Types
export interface LeadConvertToContactRequest {
  company_id?: number | null;
  create_company?: boolean;
}

export interface LeadFullConversionRequest {
  create_company?: boolean;
}

export interface ConversionResponse {
  lead_id: number;
  contact_id?: number | null;
  company_id?: number | null;
  message: string;
}

// Lead Kanban Types
export interface KanbanLead {
  id: number;
  first_name?: string | null;
  last_name?: string | null;
  full_name: string;
  email?: string | null;
  company_name?: string | null;
  score: number;
  owner_id?: number | null;
  owner_name?: string | null;
}

export interface KanbanLeadStage {
  stage_id: number;
  stage_name: string;
  color: string;
  probability: number;
  is_won: boolean;
  is_lost: boolean;
  leads: KanbanLead[];
  count: number;
}

export interface LeadKanbanResponse {
  stages: KanbanLeadStage[];
}

export interface MoveLeadRequest {
  new_stage_id: number;
}

export interface MoveLeadResponse extends Lead {
  // Conversion result on Won-stage moves. The shape varies:
  //  - successful convert: { converted: true, contact_id, company_id? }
  //  - skipped with reason: { converted: false, reason: 'stale_contact_fk' | 'already_converted' }
  //  - nothing to convert (non-Won move): conversion is absent
  conversion?:
    | {
        converted: true;
        contact_id: number;
        company_id: number | null;
      }
    | {
        converted: false;
        reason: 'stale_contact_fk' | 'already_converted';
      }
    | null;
}
