/**
 * Auth Types
 */

export interface User {
  id: number;
  email: string;
  full_name: string;
  phone?: string | null;
  job_title?: string | null;
  is_active: boolean;
  is_superuser: boolean;
  // Backend includes the user's primary role on /auth/users responses;
  // RolesSection's last-admin guard reads it. Optional to keep older
  // payloads compatible.
  role?: string;
  avatar_url?: string | null;
  created_at: string;
  last_login?: string | null;
}

export interface UserUpdate {
  full_name?: string | null;
  phone?: string | null;
  job_title?: string | null;
  avatar_url?: string | null;
}

export interface TenantInfo {
  tenant_id: number;
  tenant_slug: string;
  company_name: string | null;
  role: string;
  is_primary: boolean;
  primary_color: string | null;
  secondary_color: string | null;
  accent_color: string | null;
  logo_url: string | null;
}

export interface Token {
  access_token: string;
  token_type: string;
  tenants?: TenantInfo[] | null;
}
