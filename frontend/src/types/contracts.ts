import type { PaginatedResponse, ContactBrief, CompanyBrief } from './common';

// Contract Types

export interface ContractCreate {
  title: string;
  contact_id?: number | null;
  company_id?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  scope?: string | null;
  value?: number | null;
  currency?: string;
  status?: string;
  owner_id?: number | null;
}

export interface ContractUpdate {
  title?: string | null;
  contact_id?: number | null;
  company_id?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  scope?: string | null;
  value?: number | null;
  currency?: string | null;
  status?: string | null;
  owner_id?: number | null;
}

export interface Contract {
  id: number;
  title: string;
  contact_id?: number | null;
  company_id?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  scope?: string | null;
  value?: number | null;
  currency: string;
  status: string;
  owner_id?: number | null;
  created_at: string;
  updated_at: string;
  contact?: ContactBrief | null;
  company?: CompanyBrief | null;
}

export type ContractListResponse = PaginatedResponse<Contract>;

export interface ContractFilters {
  page?: number;
  page_size?: number;
  contact_id?: number;
  company_id?: number;
  status?: string;
  owner_id?: number;
}
