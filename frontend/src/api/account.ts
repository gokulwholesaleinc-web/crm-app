/**
 * Account-scoped settings (notification preferences + display preferences).
 *
 * Backed by /api/account/notifications and /api/account/preferences. Both
 * endpoints accept partial PUT updates — callers do not need to send the
 * full object.
 */

import { apiClient } from './client';

export type EmailDigest = 'instant' | 'daily_8am' | 'off';

export interface EventChannelPrefs {
  in_app?: boolean;
  email?: boolean;
}

export interface NotificationPrefs {
  in_app_enabled: boolean;
  email_enabled: boolean;
  email_digest: EmailDigest;
  quiet_hours_enabled: boolean;
  quiet_hours_start: string | null;
  quiet_hours_end: string | null;
  event_matrix: Record<string, EventChannelPrefs>;
}

export type NotificationPrefsUpdate = Partial<NotificationPrefs>;

export type Locale = 'en-US' | 'en-GB' | 'es-MX';
export type DateFormat = 'MM/DD/YYYY' | 'DD/MM/YYYY' | 'YYYY-MM-DD';
export type TimeFormat = '12h' | '24h';
export type WeekStart = 'sunday' | 'monday';
export type CurrencyDisplay = 'USD' | 'EUR' | 'GBP' | 'CAD';
export type Theme = 'system' | 'light' | 'dark';
export type DefaultLanding =
  | '/dashboard'
  | '/leads'
  | '/pipeline'
  | '/contacts'
  | '/proposals';

export interface AccountGuideProgress {
  completed_guide_ids?: string[];
  first_run_dismissed_at?: string | null;
  disabled_at?: string | null;
  last_reset_at?: string | null;
}

export interface AccountPreferences {
  timezone: string;
  locale: Locale;
  date_format: DateFormat;
  time_format: TimeFormat;
  week_start: WeekStart;
  currency_display: CurrencyDisplay;
  theme: Theme;
  default_landing: DefaultLanding;
  guide_progress: AccountGuideProgress;
}

export type AccountPreferencesUpdate = Partial<AccountPreferences>;

export interface NotificationEventTypeMeta {
  key: string;
  label: string;
  description?: string;
}

// Render order for the matrix table. The gate is opt-in: any event key
// absent from the user's event_matrix is treated as OFF by notification_gate.py.
// Adding an event here without a matching backend gate_event call is safe
// (the UI will show a toggle but it won't suppress anything). The reverse
// is a silent leak — always add the backend gate key first.
export const NOTIFICATION_EVENT_TYPES: readonly NotificationEventTypeMeta[] = [
  { key: 'lead_assigned', label: 'Lead assigned to me' },
  { key: 'payment_received', label: 'Payment received' },
  { key: 'proposal_signed', label: 'Proposal signed' },
  // contract_signed / contract_expiring keys retired 2026-05-14 —
  // contracts router unmounted and the backend gate no longer fires
  // these events. Preferences rows with these keys are harmless dead
  // matrix entries.
  { key: 'task_due', label: 'Task due' },
  { key: 'mention', label: 'Mentioned in a comment' },
  { key: 'email_reply_received', label: 'Email reply received' },
] as const;

const NOTIF_BASE = '/api/account/notifications';
const PREFS_BASE = '/api/account/preferences';

export const getNotificationPrefs = async (): Promise<NotificationPrefs> => {
  const response = await apiClient.get<NotificationPrefs>(NOTIF_BASE);
  return response.data;
};

export const updateNotificationPrefs = async (
  data: NotificationPrefsUpdate,
): Promise<NotificationPrefs> => {
  const response = await apiClient.put<NotificationPrefs>(NOTIF_BASE, data);
  return response.data;
};

export const getAccountPreferences = async (): Promise<AccountPreferences> => {
  const response = await apiClient.get<AccountPreferences>(PREFS_BASE);
  return response.data;
};

export const updateAccountPreferences = async (
  data: AccountPreferencesUpdate,
): Promise<AccountPreferences> => {
  const response = await apiClient.put<AccountPreferences>(PREFS_BASE, data);
  return response.data;
};

export const accountApi = {
  getNotificationPrefs,
  updateNotificationPrefs,
  getAccountPreferences,
  updateAccountPreferences,
};
