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
  ConfirmActionRequest,
  ConfirmActionResponse,
  FeedbackRequest,
  FeedbackResponse,
  AIUserPreferences,
  AIUserPreferencesUpdate,
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

// =============================================================================
// Confirm Action
// =============================================================================

/**
 * Confirm and execute a high-risk AI action
 */
export const confirmAction = async (
  request: ConfirmActionRequest
): Promise<ConfirmActionResponse> => {
  const response = await apiClient.post<ConfirmActionResponse>(
    `${AI_BASE}/confirm-action`,
    request
  );
  return response.data;
};

// =============================================================================
// Feedback
// =============================================================================

/**
 * Submit feedback on an AI response
 */
export const submitFeedback = async (
  request: FeedbackRequest
): Promise<FeedbackResponse> => {
  const response = await apiClient.post<FeedbackResponse>(
    `${AI_BASE}/feedback`,
    request
  );
  return response.data;
};

// =============================================================================
// User Preferences
// =============================================================================

/**
 * Get user AI preferences
 */
export const getPreferences = async (): Promise<AIUserPreferences> => {
  const response = await apiClient.get<AIUserPreferences>(`${AI_BASE}/preferences`);
  return response.data;
};

/**
 * Update user AI preferences
 */
export const updatePreferences = async (
  data: AIUserPreferencesUpdate
): Promise<AIUserPreferences> => {
  const response = await apiClient.put<AIUserPreferences>(`${AI_BASE}/preferences`, data);
  return response.data;
};

// =============================================================================
// Predictive AI
// =============================================================================

export interface WinProbabilityResponse {
  opportunity_id: number;
  win_probability: number;
  base_stage_probability: number;
  factors: Record<string, number | boolean>;
}

export interface ActivitySummaryResponse {
  entity_type: string;
  entity_id: number;
  period_days: number;
  total_activities: number;
  by_type: Record<string, number>;
  last_activity: { id: number; type: string; subject: string; date: string } | null;
  summary: string;
}

/**
 * Predict win probability for an opportunity
 */
export const predictWinProbability = async (
  opportunityId: number
): Promise<WinProbabilityResponse> => {
  const response = await apiClient.get<WinProbabilityResponse>(
    `${AI_BASE}/predict/opportunity/${opportunityId}`
  );
  return response.data;
};

/**
 * Suggest next best action for an entity
 */
export const suggestNextAction = async (
  entityType: string,
  entityId: number
): Promise<NextBestAction> => {
  const response = await apiClient.get<NextBestAction>(
    `${AI_BASE}/suggest/next-action/${entityType}/${entityId}`
  );
  return response.data;
};

/**
 * Get activity summary for an entity
 */
export const getActivitySummary = async (
  entityType: string,
  entityId: number,
  days = 30
): Promise<ActivitySummaryResponse> => {
  const response = await apiClient.get<ActivitySummaryResponse>(
    `${AI_BASE}/summary/${entityType}/${entityId}`,
    { params: { days } }
  );
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
  // Actions
  confirmAction,
  // Feedback
  submitFeedback,
  // Preferences
  getPreferences,
  updatePreferences,
  // Predictive AI
  predictWinProbability,
  suggestNextAction,
  getActivitySummary,
};

export default aiApi;
