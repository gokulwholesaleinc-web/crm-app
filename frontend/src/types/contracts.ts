import type { PaginatedResponse, ContactBrief, CompanyBrief } from './common';

// Contract Types

export interface ContractCreate {
  title: string;
  contract_number?: string | null;
  contact_id?: number | null;
  company_id?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  scope?: string | null;
  value?: number | null;
  currency?: string;
  status?: string;
  owner_id?: number | null;
  designated_signer_email?: string | null;
}

export interface ContractUpdate {
  title?: string | null;
  contract_number?: string | null;
  contact_id?: number | null;
  company_id?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  scope?: string | null;
  value?: number | null;
  currency?: string | null;
  status?: string | null;
  owner_id?: number | null;
  designated_signer_email?: string | null;
}

export interface Contract {
  id: number;
  title: string;
  contract_number?: string | null;
  contact_id?: number | null;
  company_id?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  scope?: string | null;
  value?: number | null;
  currency: string;
  status: string;
  owner_id?: number | null;
  designated_signer_email?: string | null;
  created_at: string;
  updated_at: string;
  contact?: ContactBrief | null;
  company?: CompanyBrief | null;
  // E-sign fields
  sent_at?: string | null;
  signed_at?: string | null;
  signed_by_name?: string | null;
  signer_email?: string | null;
  signer_ip?: string | null;
  signer_user_agent?: string | null;
  signed_pdf_r2_key?: string | null;
}

export type ContractListResponse = PaginatedResponse<Contract>;

export interface ContractFilters {
  page?: number;
  page_size?: number;
  contact_id?: number;
  company_id?: number;
  status?: string;
  owner_id?: number;
  search?: string;
  order_by?: string;
  order_dir?: string;
}

export interface ContractStats {
  total_active_value: number;
  expiring_this_month: number;
  status_breakdown: {
    draft: number;
    sent: number;
    signed: number;
    active: number;
    expired: number;
    terminated: number;
  };
}
