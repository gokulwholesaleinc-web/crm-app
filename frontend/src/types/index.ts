/**
 * CRM Application TypeScript Types
 * Matches backend Pydantic schemas
 */

// =============================================================================
// Generic Types
// =============================================================================

/**
 * Generic paginated list response
 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

/**
 * Generic API error response
 */
export interface ApiError {
  detail: string;
  status_code?: number;
}

// =============================================================================
// Auth Types
// =============================================================================

export interface User {
  id: number;
  email: string;
  full_name: string;
  phone?: string | null;
  job_title?: string | null;
  is_active: boolean;
  is_superuser: boolean;
  avatar_url?: string | null;
  created_at: string;
  last_login?: string | null;
}

export interface UserCreate {
  email: string;
  full_name: string;
  password: string;
  phone?: string | null;
  job_title?: string | null;
}

export interface UserUpdate {
  full_name?: string | null;
  phone?: string | null;
  job_title?: string | null;
  avatar_url?: string | null;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface Token {
  access_token: string;
  token_type: string;
}

// =============================================================================
// Common / Shared Types
// =============================================================================

export interface TagBrief {
  id: number;
  name: string;
  color?: string | null;
}

export interface CompanyBrief {
  id: number;
  name: string;
}

export interface ContactBrief {
  id: number;
  full_name: string;
}

export interface Note {
  id: number;
  content: string;
  entity_type: string;
  entity_id: number;
  created_at: string;
  updated_at: string;
  created_by_id: number | null;
  author_name?: string | null;
}

export interface NoteCreate {
  content: string;
  entity_type: string;
  entity_id: number;
}

export interface NoteUpdate {
  content?: string | null;
}

export type NoteListResponse = PaginatedResponse<Note>;

export interface NoteFilters {
  page?: number;
  page_size?: number;
  entity_type?: string;
  entity_id?: number;
}

// =============================================================================
// Contact Types
// =============================================================================

export interface ContactBase {
  first_name: string;
  last_name: string;
  email?: string | null;
  phone?: string | null;
  mobile?: string | null;
  job_title?: string | null;
  department?: string | null;
  company_id?: number | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  linkedin_url?: string | null;
  twitter_handle?: string | null;
  description?: string | null;
  status: string;
  owner_id?: number | null;
}

export interface ContactCreate extends ContactBase {
  tag_ids?: number[] | null;
}

export interface ContactUpdate extends Partial<ContactBase> {
  tag_ids?: number[] | null;
}

export interface Contact extends ContactBase {
  id: number;
  full_name: string;
  avatar_url?: string | null;
  created_at: string;
  updated_at: string;
  company?: CompanyBrief | null;
  tags: TagBrief[];
}

export type ContactListResponse = PaginatedResponse<Contact>;

export interface ContactFilters {
  page?: number;
  page_size?: number;
  search?: string;
  company_id?: number;
  status?: string;
  owner_id?: number;
  tag_ids?: string;
}

// =============================================================================
// Company Types
// =============================================================================

export interface CompanyBase {
  name: string;
  website?: string | null;
  industry?: string | null;
  company_size?: string | null;
  phone?: string | null;
  email?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  annual_revenue?: number | null;
  employee_count?: number | null;
  linkedin_url?: string | null;
  twitter_handle?: string | null;
  description?: string | null;
  status: string;
  owner_id?: number | null;
}

export interface CompanyCreate extends CompanyBase {
  tag_ids?: number[] | null;
}

export interface CompanyUpdate extends Partial<CompanyBase> {
  tag_ids?: number[] | null;
}

export interface Company extends CompanyBase {
  id: number;
  logo_url?: string | null;
  created_at: string;
  updated_at: string;
  tags: TagBrief[];
  contact_count: number;
}

export type CompanyListResponse = PaginatedResponse<Company>;

export interface CompanyFilters {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  industry?: string;
  owner_id?: number;
  tag_ids?: string;
}

// =============================================================================
// Lead Types
// =============================================================================

export interface LeadSource {
  id: number;
  name: string;
  description?: string | null;
  is_active: boolean;
}

export interface LeadSourceCreate {
  name: string;
  description?: string | null;
  is_active?: boolean;
}

export interface LeadBase {
  first_name: string;
  last_name: string;
  email?: string | null;
  phone?: string | null;
  mobile?: string | null;
  job_title?: string | null;
  company_name?: string | null;
  website?: string | null;
  industry?: string | null;
  source_id?: number | null;
  source_details?: string | null;
  address_line1?: string | null;
  address_line2?: string | null;
  city?: string | null;
  state?: string | null;
  postal_code?: string | null;
  country?: string | null;
  description?: string | null;
  requirements?: string | null;
  budget_amount?: number | null;
  budget_currency: string;
  owner_id?: number | null;
}

export interface LeadCreate extends LeadBase {
  status?: string;
  tag_ids?: number[] | null;
}

export interface LeadUpdate extends Partial<LeadBase> {
  status?: string;
  tag_ids?: number[] | null;
}

export interface Lead extends LeadBase {
  id: number;
  full_name: string;
  status: string;
  score: number;
  score_factors?: string | null;
  created_at: string;
  updated_at: string;
  source?: LeadSource | null;
  tags: TagBrief[];
  converted_contact_id?: number | null;
  converted_opportunity_id?: number | null;
}

export type LeadListResponse = PaginatedResponse<Lead>;

export interface LeadFilters {
  page?: number;
  page_size?: number;
  search?: string;
  status?: string;
  source_id?: number;
  owner_id?: number;
  min_score?: number;
  tag_ids?: string;
}

// Lead Conversion Types
export interface LeadConvertToContactRequest {
  company_id?: number | null;
  create_company?: boolean;
}

export interface LeadConvertToOpportunityRequest {
  pipeline_stage_id: number;
  contact_id?: number | null;
  company_id?: number | null;
}

export interface LeadFullConversionRequest {
  pipeline_stage_id: number;
  create_company?: boolean;
}

export interface ConversionResponse {
  lead_id: number;
  contact_id?: number | null;
  company_id?: number | null;
  opportunity_id?: number | null;
  message: string;
}

// =============================================================================
// Opportunity Types
// =============================================================================

export interface PipelineStage {
  id: number;
  name: string;
  description?: string | null;
  order: number;
  color: string;
  probability: number;
  is_won: boolean;
  is_lost: boolean;
  is_active: boolean;
}

export interface PipelineStageCreate {
  name: string;
  description?: string | null;
  order?: number;
  color?: string;
  probability?: number;
  is_won?: boolean;
  is_lost?: boolean;
  is_active?: boolean;
}

export interface PipelineStageUpdate extends Partial<PipelineStageCreate> {}

export interface OpportunityBase {
  name: string;
  description?: string | null;
  pipeline_stage_id: number;
  amount?: number | null;
  currency: string;
  probability?: number | null;
  expected_close_date?: string | null;
  contact_id?: number | null;
  company_id?: number | null;
  source?: string | null;
  owner_id?: number | null;
}

export interface OpportunityCreate extends OpportunityBase {
  tag_ids?: number[] | null;
}

export interface OpportunityUpdate extends Partial<OpportunityBase> {
  actual_close_date?: string | null;
  loss_reason?: string | null;
  loss_notes?: string | null;
  tag_ids?: number[] | null;
}

export interface Opportunity extends OpportunityBase {
  id: number;
  actual_close_date?: string | null;
  loss_reason?: string | null;
  loss_notes?: string | null;
  weighted_amount?: number | null;
  created_at: string;
  updated_at: string;
  pipeline_stage: PipelineStage;
  contact?: ContactBrief | null;
  company?: CompanyBrief | null;
  tags: TagBrief[];
}

export type OpportunityListResponse = PaginatedResponse<Opportunity>;

export interface OpportunityFilters {
  page?: number;
  page_size?: number;
  search?: string;
  pipeline_stage_id?: number;
  contact_id?: number;
  company_id?: number;
  owner_id?: number;
  tag_ids?: string;
}

// Kanban Types
export interface KanbanOpportunity {
  id: number;
  name: string;
  amount?: number | null;
  currency: string;
  weighted_amount?: number | null;
  expected_close_date?: string | null;
  contact_name?: string | null;
  company_name?: string | null;
  owner_id?: number | null;
}

export interface KanbanStage {
  stage_id: number;
  stage_name: string;
  color: string;
  probability: number;
  is_won: boolean;
  is_lost: boolean;
  opportunities: KanbanOpportunity[];
  total_amount: number;
  total_weighted: number;
  count: number;
}

export interface KanbanResponse {
  stages: KanbanStage[];
}

export interface MoveOpportunityRequest {
  new_stage_id: number;
}

// Forecast Types
export interface ForecastPeriod {
  month: string;
  month_label: string;
  best_case: number;
  weighted: number;
  commit: number;
  opportunity_count: number;
}

export interface ForecastTotals {
  best_case: number;
  weighted: number;
  commit: number;
}

export interface ForecastResponse {
  periods: ForecastPeriod[];
  totals: ForecastTotals;
  currency: string;
}

export interface PipelineSummaryStage {
  count: number;
  value: number;
  weighted: number;
}

export interface PipelineSummaryResponse {
  total_opportunities: number;
  total_value: number;
  weighted_value: number;
  currency: string;
  by_stage: Record<string, PipelineSummaryStage>;
}

// =============================================================================
// Activity Types
// =============================================================================

export type ActivityType = 'call' | 'email' | 'meeting' | 'task' | 'note';
export type EntityType = 'contact' | 'company' | 'lead' | 'opportunity';
export type Priority = 'low' | 'normal' | 'high' | 'urgent';

export interface ActivityBase {
  activity_type: string;
  subject: string;
  description?: string | null;
  entity_type: string;
  entity_id: number;
  scheduled_at?: string | null;
  due_date?: string | null;
  priority: string;
  owner_id?: number | null;
  assigned_to_id?: number | null;
}

export interface ActivityCreate extends ActivityBase {
  // Call-specific
  call_duration_minutes?: number | null;
  call_outcome?: string | null;
  // Email-specific
  email_to?: string | null;
  email_cc?: string | null;
  // Meeting-specific
  meeting_location?: string | null;
  meeting_attendees?: string | null;
  // Task-specific
  task_reminder_at?: string | null;
}

export interface ActivityUpdate {
  subject?: string | null;
  description?: string | null;
  scheduled_at?: string | null;
  due_date?: string | null;
  priority?: string | null;
  is_completed?: boolean | null;
  completed_at?: string | null;
  owner_id?: number | null;
  assigned_to_id?: number | null;
  // Call-specific
  call_duration_minutes?: number | null;
  call_outcome?: string | null;
  // Email-specific
  email_to?: string | null;
  email_cc?: string | null;
  email_opened?: boolean | null;
  // Meeting-specific
  meeting_location?: string | null;
  meeting_attendees?: string | null;
  // Task-specific
  task_reminder_at?: string | null;
}

export interface Activity extends ActivityBase {
  id: number;
  is_completed: boolean;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
  // Call-specific
  call_duration_minutes?: number | null;
  call_outcome?: string | null;
  // Email-specific
  email_to?: string | null;
  email_cc?: string | null;
  email_opened?: boolean | null;
  // Meeting-specific
  meeting_location?: string | null;
  meeting_attendees?: string | null;
  // Task-specific
  task_reminder_at?: string | null;
}

export type ActivityListResponse = PaginatedResponse<Activity>;

export interface ActivityFilters {
  page?: number;
  page_size?: number;
  entity_type?: string;
  entity_id?: number;
  activity_type?: string;
  owner_id?: number;
  assigned_to_id?: number;
  is_completed?: boolean;
  priority?: string;
}

export interface TimelineItem {
  id: number;
  activity_type: string;
  subject: string;
  description?: string | null;
  entity_type: string;
  entity_id: number;
  scheduled_at?: string | null;
  due_date?: string | null;
  completed_at?: string | null;
  is_completed: boolean;
  priority: string;
  created_at: string;
  owner_id?: number | null;
  assigned_to_id?: number | null;
  call_duration_minutes?: number | null;
  call_outcome?: string | null;
  meeting_location?: string | null;
}

export interface TimelineResponse {
  items: TimelineItem[];
}

export interface CompleteActivityRequest {
  notes?: string | null;
}

// =============================================================================
// Campaign Types
// =============================================================================

export interface CampaignBase {
  name: string;
  description?: string | null;
  campaign_type: string;
  status: string;
  start_date?: string | null;
  end_date?: string | null;
  budget_amount?: number | null;
  actual_cost?: number | null;
  budget_currency: string;
  target_audience?: string | null;
  expected_revenue?: number | null;
  expected_response?: number | null;
  owner_id?: number | null;
}

export interface CampaignCreate extends CampaignBase {}

export interface CampaignUpdate extends Partial<CampaignBase> {
  actual_revenue?: number | null;
  num_sent?: number | null;
  num_responses?: number | null;
  num_converted?: number | null;
}

export interface Campaign extends CampaignBase {
  id: number;
  actual_revenue?: number | null;
  num_sent: number;
  num_responses: number;
  num_converted: number;
  response_rate?: number | null;
  conversion_rate?: number | null;
  roi?: number | null;
  created_at: string;
  updated_at: string;
}

export type CampaignListResponse = PaginatedResponse<Campaign>;

export interface CampaignFilters {
  page?: number;
  page_size?: number;
  search?: string;
  campaign_type?: string;
  status?: string;
  owner_id?: number;
}

// Campaign Member Types
export interface CampaignMemberBase {
  campaign_id: number;
  member_type: string;
  member_id: number;
  status: string;
}

export interface CampaignMemberCreate extends CampaignMemberBase {}

export interface CampaignMemberUpdate {
  status?: string | null;
  sent_at?: string | null;
  responded_at?: string | null;
  converted_at?: string | null;
  response_notes?: string | null;
}

export interface CampaignMember extends CampaignMemberBase {
  id: number;
  sent_at?: string | null;
  responded_at?: string | null;
  converted_at?: string | null;
  response_notes?: string | null;
}

export interface AddMembersRequest {
  member_type: string;
  member_ids: number[];
}

export interface AddMembersResponse {
  added: number;
  message: string;
}

export interface CampaignStats {
  total_members: number;
  pending: number;
  sent: number;
  responded: number;
  converted: number;
  response_rate?: number | null;
  conversion_rate?: number | null;
}

// =============================================================================
// Dashboard Types
// =============================================================================

export interface NumberCardData {
  id: string;
  label: string;
  value: number | string;
  format?: string | null;
  icon?: string | null;
  color: string;
  change?: number | null;
}

export interface ChartDataPoint {
  label: string;
  value: number | string;
  color?: string | null;
}

export interface ChartData {
  type: 'bar' | 'line' | 'pie' | 'funnel' | 'area';
  title: string;
  data: ChartDataPoint[];
}

export interface DashboardResponse {
  number_cards: NumberCardData[];
  charts: ChartData[];
}

export interface NumberCardConfig {
  id: number;
  name: string;
  label: string;
  description?: string | null;
  config: string;
  color: string;
  icon?: string | null;
  is_active: boolean;
  order: number;
  show_percentage_change: boolean;
}

export interface ChartConfig {
  id: number;
  name: string;
  label: string;
  description?: string | null;
  chart_type: string;
  config: string;
  is_active: boolean;
  order: number;
  width: 'half' | 'full';
}

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
export interface ImportResult {
  success: boolean;
  imported_count: number;
  errors: string[];
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
// Audit Log Types
// =============================================================================

export interface AuditChangeDetail {
  field: string;
  old_value?: string | null;
  new_value?: string | null;
}

export interface AuditLogEntry {
  id: number;
  entity_type: string;
  entity_id: number;
  action: string;
  changes?: AuditChangeDetail[] | null;
  user_id?: number | null;
  user_name?: string | null;
  user_email?: string | null;
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
// Comment Types
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
  parent_id?: number | null;
  is_internal: boolean;
  user_id: number;
  user_name?: string | null;
  user_email?: string | null;
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
  page?: number;
  page_size?: number;
  entity_type?: string;
  entity_id?: number;
}

// =============================================================================
// Pipeline Management Types
// =============================================================================

export interface PipelineStageInPipeline {
  id: number;
  name: string;
  order: number;
  color?: string | null;
  probability?: number | null;
  is_won: boolean;
  is_lost: boolean;
}

export interface Pipeline {
  id: number;
  name: string;
  description?: string | null;
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
