/**
 * Quote Types
 */

import type { PaginatedResponse, ContactBrief, CompanyBrief } from './common';

export interface QuoteLineItem {
  id: number;
  quote_id: number;
  description: string;
  quantity: number;
  unit_price: number;
  discount: number;
  total: number;
  sort_order: number;
}

export interface QuoteLineItemCreate {
  description: string;
  quantity?: number;
  unit_price?: number;
  discount?: number;
  sort_order?: number;
}

export interface QuoteBase {
  title: string;
  description?: string | null;
  opportunity_id?: number | null;
  contact_id?: number | null;
  company_id?: number | null;
  status: string;
  valid_until?: string | null;
  currency: string;
  discount_type?: string | null;
  discount_value: number;
  tax_rate: number;
  terms_and_conditions?: string | null;
  notes?: string | null;
  owner_id?: number | null;
  payment_type?: string;
  recurring_interval?: string | null;
}

export interface QuoteCreate extends QuoteBase {
  line_items?: QuoteLineItemCreate[] | null;
}

export interface QuoteUpdate {
  title?: string | null;
  description?: string | null;
  opportunity_id?: number | null;
  contact_id?: number | null;
  company_id?: number | null;
  status?: string | null;
  valid_until?: string | null;
  currency?: string | null;
  discount_type?: string | null;
  discount_value?: number | null;
  tax_rate?: number | null;
  terms_and_conditions?: string | null;
  notes?: string | null;
  owner_id?: number | null;
  payment_type?: string | null;
  recurring_interval?: string | null;
}

export interface Quote extends QuoteBase {
  id: number;
  quote_number: string;
  /** Unguessable token used for the public accept/reject link. Nullable
   * only for pre-migration rows; new quotes get one on create. */
  public_token?: string | null;
  subtotal: number;
  tax_amount: number;
  total: number;
  sent_at?: string | null;
  accepted_at?: string | null;
  rejected_at?: string | null;
  created_at: string;
  updated_at: string;
  line_items: QuoteLineItem[];
  contact?: ContactBrief | null;
  company?: CompanyBrief | null;
  opportunity?: { id: number; name: string } | null;
}

export type QuoteListResponse = PaginatedResponse<Quote>;

export interface QuoteFilters {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  contact_id?: number;
  company_id?: number;
  opportunity_id?: number;
  owner_id?: number;
}

// Product Bundle Types
export interface ProductBundleItem {
  id: number;
  bundle_id: number;
  description: string;
  quantity: number;
  unit_price: number;
  sort_order: number;
}

export interface ProductBundleItemCreate {
  description: string;
  quantity?: number;
  unit_price?: number;
  sort_order?: number;
}

export interface ProductBundleCreate {
  name: string;
  description?: string | null;
  is_active?: boolean;
  items?: ProductBundleItemCreate[];
}

export interface ProductBundleUpdate {
  name?: string;
  description?: string | null;
  is_active?: boolean;
  items?: ProductBundleItemCreate[];
}

export interface ProductBundle {
  id: number;
  name: string;
  description?: string | null;
  is_active: boolean;
  items: ProductBundleItem[];
  created_at: string;
  updated_at: string;
}

export type ProductBundleListResponse = PaginatedResponse<ProductBundle>;

export interface ProductBundleFilters {
  page?: number;
  page_size?: number;
  search?: string;
  is_active?: boolean;
}
