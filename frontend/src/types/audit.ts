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
