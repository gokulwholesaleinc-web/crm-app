/**
 * Payments API
 */

import { apiClient } from './client';
import type {
  Payment,
  PaymentListResponse,
  PaymentFilters,
  ProductItem,
  ProductCreate,
  ProductListResponse,
  StripeCustomer,
  StripeCustomerListResponse,
  SyncCustomerRequest,
  SubscriptionItem,
  SubscriptionListResponse,
  CreateCheckoutRequest,
  CreateCheckoutResponse,
  CreatePaymentIntentRequest,
  CreatePaymentIntentResponse,
} from '../types';

const PAYMENTS_BASE = '/api/payments';

/**
 * List payments with pagination and filters
 */
export const listPayments = async (filters: PaymentFilters = {}): Promise<PaymentListResponse> => {
  const response = await apiClient.get<PaymentListResponse>(PAYMENTS_BASE, {
    params: filters,
  });
  return response.data;
};

/**
 * Get a payment by ID
 */
export const getPayment = async (paymentId: number): Promise<Payment> => {
  const response = await apiClient.get<Payment>(`${PAYMENTS_BASE}/${paymentId}`);
  return response.data;
};

/**
 * Create a Stripe Checkout Session
 */
export const createCheckout = async (data: CreateCheckoutRequest): Promise<CreateCheckoutResponse> => {
  const response = await apiClient.post<CreateCheckoutResponse>(`${PAYMENTS_BASE}/create-checkout`, data);
  return response.data;
};

/**
 * Create a Stripe PaymentIntent
 */
export const createPaymentIntent = async (data: CreatePaymentIntentRequest): Promise<CreatePaymentIntentResponse> => {
  const response = await apiClient.post<CreatePaymentIntentResponse>(`${PAYMENTS_BASE}/create-payment-intent`, data);
  return response.data;
};

/**
 * List Stripe customers
 */
export const listCustomers = async (params: { page?: number; page_size?: number } = {}): Promise<StripeCustomerListResponse> => {
  const response = await apiClient.get<StripeCustomerListResponse>(`${PAYMENTS_BASE}/customers`, { params });
  return response.data;
};

/**
 * Sync a CRM contact/company to Stripe
 */
export const syncCustomer = async (data: SyncCustomerRequest): Promise<StripeCustomer> => {
  const response = await apiClient.post<StripeCustomer>(`${PAYMENTS_BASE}/customers/sync`, data);
  return response.data;
};

/**
 * List products
 */
export const listProducts = async (params: { page?: number; page_size?: number; is_active?: boolean } = {}): Promise<ProductListResponse> => {
  const response = await apiClient.get<ProductListResponse>(`${PAYMENTS_BASE}/products`, { params });
  return response.data;
};

/**
 * Create a product
 */
export const createProduct = async (data: ProductCreate): Promise<ProductItem> => {
  const response = await apiClient.post<ProductItem>(`${PAYMENTS_BASE}/products`, data);
  return response.data;
};

/**
 * List subscriptions
 */
export const listSubscriptions = async (params: { page?: number; page_size?: number; status?: string; customer_id?: number } = {}): Promise<SubscriptionListResponse> => {
  const response = await apiClient.get<SubscriptionListResponse>(`${PAYMENTS_BASE}/subscriptions`, { params });
  return response.data;
};

/**
 * Cancel a subscription
 */
export const cancelSubscription = async (subscriptionId: number): Promise<SubscriptionItem> => {
  const response = await apiClient.post<SubscriptionItem>(`${PAYMENTS_BASE}/subscriptions/${subscriptionId}/cancel`);
  return response.data;
};

export const paymentsApi = {
  list: listPayments,
  get: getPayment,
  createCheckout,
  createPaymentIntent,
  listCustomers,
  syncCustomer,
  listProducts,
  createProduct,
  listSubscriptions,
  cancelSubscription,
};

export default paymentsApi;
