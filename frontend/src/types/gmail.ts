export type EmailProvider = 'resend' | 'gmail';

export interface GmailConnection {
  id: number;
  email: string;
  scopes: string[];
  is_active: boolean;
  last_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface GmailStatus {
  connected: boolean;
  email: string | null;
  last_synced_at: string | null;
  last_error: string | null;
}

export interface GmailAuthorizeResponse {
  auth_url: string;
}
