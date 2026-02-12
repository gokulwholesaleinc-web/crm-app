/**
 * Quotes hooks using the entity CRUD factory pattern.
 * Uses TanStack Query for data fetching and caching.
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { createEntityHooks, createQueryKeys } from './useEntityCRUD';
import { useAuthQuery } from './useAuthQuery';
import { quotesApi, bundlesApi } from '../api/quotes';
import type {
  Quote,
  QuoteCreate,
  QuoteUpdate,
  QuoteFilters,
  QuoteLineItemCreate,
  ProductBundleFilters,
} from '../types';

// =============================================================================
// Query Keys
// =============================================================================

export const quoteKeys = createQueryKeys('quotes');

// =============================================================================
// Entity CRUD Hooks using Factory Pattern
// =============================================================================

const quoteEntityHooks = createEntityHooks<
  Quote,
  QuoteCreate,
  QuoteUpdate,
  QuoteFilters
>({
  entityName: 'quotes',
  baseUrl: '/api/quotes',
  queryKey: 'quotes',
});

/**
 * Hook to fetch a paginated list of quotes
 */
export function useQuotes(filters?: QuoteFilters) {
  return quoteEntityHooks.useList(filters);
}

/**
 * Hook to fetch a single quote by ID
 */
export function useQuote(id: number | undefined) {
  return quoteEntityHooks.useOne(id);
}

/**
 * Hook to create a new quote
 */
export function useCreateQuote() {
  return quoteEntityHooks.useCreate();
}

/**
 * Hook to update a quote
 */
export function useUpdateQuote() {
  return quoteEntityHooks.useUpdate();
}

/**
 * Hook to delete a quote
 */
export function useDeleteQuote() {
  return quoteEntityHooks.useDelete();
}

// =============================================================================
// Status Action Hooks
// =============================================================================

/**
 * Hook to send a branded quote email
 */
export function useSendQuote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ quoteId, attachPdf = false }: { quoteId: number; attachPdf?: boolean }) =>
      quotesApi.send(quoteId, attachPdf),
    onSuccess: (_data, { quoteId }) => {
      queryClient.invalidateQueries({ queryKey: quoteKeys.lists() });
      queryClient.invalidateQueries({ queryKey: quoteKeys.detail(quoteId) });
    },
  });
}

/**
 * Hook to download a quote as branded PDF
 */
export function useDownloadQuotePDF() {
  return useMutation({
    mutationFn: (quoteId: number) => quotesApi.downloadPDF(quoteId),
  });
}

/**
 * Hook to accept a quote
 */
export function useAcceptQuote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (quoteId: number) => quotesApi.accept(quoteId),
    onSuccess: (_data, quoteId) => {
      queryClient.invalidateQueries({ queryKey: quoteKeys.lists() });
      queryClient.invalidateQueries({ queryKey: quoteKeys.detail(quoteId) });
    },
  });
}

/**
 * Hook to reject a quote
 */
export function useRejectQuote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (quoteId: number) => quotesApi.reject(quoteId),
    onSuccess: (_data, quoteId) => {
      queryClient.invalidateQueries({ queryKey: quoteKeys.lists() });
      queryClient.invalidateQueries({ queryKey: quoteKeys.detail(quoteId) });
    },
  });
}

// =============================================================================
// Line Item Hooks
// =============================================================================

/**
 * Hook to add a line item to a quote
 */
export function useAddLineItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ quoteId, data }: { quoteId: number; data: QuoteLineItemCreate }) =>
      quotesApi.addLineItem(quoteId, data),
    onSuccess: (_data, { quoteId }) => {
      queryClient.invalidateQueries({ queryKey: quoteKeys.detail(quoteId) });
      queryClient.invalidateQueries({ queryKey: quoteKeys.lists() });
    },
  });
}

/**
 * Hook to remove a line item from a quote
 */
export function useRemoveLineItem() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ quoteId, itemId }: { quoteId: number; itemId: number }) =>
      quotesApi.removeLineItem(quoteId, itemId),
    onSuccess: (_data, { quoteId }) => {
      queryClient.invalidateQueries({ queryKey: quoteKeys.detail(quoteId) });
      queryClient.invalidateQueries({ queryKey: quoteKeys.lists() });
    },
  });
}

// =============================================================================
// Product Bundle Hooks
// =============================================================================

export const bundleKeys = createQueryKeys('bundles');

export function useBundles(filters?: ProductBundleFilters) {
  return useAuthQuery({
    queryKey: [...bundleKeys.lists(), filters],
    queryFn: () => bundlesApi.list(filters),
  });
}

export function useCreateBundle() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: bundlesApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bundleKeys.lists() });
    },
  });
}

export function useUpdateBundle() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: Parameters<typeof bundlesApi.update>[1] }) =>
      bundlesApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bundleKeys.lists() });
    },
  });
}

export function useDeleteBundle() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: bundlesApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: bundleKeys.lists() });
    },
  });
}

export function useAddBundleToQuote() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ quoteId, bundleId }: { quoteId: number; bundleId: number }) =>
      bundlesApi.addToQuote(quoteId, bundleId),
    onSuccess: (_data, { quoteId }) => {
      queryClient.invalidateQueries({ queryKey: quoteKeys.detail(quoteId) });
      queryClient.invalidateQueries({ queryKey: quoteKeys.lists() });
    },
  });
}
