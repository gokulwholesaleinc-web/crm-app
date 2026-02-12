/**
 * Quotes API
 */

import { apiClient } from './client';
import type {
  Quote,
  QuoteCreate,
  QuoteUpdate,
  QuoteListResponse,
  QuoteFilters,
  QuoteLineItem,
  QuoteLineItemCreate,
} from '../types';

const QUOTES_BASE = '/api/quotes';

/**
 * List quotes with pagination and filters
 */
export const listQuotes = async (filters: QuoteFilters = {}): Promise<QuoteListResponse> => {
  const response = await apiClient.get<QuoteListResponse>(QUOTES_BASE, {
    params: filters,
  });
  return response.data;
};

/**
 * Get a quote by ID
 */
export const getQuote = async (quoteId: number): Promise<Quote> => {
  const response = await apiClient.get<Quote>(`${QUOTES_BASE}/${quoteId}`);
  return response.data;
};

/**
 * Create a new quote
 */
export const createQuote = async (quoteData: QuoteCreate): Promise<Quote> => {
  const response = await apiClient.post<Quote>(QUOTES_BASE, quoteData);
  return response.data;
};

/**
 * Update a quote
 */
export const updateQuote = async (
  quoteId: number,
  quoteData: QuoteUpdate
): Promise<Quote> => {
  const response = await apiClient.patch<Quote>(`${QUOTES_BASE}/${quoteId}`, quoteData);
  return response.data;
};

/**
 * Delete a quote
 */
export const deleteQuote = async (quoteId: number): Promise<void> => {
  await apiClient.delete(`${QUOTES_BASE}/${quoteId}`);
};

/**
 * Send a branded quote email
 */
export const sendQuote = async (quoteId: number, attachPdf: boolean = false): Promise<Quote> => {
  const response = await apiClient.post<Quote>(`${QUOTES_BASE}/${quoteId}/send`, null, {
    params: attachPdf ? { attach_pdf: true } : undefined,
  });
  return response.data;
};

/**
 * Download quote as branded PDF
 */
export const downloadQuotePDF = async (quoteId: number): Promise<Blob> => {
  const response = await apiClient.get(`${QUOTES_BASE}/${quoteId}/pdf`, {
    params: { download: true },
    responseType: 'blob',
  });
  return response.data;
};

/**
 * Accept a quote
 */
export const acceptQuote = async (quoteId: number): Promise<Quote> => {
  const response = await apiClient.post<Quote>(`${QUOTES_BASE}/${quoteId}/accept`);
  return response.data;
};

/**
 * Reject a quote
 */
export const rejectQuote = async (quoteId: number): Promise<Quote> => {
  const response = await apiClient.post<Quote>(`${QUOTES_BASE}/${quoteId}/reject`);
  return response.data;
};

/**
 * Add a line item to a quote
 */
export const addLineItem = async (
  quoteId: number,
  itemData: QuoteLineItemCreate
): Promise<QuoteLineItem> => {
  const response = await apiClient.post<QuoteLineItem>(
    `${QUOTES_BASE}/${quoteId}/line-items`,
    itemData
  );
  return response.data;
};

/**
 * Remove a line item from a quote
 */
export const removeLineItem = async (
  quoteId: number,
  itemId: number
): Promise<void> => {
  await apiClient.delete(`${QUOTES_BASE}/${quoteId}/line-items/${itemId}`);
};

export const quotesApi = {
  list: listQuotes,
  get: getQuote,
  create: createQuote,
  update: updateQuote,
  delete: deleteQuote,
  send: sendQuote,
  accept: acceptQuote,
  reject: rejectQuote,
  addLineItem,
  removeLineItem,
  downloadPDF: downloadQuotePDF,
};

export default quotesApi;

// =============================================================================
// Product Bundle API
// =============================================================================

import type {
  ProductBundle,
  ProductBundleCreate,
  ProductBundleUpdate,
  ProductBundleListResponse,
  ProductBundleFilters,
} from '../types';

const BUNDLES_BASE = `${QUOTES_BASE}/bundles`;

export const listBundles = async (filters: ProductBundleFilters = {}): Promise<ProductBundleListResponse> => {
  const response = await apiClient.get<ProductBundleListResponse>(BUNDLES_BASE, { params: filters });
  return response.data;
};

export const getBundle = async (bundleId: number): Promise<ProductBundle> => {
  const response = await apiClient.get<ProductBundle>(`${BUNDLES_BASE}/${bundleId}`);
  return response.data;
};

export const createBundle = async (data: ProductBundleCreate): Promise<ProductBundle> => {
  const response = await apiClient.post<ProductBundle>(BUNDLES_BASE, data);
  return response.data;
};

export const updateBundle = async (bundleId: number, data: ProductBundleUpdate): Promise<ProductBundle> => {
  const response = await apiClient.patch<ProductBundle>(`${BUNDLES_BASE}/${bundleId}`, data);
  return response.data;
};

export const deleteBundle = async (bundleId: number): Promise<void> => {
  await apiClient.delete(`${BUNDLES_BASE}/${bundleId}`);
};

export const addBundleToQuote = async (quoteId: number, bundleId: number): Promise<Quote> => {
  const response = await apiClient.post<Quote>(`${QUOTES_BASE}/${quoteId}/add-bundle/${bundleId}`);
  return response.data;
};

export const bundlesApi = {
  list: listBundles,
  get: getBundle,
  create: createBundle,
  update: updateBundle,
  delete: deleteBundle,
  addToQuote: addBundleToQuote,
};
