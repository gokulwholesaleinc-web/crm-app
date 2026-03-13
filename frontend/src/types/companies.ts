/**
 * Company Types
 */

import type { PaginatedResponse, TagBrief } from './common';

export interface CompanyBase {
  name: string;
  website?: string | null;
  industry?: string | null;
  company_size?: string | null;
  phone?: string | null;
  email?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  annual_revenue?: number | null;
  employee_count?: number | null;
  linkedin_url?: string | null;
  twitter_handle?: string | null;
  description?: string | null;
  link_creative_tier?: string | null;
  sow_url?: string | null;
  account_manager?: string | null;
  status: string;
  segment?: string | null;
  owner_id?: number | null;
}

export interface CompanyCreate extends CompanyBase {
  tag_ids?: number[] | null;
}

export interface CompanyUpdate extends Partial<CompanyBase> {
  tag_ids?: number[] | null;
}

export interface Company extends CompanyBase {
  id: number;
  logo_url?: string | null;
  created_at: string;
  updated_at: string;
  tags: TagBrief[];
  contact_count: number;
}

export type CompanyListResponse = PaginatedResponse<Company>;

export interface CompanyFilters {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  industry?: string;
  owner_id?: number;
  tag_ids?: string;
}
