/**
 * Contact Types
 */

import type { PaginatedResponse, TagBrief, CompanyBrief } from './common';

export interface ContactBase {
  first_name: string;
  last_name: string;
  email?: string | null;
  phone?: string | null;
  mobile?: string | null;
  job_title?: string | null;
  department?: string | null;
  company_id?: number | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  linkedin_url?: string | null;
  twitter_handle?: string | null;
  description?: string | null;
  status: string;
  owner_id?: number | null;
  sales_code?: string | null;
}

export interface ContactCreate extends ContactBase {
  tag_ids?: number[] | null;
}

export interface ContactUpdate extends Partial<ContactBase> {
  tag_ids?: number[] | null;
}

export interface Contact extends ContactBase {
  id: number;
  full_name: string;
  avatar_url?: string | null;
  created_at: string;
  updated_at: string;
  company?: CompanyBrief | null;
  tags: TagBrief[];
}

export type ContactListResponse = PaginatedResponse<Contact>;

export interface ContactFilters {
  page?: number;
  page_size?: number;
  search?: string;
  company_id?: number;
  status?: string;
  owner_id?: number;
  tag_ids?: string;
  filters?: string;
  order_by?: string;
  order_dir?: 'asc' | 'desc';
}
