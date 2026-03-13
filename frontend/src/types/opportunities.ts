/**
 * Opportunity Types
 */

import type { PaginatedResponse, TagBrief, ContactBrief, CompanyBrief } from './common';

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

export interface OpportunityBase {
  name: string;
  description?: string | null;
  pipeline_stage_id: number;
  amount?: number | null;
  currency: string;
  probability?: number | null;
  expected_close_date?: string | null;
  contact_id?: number | null;
  company_id?: number | null;
  source?: string | null;
  owner_id?: number | null;
}

export interface OpportunityCreate extends OpportunityBase {
  tag_ids?: number[] | null;
}

export interface OpportunityUpdate extends Partial<OpportunityBase> {
  actual_close_date?: string | null;
  loss_reason?: string | null;
  loss_notes?: string | null;
  tag_ids?: number[] | null;
}

export interface Opportunity extends OpportunityBase {
  id: number;
  actual_close_date?: string | null;
  loss_reason?: string | null;
  loss_notes?: string | null;
  weighted_amount?: number | null;
  created_at: string;
  updated_at: string;
  pipeline_stage: PipelineStage;
  contact?: ContactBrief | null;
  company?: CompanyBrief | null;
  tags: TagBrief[];
}

export type OpportunityListResponse = PaginatedResponse<Opportunity>;

export interface OpportunityFilters {
  page?: number;
  page_size?: number;
  search?: string;
  pipeline_stage_id?: number;
  contact_id?: number;
  company_id?: number;
  owner_id?: number;
  tag_ids?: string;
}

// Kanban Types
export interface KanbanOpportunity {
  id: number;
  name: string;
  amount?: number | null;
  currency: string;
  weighted_amount?: number | null;
  expected_close_date?: string | null;
  contact_name?: string | null;
  company_name?: string | null;
  owner_id?: number | null;
}

export interface KanbanStage {
  stage_id: number;
  stage_name: string;
  color: string;
  probability: number;
  is_won: boolean;
  is_lost: boolean;
  opportunities: KanbanOpportunity[];
  total_amount: number;
  total_weighted: number;
  count: number;
}

export interface KanbanResponse {
  stages: KanbanStage[];
}

export interface MoveOpportunityRequest {
  new_stage_id: number;
}

// Unified Pipeline Types
export interface UnifiedPipelineItem {
  id: number;
  name: string;
  entity_type: 'lead' | 'opportunity';
  value: number | null;
  owner_id: number | null;
  company_name?: string | null;
  contact_name?: string | null;
  score?: number | null;
}

export interface UnifiedPipelineStage {
  stage_id: number;
  stage_name: string;
  color: string;
  entity_type: 'lead' | 'opportunity';
  items: UnifiedPipelineItem[];
  count: number;
  total_value?: number;
}

export interface UnifiedPipelineResponse {
  lead_stages: UnifiedPipelineStage[];
  opportunity_stages: UnifiedPipelineStage[];
}

// Forecast Types
export interface ForecastPeriod {
  month: string;
  month_label: string;
  best_case: number;
  weighted: number;
  commit: number;
  opportunity_count: number;
}

export interface ForecastTotals {
  best_case: number;
  weighted: number;
  commit: number;
}

export interface ForecastResponse {
  periods: ForecastPeriod[];
  totals: ForecastTotals;
  currency: string;
}

export interface PipelineSummaryStage {
  count: number;
  value: number;
  weighted: number;
}

export interface PipelineSummaryResponse {
  total_opportunities: number;
  total_value: number;
  weighted_value: number;
  currency: string;
  by_stage: Record<string, PipelineSummaryStage>;
}
