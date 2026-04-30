/**
 * Payment / Stripe Types
 */

import type { PaginatedResponse } from './common';

export interface StripeCustomerBrief {
  id: number;
  stripe_customer_id: string;
  email: string | null;
  name: string | null;
  contact_id?: number | null;
  company_id?: number | null;
}

export interface StripeCustomer extends StripeCustomerBrief {
  contact_id: number | null;
  company_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface PaymentBase {
  amount: number;
  currency: string;
  status: string;
  payment_method?: string | null;
  customer_id?: number | null;
  opportunity_id?: number | null;
  quote_id?: number | null;
  owner_id?: number | null;
}

export interface PaymentCreate extends PaymentBase {}

export interface PaymentUpdate {
  status?: string;
  amount?: number;
  currency?: string;
}

export interface Payment extends PaymentBase {
  id: number;
  stripe_payment_intent_id: string | null;
  stripe_checkout_session_id: string | null;
  description: string | null;
  receipt_url: string | null;
  refund_amount: number | null;
  metadata_json: Record<string, unknown> | null;
  customer?: StripeCustomerBrief | null;
  opportunity?: { id: number; name: string } | null;
  quote?: { id: number; title: string } | null;
  proposal?: { id: number; title: string; proposal_number: string } | null;
  created_at: string;
  updated_at: string;
}

export type PaymentListResponse = PaginatedResponse<Payment>;

export interface PaymentFilters {
  page?: number;
  page_size?: number;
  status?: string;
  customer_id?: number;
  opportunity_id?: number;
  owner_id?: number;
  search?: string;
}

export interface ProductPrice {
  id: number;
  stripe_price_id: string | null;
  amount: number;
  currency: string;
  recurring_interval: string | null;
  is_active: boolean;
}

export interface ProductCreate {
  name: string;
  description?: string;
}

export interface ProductItem {
  id: number;
  name: string;
  description: string | null;
  stripe_product_id: string | null;
  is_active: boolean;
  prices: ProductPrice[];
  created_at: string;
  updated_at: string;
}

export interface SubscriptionItem {
  id: number;
  stripe_subscription_id: string;
  customer_id: number;
  price_id: number | null;
  status: string;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  customer?: StripeCustomerBrief | null;
  created_at: string;
  updated_at: string;
}

export interface CreateCheckoutRequest {
  amount?: number;
  currency?: string;
  success_url: string;
  cancel_url: string;
  customer_id?: number;
  quote_id?: number;
}

export interface CreateCheckoutResponse {
  session_id: string;
  checkout_url: string;
  payment_id: number;
}

export interface CreatePaymentIntentRequest {
  amount: number;
  currency?: string;
  customer_id?: number;
  opportunity_id?: number;
  quote_id?: number;
}

export interface CreatePaymentIntentResponse {
  client_secret: string;
  payment_intent_id: string;
  payment_id: number;
}

export interface SyncCustomerRequest {
  contact_id?: number;
  company_id?: number;
}

export interface CreateAndSendInvoiceRequest {
  customer_id: number;
  amount: number;
  description: string;
  due_days?: number;
  payment_method_types?: string[];
}

export interface CreateAndSendInvoiceResponse {
  invoice_id: string;
  payment_id: number;
  status: string;
  invoice_url?: string;
}

export interface CreateOnboardingLinkRequest {
  contact_id?: number;
  company_id?: number;
  success_url: string;
  cancel_url: string;
}

export interface CreateOnboardingLinkResponse {
  url: string;
}

export type StripeCustomerListResponse = PaginatedResponse<StripeCustomer>;
export type ProductListResponse = PaginatedResponse<ProductItem>;
export type SubscriptionListResponse = PaginatedResponse<SubscriptionItem>;
