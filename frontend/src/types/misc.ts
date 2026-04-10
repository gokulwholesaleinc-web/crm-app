/**
 * Miscellaneous Types
 * AI, Tags, Import/Export, Email Templates, Workflows, Webhooks,
 * Sequences, Admin, Comments, Audit, Roles, Assignment, Contracts,
 * Pipelines, Sales Funnel
 */

import type { PaginatedResponse, ContactBrief, CompanyBrief } from './common';

// =============================================================================
// AI Types
// =============================================================================

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
  feedback: string;
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

// =============================================================================
// Tag Types
// =============================================================================

export interface Tag {
  id: number;
  name: string;
  color?: string | null;
  entity_type: string;
  created_at: string;
}

export interface TagCreate {
  name: string;
  color?: string | null;
  entity_type: string;
}

// =============================================================================
// Import/Export Types
// =============================================================================

/**
 * Result of an import operation
 */
export interface DuplicateEntry {
  row: number;
  email: string;
  label: string;
}

export interface ImportResult {
  success: boolean;
  imported_count: number;
  errors: string[];
  duplicates_skipped: number;
  duplicates: DuplicateEntry[];
  contacts_created?: number;
  contacts_linked?: number;
}

export interface ContactMatchCandidate {
  contact_id: number;
  name: string;
  email: string | null;
  match_pct: number;
}

export interface ContactMatch {
  row: number;
  csv_name: string;
  first_name: string;
  last_name: string;
  candidates: ContactMatchCandidate[];
}

export interface ContactDecision {
  csv_name: string;
  action: 'create_new' | 'link_existing' | 'skip';
  contact_id?: number;
}

export interface ImportPreview {
  total_rows: number;
  csv_headers: string[];
  available_fields: string[];
  column_mapping: Record<string, string>;
  unmapped_columns: string[];
  missing_fields: string[];
  preview_rows: Record<string, string>[];
  warnings: string[];
  source_detected?: string | null;
  is_linkedin_format?: boolean;
  contact_person_column?: string;
  contact_matches?: ContactMatch[];
}

/**
 * Entity types available for import/export
 */
export type ImportExportEntityType = 'contacts' | 'companies' | 'leads';

// Bulk Operation Types
export interface BulkUpdateRequest {
  entity_type: string;
  entity_ids: number[];
  updates: Record<string, unknown>;
}

export interface BulkAssignRequest {
  entity_type: string;
  entity_ids: number[];
  owner_id: number;
}

export interface BulkOperationResult {
  success: boolean;
  updated: number;
  entity_type: string;
  error?: string;
  updates_applied?: Record<string, unknown>;
  owner_id?: number;
}

// =============================================================================
// Email Template Types
// =============================================================================

export interface EmailTemplate {
  id: number;
  name: string;
  subject_template: string;
  body_template: string;
  category?: string | null;
  created_by_id?: number | null;
  created_at: string;
  updated_at: string;
}

export interface EmailTemplateCreate {
  name: string;
  subject_template: string;
  body_template: string;
  category?: string | null;
}

export interface EmailTemplateUpdate {
  name?: string | null;
  subject_template?: string | null;
  body_template?: string | null;
  category?: string | null;
}

// =============================================================================
// Email Campaign Step Types
// =============================================================================

export interface EmailCampaignStep {
  id: number;
  campaign_id: number;
  template_id: number;
  delay_days: number;
  step_order: number;
  created_at: string;
}

export interface EmailCampaignStepCreate {
  template_id: number;
  delay_days: number;
  step_order: number;
}

export interface EmailCampaignStepUpdate {
  template_id?: number | null;
  delay_days?: number | null;
  step_order?: number | null;
}

// =============================================================================
// Workflow Types
// =============================================================================

export interface WorkflowRule {
  id: number;
  name: string;
  description?: string | null;
  is_active: boolean;
  trigger_entity: string;
  trigger_event: string;
  conditions?: Record<string, unknown> | null;
  actions?: Record<string, unknown>[] | null;
  created_by_id?: number | null;
  created_at: string;
  updated_at: string;
}

export interface WorkflowRuleCreate {
  name: string;
  description?: string | null;
  is_active?: boolean;
  trigger_entity: string;
  trigger_event: string;
  conditions?: Record<string, unknown> | null;
  actions?: Record<string, unknown>[] | null;
}

export interface WorkflowRuleUpdate {
  name?: string | null;
  description?: string | null;
  is_active?: boolean | null;
  trigger_entity?: string | null;
  trigger_event?: string | null;
  conditions?: Record<string, unknown> | null;
  actions?: Record<string, unknown>[] | null;
}

export interface WorkflowExecution {
  id: number;
  rule_id: number;
  entity_type: string;
  entity_id: number;
  status: string;
  result?: Record<string, unknown> | null;
  executed_at: string;
}

export interface WorkflowTestRequest {
  entity_type: string;
  entity_id: number;
}

// =============================================================================
// Sales Funnel Types
// =============================================================================

export interface FunnelStage {
  stage: string;
  count: number;
  color?: string | null;
}

export interface FunnelConversion {
  from_stage: string;
  to_stage: string;
  rate: number;
}

export interface SalesFunnelResponse {
  stages: FunnelStage[];
  conversions: FunnelConversion[];
  avg_days_in_stage: Record<string, number | null>;
}

// =============================================================================
// Audit / Change History Types
// =============================================================================

export interface AuditChangeDetail {
  field: string;
  old_value: unknown;
  new_value: unknown;
}

export interface AuditLogEntry {
  id: number;
  entity_type: string;
  entity_id: number;
  action: string;
  changes: AuditChangeDetail[];
  user_id: number;
  user_name?: string;
  user_email?: string;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// =============================================================================
// Comment / Team Collaboration Types
// =============================================================================

export interface CommentCreate {
  content: string;
  entity_type: string;
  entity_id: number;
  parent_id?: number | null;
  is_internal?: boolean;
}

export interface CommentUpdate {
  content: string;
}

export interface Comment {
  id: number;
  content: string;
  entity_type: string;
  entity_id: number;
  parent_id: number | null;
  is_internal: boolean;
  user_id: number;
  user_name?: string;
  user_email?: string;
  mentioned_users: string[];
  replies: Comment[];
  created_at: string;
  updated_at: string;
}

export interface CommentListResponse {
  items: Comment[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface CommentFilters {
  entity_type: string;
  entity_id: number;
  page?: number;
  page_size?: number;
}

// =============================================================================
// Pipeline (Multiple Pipelines) Types
// =============================================================================

export interface PipelineStageInPipeline {
  id: number;
  name: string;
  order: number;
  color: string | null;
  probability: number;
  is_won: boolean;
  is_lost: boolean;
}

export interface Pipeline {
  id: number;
  name: string;
  description: string | null;
  is_default: boolean;
  is_active: boolean;
  stages: PipelineStageInPipeline[];
  created_at: string;
  updated_at: string;
}

export interface PipelineCreate {
  name: string;
  description?: string;
  is_default?: boolean;
}

export interface PipelineUpdate {
  name?: string;
  description?: string;
  is_default?: boolean;
  is_active?: boolean;
}

export interface PipelineListResponse {
  items: Pipeline[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// =============================================================================
// Role & Permission Types
// =============================================================================

export interface Role {
  id: number;
  name: string;
  description?: string;
  permissions?: Record<string, string[]>;
  created_at?: string;
  updated_at?: string;
}

export interface UserPermissions {
  role: string;
  permissions: Record<string, string[]>;
}

export interface UserRoleAssign {
  user_id: number;
  role_id: number;
}

// =============================================================================
// Assignment Rule Types
// =============================================================================

export interface AssignmentRule {
  id: number;
  name: string;
  assignment_type: 'round_robin' | 'load_balance';
  user_ids: number[];
  filters?: Record<string, unknown> | null;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface AssignmentRuleCreate {
  name: string;
  assignment_type: 'round_robin' | 'load_balance';
  user_ids: number[];
  filters?: Record<string, unknown> | null;
  is_active?: boolean;
}

export interface AssignmentRuleUpdate {
  name?: string;
  assignment_type?: 'round_robin' | 'load_balance';
  user_ids?: number[];
  filters?: Record<string, unknown> | null;
  is_active?: boolean;
}

export interface AssignmentStats {
  user_id: number;
  assigned_count: number;
  active_leads_count?: number;
  period?: string;
}

// =============================================================================
// Webhook Types
// =============================================================================

export interface Webhook {
  id: number;
  name?: string;
  url: string;
  events: string[];
  is_active: boolean;
  secret?: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

export interface WebhookCreate {
  name?: string;
  url: string;
  events: string[];
  is_active?: boolean;
  secret?: string;
  description?: string;
}

export interface WebhookUpdate {
  name?: string;
  url?: string;
  events?: string[];
  is_active?: boolean;
  secret?: string;
  description?: string;
}

export interface WebhookDelivery {
  id: number;
  webhook_id: number;
  event: string;
  event_type?: string;
  status: string;
  response_code?: number;
  response_body?: string;
  attempted_at?: string;
  created_at?: string;
}

// =============================================================================
// Sequence Types
// =============================================================================

export interface SequenceStep {
  step_number: number;
  type: 'email' | 'task' | 'wait';
  delay_days: number;
  template_id?: number;
  task_description?: string;
}

export interface Sequence {
  id: number;
  name: string;
  description?: string;
  steps: SequenceStep[];
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface SequenceCreate {
  name: string;
  description?: string;
  steps: SequenceStep[];
  is_active?: boolean;
}

export interface SequenceUpdate {
  name?: string;
  description?: string;
  steps?: SequenceStep[];
  is_active?: boolean;
}

export interface SequenceEnrollment {
  id: number;
  sequence_id: number;
  contact_id: number;
  current_step: number;
  status: 'active' | 'paused' | 'completed' | 'cancelled';
  created_at?: string;
  updated_at?: string;
}

export interface ProcessDueResult {
  processed: number;
  errors: number;
}

// =============================================================================
// Admin Dashboard Types
// =============================================================================

export interface AdminUser {
  id: number;
  email: string;
  full_name: string;
  role: string;
  is_active: boolean;
  is_superuser: boolean;
  last_login?: string | null;
  created_at?: string | null;
  lead_count: number;
  contact_count: number;
  opportunity_count: number;
}

export interface AdminUserUpdate {
  role?: string;
  is_active?: boolean;
  email?: string;
  full_name?: string;
}

export interface AssignRoleRequest {
  role: string;
}

export interface SystemStats {
  total_users: number;
  total_contacts: number;
  total_companies: number;
  total_leads: number;
  total_opportunities: number;
  total_quotes: number;
  total_proposals: number;
  total_payments: number;
  active_users_7d: number;
}

export interface TeamMemberOverview {
  user_id: number;
  user_name: string;
  role: string;
  lead_count: number;
  opportunity_count: number;
  total_pipeline_value: number;
  won_deals: number;
}

export interface ActivityFeedEntry {
  id: number;
  entity_type: string;
  entity_id: number;
  action: string;
  user_id?: number | null;
  user_name?: string | null;
  timestamp: string;
  changes?: Record<string, unknown> | null;
}

// =============================================================================
// Contract Types
// =============================================================================

export interface ContractCreate {
  title: string;
  contact_id?: number | null;
  company_id?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  scope?: string | null;
  value?: number | null;
  currency?: string;
  status?: string;
  owner_id?: number | null;
}

export interface ContractUpdate {
  title?: string | null;
  contact_id?: number | null;
  company_id?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  scope?: string | null;
  value?: number | null;
  currency?: string | null;
  status?: string | null;
  owner_id?: number | null;
}

export interface Contract {
  id: number;
  title: string;
  contact_id?: number | null;
  company_id?: number | null;
  start_date?: string | null;
  end_date?: string | null;
  scope?: string | null;
  value?: number | null;
  currency: string;
  status: string;
  owner_id?: number | null;
  created_at: string;
  updated_at: string;
  contact?: ContactBrief | null;
  company?: CompanyBrief | null;
}

export type ContractListResponse = PaginatedResponse<Contract>;

export interface ContractFilters {
  page?: number;
  page_size?: number;
  contact_id?: number;
  company_id?: number;
  status?: string;
  owner_id?: number;
}
