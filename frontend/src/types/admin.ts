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
// User Approval Types
// =============================================================================

export interface PendingUser {
  id: number;
  email: string;
  full_name: string;
  avatar_url?: string | null;
  created_at: string;
}

export interface RejectedEmail {
  id: number;
  email: string;
  rejected_by_id?: number | null;
  rejected_by_email?: string | null;
  rejected_at: string;
  reason?: string | null;
}
