/**
 * Integrations API — Google Calendar + Meta OAuth/sync
 */

import { apiClient } from './client';

// Google Calendar

export interface CalendarSyncStatus {
  connected: boolean;
  calendar_id: string | null;
  last_synced_at: string | null;
  synced_events_count: number;
}

export const getCalendarStatus = async (): Promise<CalendarSyncStatus> => {
  const response = await apiClient.get<CalendarSyncStatus>('/api/integrations/google-calendar/status');
  return response.data;
};

export const getCalendarAuthUrl = async (redirectUri: string): Promise<{ auth_url: string }> => {
  const response = await apiClient.post<{ auth_url: string }>('/api/integrations/google-calendar/connect', {
    redirect_uri: redirectUri,
  });
  return response.data;
};

export const calendarCallback = async (code: string, redirectUri: string): Promise<unknown> => {
  const response = await apiClient.post('/api/integrations/google-calendar/callback', {
    code,
    redirect_uri: redirectUri,
  });
  return response.data;
};

export const disconnectCalendar = async (): Promise<void> => {
  await apiClient.delete('/api/integrations/google-calendar/disconnect');
};

export const syncCalendar = async (): Promise<{ synced: number; events: unknown[] }> => {
  const response = await apiClient.post<{ synced: number; events: unknown[] }>('/api/integrations/google-calendar/sync');
  return response.data;
};

export const pushToCalendar = async (activityId: number): Promise<{ google_event_id: string }> => {
  const response = await apiClient.post<{ google_event_id: string }>('/api/integrations/google-calendar/push', {
    activity_id: activityId,
  });
  return response.data;
};

// Gmail

export type GmailConnectionState = 'connected' | 'needs_reconnect' | 'disconnected';

export interface GmailStatus {
  /** New canonical UI signal. Branch on this; `connected` is kept for
   * backwards compatibility with older clients. */
  state: GmailConnectionState;
  connected: boolean;
  email: string | null;
  last_synced_at: string | null;
  last_error: string | null;
}

export const getGmailStatus = async (): Promise<GmailStatus> => {
  const response = await apiClient.get<GmailStatus>('/api/integrations/gmail/status');
  return response.data;
};

export const getGmailAuthUrl = async (): Promise<{ auth_url: string }> => {
  const response = await apiClient.get<{ auth_url: string }>('/api/integrations/gmail/authorize');
  return response.data;
};

export const gmailCallback = async (code: string, state: string): Promise<unknown> => {
  const response = await apiClient.post('/api/integrations/gmail/callback', { code, state });
  return response.data;
};

export const disconnectGmail = async (): Promise<void> => {
  await apiClient.post('/api/integrations/gmail/disconnect');
};

export const syncGmail = async (): Promise<unknown> => {
  const response = await apiClient.post('/api/integrations/gmail/sync');
  return response.data;
};

export interface GmailBackfillStatus {
  status: 'none' | 'pending' | 'running' | 'complete' | 'failed';
  processed_count: number;
  total_count: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
}

export const backfillGmail = async (days = 365): Promise<GmailBackfillStatus> => {
  const response = await apiClient.post<GmailBackfillStatus>('/api/integrations/gmail/backfill', { days });
  return response.data;
};

export const getBackfillStatus = async (): Promise<GmailBackfillStatus> => {
  const response = await apiClient.get<GmailBackfillStatus>('/api/integrations/gmail/backfill/status');
  return response.data;
};

// Meta (Facebook/Instagram)

export interface MetaConnectionStatus {
  connected: boolean;
  scopes: string | null;
  token_expiry: string | null;
  pages: Array<{ id: string; name: string; category: string; fan_count: number }>;
}

export const getMetaStatus = async (): Promise<MetaConnectionStatus> => {
  const response = await apiClient.get<MetaConnectionStatus>('/api/meta/status');
  return response.data;
};

export const getMetaAuthUrl = async (redirectUri: string): Promise<{ auth_url: string }> => {
  const response = await apiClient.post<{ auth_url: string }>('/api/meta/connect', {
    redirect_uri: redirectUri,
  });
  return response.data;
};

export const metaCallback = async (code: string, redirectUri: string): Promise<unknown> => {
  const response = await apiClient.post('/api/meta/callback', { code, redirect_uri: redirectUri });
  return response.data;
};

export const disconnectMeta = async (): Promise<void> => {
  await apiClient.delete('/api/meta/disconnect');
};

export const syncInstagram = async (companyId: number, pageId: string): Promise<unknown> => {
  const response = await apiClient.post(`/api/meta/companies/${companyId}/sync-instagram`, { page_id: pageId });
  return response.data;
};
