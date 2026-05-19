// Audit / Change History Types

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
  changes: AuditChangeDetail[] | Record<string, unknown> | null;
  user_id: number | null;
  user_name?: string;
  user_email?: string;
  ip_address?: string | null;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogEntry[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// Comment / Team Collaboration Types

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
  author_name?: string | null;
  mentions: string[];
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

export interface AdminAuditFeedFilters {
  page?: number;
  page_size?: number;
  start_date?: string;
  end_date?: string;
  user_id?: number;
  entity_type?: string;
  entity_id?: number;
  action?: string;
  search?: string;
}

export type AdminAuditFeedItem = AuditLogEntry;

export interface AdminAuditFeedResponse {
  items: AdminAuditFeedItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface AdminAuditTotals {
  audit_events: number;
  active_crm_seconds: number;
  activities: number;
  calls: number;
  emails: number;
  security_events: number;
}

export interface AdminAuditUserSummary {
  user_id: number;
  user_name: string;
  user_email?: string | null;
  role?: string | null;
  active_crm_seconds: number;
  audit_events: number;
  calls: number;
  call_duration_minutes: number;
  emails: number;
  proposals_touched: number;
  opportunities_touched: number;
  last_active_at?: string | null;
}

export interface AdminAuditEntitySummary {
  entity_type: string;
  entity_id: number;
  label?: string | null;
  owner_id?: number | null;
  owner_name?: string | null;
  active_crm_seconds: number;
  activity_count: number;
  audit_count: number;
  last_touched_at?: string | null;
  last_touched_by_id?: number | null;
  last_touched_by_name?: string | null;
}

export interface AdminAuditSecurityEvent {
  id: string;
  severity: 'low' | 'medium' | 'high' | string;
  category: string;
  description: string;
  user_id?: number | null;
  user_name?: string | null;
  entity_type?: string | null;
  entity_id?: number | null;
  count: number;
  created_at: string;
}

export interface AdminAuditSummaryResponse {
  start_at?: string | null;
  end_at?: string | null;
  totals: AdminAuditTotals;
  users: AdminAuditUserSummary[];
  entities: AdminAuditEntitySummary[];
  security: AdminAuditSecurityEvent[];
}

export interface WorkSessionHeartbeatRequest {
  entity_type: string;
  entity_id: number;
  source?: string;
  metadata?: Record<string, unknown>;
}

export interface WorkSession {
  id: number;
  user_id?: number | null;
  user_name?: string | null;
  entity_type: string;
  entity_id: number;
  started_at: string;
  last_seen_at: string;
  ended_at?: string | null;
  duration_seconds: number;
  source: string;
  metadata?: Record<string, unknown> | null;
}

export interface AdminAuditUserDetail {
  summary: AdminAuditUserSummary;
  feed: AdminAuditFeedResponse;
  sessions: WorkSession[];
}

export interface AdminAuditEntityDetail {
  summary: AdminAuditEntitySummary;
  feed: AdminAuditFeedResponse;
  sessions: WorkSession[];
}
