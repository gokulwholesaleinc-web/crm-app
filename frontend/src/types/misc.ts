/**
 * Miscellaneous Types — re-exported from domain files.
 * Import from this file or directly from the domain file; both work.
 */

export * from './ai';
export * from './admin';
export * from './workflows';
export * from './audit';
export * from './contracts';
export * from './import-export';

// =============================================================================
// Tag Types (used across multiple domains)
// =============================================================================

export interface Tag {
  id: number;
  name: string;
  color?: string | null;
  entity_type: string;
  created_at: string;
}

export interface TagCreate {
  name: string;
  color?: string | null;
  entity_type: string;
}

// =============================================================================
// Email Template Types
// =============================================================================

export interface EmailTemplate {
  id: number;
  name: string;
  subject_template: string;
  body_template: string;
  category?: string | null;
  created_by_id?: number | null;
  created_at: string;
  updated_at: string;
}

export interface EmailTemplateCreate {
  name: string;
  subject_template: string;
  body_template: string;
  category?: string | null;
}

export interface EmailTemplateUpdate {
  name?: string | null;
  subject_template?: string | null;
  body_template?: string | null;
  category?: string | null;
}

// =============================================================================
// Email Campaign Step Types
// =============================================================================

export interface EmailCampaignStep {
  id: number;
  campaign_id: number;
  template_id: number;
  delay_days: number;
  step_order: number;
  created_at: string;
}

export interface EmailCampaignStepCreate {
  template_id: number;
  delay_days: number;
  step_order: number;
}

export interface EmailCampaignStepUpdate {
  template_id?: number | null;
  delay_days?: number | null;
  step_order?: number | null;
}

// =============================================================================
// Sales Funnel Types
// =============================================================================

export interface FunnelStage {
  stage: string;
  count: number;
  color?: string | null;
}

export interface FunnelConversion {
  from_stage: string;
  to_stage: string;
  rate: number;
}

export interface SalesFunnelResponse {
  stages: FunnelStage[];
  conversions: FunnelConversion[];
  avg_days_in_stage: Record<string, number | null>;
}

// =============================================================================
// Pipeline (Multiple Pipelines) Types
// =============================================================================

export interface PipelineStageInPipeline {
  id: number;
  name: string;
  order: number;
  color: string | null;
  probability: number;
  is_won: boolean;
  is_lost: boolean;
}

export interface Pipeline {
  id: number;
  name: string;
  description: string | null;
  is_default: boolean;
  is_active: boolean;
  stages: PipelineStageInPipeline[];
  created_at: string;
  updated_at: string;
}

export interface PipelineCreate {
  name: string;
  description?: string;
  is_default?: boolean;
}

export interface PipelineUpdate {
  name?: string;
  description?: string;
  is_default?: boolean;
  is_active?: boolean;
}

export interface PipelineListResponse {
  items: Pipeline[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}
