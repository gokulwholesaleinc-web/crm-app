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
 * Send a quote
 */
export const sendQuote = async (quoteId: number): Promise<Quote> => {
  const response = await apiClient.post<Quote>(`${QUOTES_BASE}/${quoteId}/send`);
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
};

export default quotesApi;
