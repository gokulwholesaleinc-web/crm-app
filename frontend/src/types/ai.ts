// AI Types

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatRequest {
  message: string;
  session_id?: string | null;
}

export interface ChatResponse {
  response: string;
  data?: Record<string, unknown> | null;
  function_called?: string | null;
  session_id?: string | null;
  confirmation_required?: boolean;
  pending_action?: Record<string, unknown> | null;
  actions_taken?: Array<Record<string, unknown>>;
}

export interface ConfirmActionRequest {
  session_id: string;
  function_name: string;
  arguments: Record<string, unknown>;
  confirmed: boolean;
}

export interface ConfirmActionResponse {
  response: string;
  data?: Record<string, unknown> | null;
  function_called?: string | null;
  actions_taken?: Array<Record<string, unknown>>;
}

export interface FeedbackRequest {
  session_id?: string | null;
  query: string;
  response: string;
  retrieved_context_ids?: number[] | null;
  feedback: 'positive' | 'negative' | 'correction';
  correction_text?: string | null;
}

export interface FeedbackResponse {
  id: number;
  feedback: 'positive' | 'negative' | 'correction';
  created_at: string;
}

export interface InsightResponse {
  lead_data?: Record<string, unknown> | null;
  opportunity_data?: Record<string, unknown> | null;
  insights: string;
}

export interface DailySummaryResponse {
  data: Record<string, unknown>;
  summary: string;
}

export interface Recommendation {
  type: string;
  priority: string;
  title: string;
  description: string;
  action: string;
  entity_type?: string | null;
  entity_id?: number | null;
  activity_id?: number | null;
  amount?: number | null;
  score?: number | null;
}

export interface RecommendationsResponse {
  recommendations: Recommendation[];
}

export interface NextBestAction {
  action: string;
  activity_type?: string | null;
  reason: string;
}

export interface SimilarContentResult {
  entity_type: string;
  entity_id: number;
  content: string;
  content_type: string;
  similarity: number;
}

export interface SearchResponse {
  results: SimilarContentResult[];
}

export interface AIUserPreferences {
  id: number;
  user_id: number;
  preferred_communication_style: string | null;
  priority_entities: Record<string, unknown> | null;
  custom_instructions: string | null;
}

export interface AIUserPreferencesUpdate {
  preferred_communication_style?: string | null;
  priority_entities?: Record<string, unknown> | null;
  custom_instructions?: string | null;
}

export interface AILearning {
  id: number;
  user_id: number;
  category: string;
  key: string;
  value: string;
  confidence: number;
  times_reinforced: number;
  last_used_at: string | null;
  created_at: string;
}

export interface AILearningListResponse {
  learnings: AILearning[];
}

export interface TeachAIRequest {
  category: string;
  key: string;
  value: string;
}

export interface SmartSuggestion {
  type: string;
  priority: string;
  title: string;
  description: string;
  action: string;
  entity_type?: string | null;
  entity_id?: number | null;
}

export interface SmartSuggestionsResponse {
  suggestions: SmartSuggestion[];
}

export interface EntityInsightsResponse {
  entity_type: string;
  entity_id: number;
  insights: Array<{ label: string; value: number }>;
  suggestions: string[];
}
