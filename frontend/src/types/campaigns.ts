/**
 * Campaign Types
 */

import type { PaginatedResponse } from './common';

export interface CampaignBase {
  name: string;
  description?: string | null;
  campaign_type: string;
  status: string;
  start_date?: string | null;
  end_date?: string | null;
  budget_amount?: number | null;
  actual_cost?: number | null;
  budget_currency: string;
  target_audience?: string | null;
  expected_revenue?: number | null;
  expected_response?: number | null;
  owner_id?: number | null;
}

export interface CampaignCreate extends CampaignBase {}

export interface CampaignUpdate extends Partial<CampaignBase> {
  actual_revenue?: number | null;
  num_sent?: number | null;
  num_responses?: number | null;
  num_converted?: number | null;
}

export interface Campaign extends CampaignBase {
  id: number;
  actual_revenue?: number | null;
  num_sent: number;
  num_responses: number;
  num_converted: number;
  response_rate?: number | null;
  conversion_rate?: number | null;
  roi?: number | null;
  is_executing: boolean;
  created_at: string;
  updated_at: string;
}

export type CampaignListResponse = PaginatedResponse<Campaign>;

export interface CampaignFilters {
  page?: number;
  page_size?: number;
  search?: string;
  campaign_type?: string;
  status?: string;
  owner_id?: number;
}

// Campaign Member Types
export interface CampaignMemberBase {
  campaign_id: number;
  member_type: string;
  member_id: number;
  status: string;
}

export interface CampaignMemberCreate extends CampaignMemberBase {}

export interface CampaignMemberUpdate {
  status?: string | null;
  sent_at?: string | null;
  responded_at?: string | null;
  converted_at?: string | null;
  response_notes?: string | null;
}

export interface CampaignMember extends CampaignMemberBase {
  id: number;
  sent_at?: string | null;
  responded_at?: string | null;
  converted_at?: string | null;
  response_notes?: string | null;
}

export interface AddMembersRequest {
  member_type: string;
  member_ids: number[];
}

export interface AddMembersResponse {
  added: number;
  message: string;
}

export interface CampaignStats {
  total_members: number;
  pending: number;
  sent: number;
  responded: number;
  converted: number;
  response_rate?: number | null;
  conversion_rate?: number | null;
}

export interface StepAnalytics {
  step_order: number;
  template_name: string;
  sent: number;
  opened: number;
  clicked: number;
  failed: number;
  open_rate: number;
  click_rate: number;
}

export interface CampaignAnalytics {
  campaign_id: number;
  total_sent: number;
  total_opened: number;
  total_clicked: number;
  total_failed: number;
  open_rate: number;
  click_rate: number;
  steps: StepAnalytics[];
}

// =============================================================================
// LinkedIn Campaign / Volume Types
// =============================================================================

export interface VolumeStats {
  sent_today: number;
  daily_limit: number;
  warmup_enabled: boolean;
  warmup_day: number;
  warmup_current_limit: number;
  remaining_today: number;
}

export interface EmailSettings {
  daily_send_limit: number;
  warmup_enabled: boolean;
  warmup_start_date: string | null;
  warmup_target_daily: number;
}

export interface EmailSettingsUpdate {
  daily_send_limit?: number;
  warmup_enabled?: boolean;
  warmup_start_date?: string | null;
  warmup_target_daily?: number;
}

export interface CreateCampaignFromImportRequest {
  name: string;
  member_ids: number[];
  member_type: string;
  template_id?: number;
  schedule_start?: string;
  delay_days?: number;
}

export interface CreateCampaignFromImportResponse extends Campaign {
  member_count: number;
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
