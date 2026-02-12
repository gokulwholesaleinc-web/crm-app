/**
 * Payments hooks using TanStack Query v5.
 * Uses the entity CRUD factory pattern for list/detail, plus custom mutations.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createEntityHooks, createQueryKeys } from './useEntityCRUD';
import { paymentsApi } from '../api/payments';
import { useAuthQuery } from './useAuthQuery';
import type {
  Payment,
  PaymentCreate,
  PaymentUpdate,
  PaymentFilters,
  ProductItem,
  ProductCreate,
  CreateCheckoutRequest,
  CreatePaymentIntentRequest,
  SyncCustomerRequest,
} from '../types';

// =============================================================================
// Query Keys
// =============================================================================

export const paymentKeys = createQueryKeys('payments');

const productQueryKey = 'payment-products';
const customerQueryKey = 'payment-customers';
const subscriptionQueryKey = 'payment-subscriptions';

// =============================================================================
// Entity CRUD Hooks using Factory Pattern
// =============================================================================

const paymentEntityHooks = createEntityHooks<
  Payment,
  PaymentCreate,
  PaymentUpdate,
  PaymentFilters
>({
  entityName: 'payments',
  baseUrl: '/api/payments',
  queryKey: 'payments',
});

/**
 * Hook to fetch a paginated list of payments
 */
export function usePayments(filters?: PaymentFilters) {
  return paymentEntityHooks.useList(filters);
}

/**
 * Hook to fetch a single payment by ID
 */
export function usePayment(id: number | undefined) {
  return paymentEntityHooks.useOne(id);
}

// =============================================================================
// Checkout & PaymentIntent Hooks
// =============================================================================

/**
 * Hook to create a Stripe Checkout Session
 */
export function useCreateCheckout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreateCheckoutRequest) => paymentsApi.createCheckout(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: paymentKeys.lists() });
    },
  });
}

/**
 * Hook to create a Stripe PaymentIntent
 */
export function useCreatePaymentIntent() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: CreatePaymentIntentRequest) => paymentsApi.createPaymentIntent(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: paymentKeys.lists() });
    },
  });
}

// =============================================================================
// Customer Hooks
// =============================================================================

/**
 * Hook to list Stripe customers
 */
export function useStripeCustomers(params?: { page?: number; page_size?: number }) {
  return useAuthQuery({
    queryKey: [customerQueryKey, 'list', params],
    queryFn: () => paymentsApi.listCustomers(params),
  });
}

/**
 * Hook to sync a CRM entity to Stripe
 */
export function useSyncCustomer() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: SyncCustomerRequest) => paymentsApi.syncCustomer(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [customerQueryKey, 'list'] });
    },
  });
}

// =============================================================================
// Product Hooks
// =============================================================================

/**
 * Hook to list products
 */
export function useProducts(params?: { page?: number; page_size?: number; is_active?: boolean }) {
  return useAuthQuery({
    queryKey: [productQueryKey, 'list', params],
    queryFn: () => paymentsApi.listProducts(params),
  });
}

/**
 * Hook to create a product
 */
export function useCreateProduct() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: ProductCreate) => paymentsApi.createProduct(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [productQueryKey, 'list'] });
    },
  });
}

// =============================================================================
// Subscription Hooks
// =============================================================================

/**
 * Hook to list subscriptions
 */
export function useSubscriptions(params?: { page?: number; page_size?: number; status?: string; customer_id?: number }) {
  return useAuthQuery({
    queryKey: [subscriptionQueryKey, 'list', params],
    queryFn: () => paymentsApi.listSubscriptions(params),
  });
}

/**
 * Hook to cancel a subscription
 */
export function useCancelSubscription() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (subscriptionId: number) => paymentsApi.cancelSubscription(subscriptionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [subscriptionQueryKey, 'list'] });
    },
  });
}
