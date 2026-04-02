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
