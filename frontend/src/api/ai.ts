/**
 * AI Assistant API
 */

import { apiClient } from './client';
import type {
  ChatRequest,
  ChatResponse,
  InsightResponse,
  DailySummaryResponse,
  RecommendationsResponse,
  NextBestAction,
  SearchResponse,
} from '../types';

const AI_BASE = '/api/ai';

// =============================================================================
// Chat
// =============================================================================

/**
 * Send a chat message to the AI assistant
 */
export const chat = async (request: ChatRequest): Promise<ChatResponse> => {
  const response = await apiClient.post<ChatResponse>(`${AI_BASE}/chat`, request);
  return response.data;
};

// =============================================================================
// Insights
// =============================================================================

/**
 * Get AI-powered insights for a lead
 */
export const getLeadInsights = async (leadId: number): Promise<InsightResponse> => {
  const response = await apiClient.get<InsightResponse>(
    `${AI_BASE}/insights/lead/${leadId}`
  );
  return response.data;
};

/**
 * Get AI-powered insights for an opportunity
 */
export const getOpportunityInsights = async (
  opportunityId: number
): Promise<InsightResponse> => {
  const response = await apiClient.get<InsightResponse>(
    `${AI_BASE}/insights/opportunity/${opportunityId}`
  );
  return response.data;
};

// =============================================================================
// Summary
// =============================================================================

/**
 * Get AI-generated daily summary
 */
export const getDailySummary = async (): Promise<DailySummaryResponse> => {
  const response = await apiClient.get<DailySummaryResponse>(`${AI_BASE}/summary/daily`);
  return response.data;
};

// =============================================================================
// Recommendations
// =============================================================================

/**
 * Get prioritized action recommendations
 */
export const getRecommendations = async (): Promise<RecommendationsResponse> => {
  const response = await apiClient.get<RecommendationsResponse>(
    `${AI_BASE}/recommendations`
  );
  return response.data;
};

/**
 * Get the recommended next action for an entity
 */
export const getNextBestAction = async (
  entityType: string,
  entityId: number
): Promise<NextBestAction> => {
  const response = await apiClient.get<NextBestAction>(
    `${AI_BASE}/next-action/${entityType}/${entityId}`
  );
  return response.data;
};

// =============================================================================
// Semantic Search
// =============================================================================

/**
 * Perform semantic search across CRM content
 */
export const semanticSearch = async (
  query: string,
  entityTypes?: string,
  limit = 5
): Promise<SearchResponse> => {
  const response = await apiClient.get<SearchResponse>(`${AI_BASE}/search`, {
    params: {
      query,
      ...(entityTypes && { entity_types: entityTypes }),
      limit,
    },
  });
  return response.data;
};

// Export all AI functions
export const aiApi = {
  chat,
  // Insights
  getLeadInsights,
  getOpportunityInsights,
  // Summary
  getDailySummary,
  // Recommendations
  getRecommendations,
  getNextBestAction,
  // Search
  semanticSearch,
};

export default aiApi;
