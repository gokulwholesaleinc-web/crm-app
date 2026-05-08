/**
 * Account-scoped settings hooks (notifications + display preferences).
 *
 * Both update mutations toast on success and invalidate the matching query
 * so the form re-syncs to the server's authoritative shape (e.g. nullable
 * fields zeroed out, default fields backfilled).
 */

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthQuery } from './useAuthQuery';
import {
  accountApi,
  type AccountPreferencesUpdate,
  type NotificationPrefsUpdate,
} from '../api/account';
import { showSuccess } from '../utils/toast';

export const accountKeys = {
  all: ['account'] as const,
  notifications: () => ['account', 'notifications'] as const,
  preferences: () => ['account', 'preferences'] as const,
};

export function useNotificationPrefs() {
  return useAuthQuery({
    queryKey: accountKeys.notifications(),
    queryFn: accountApi.getNotificationPrefs,
  });
}

export function useUpdateNotificationPrefs() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: NotificationPrefsUpdate) =>
      accountApi.updateNotificationPrefs(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: accountKeys.notifications() });
      showSuccess('Saved');
    },
  });
}

export function useAccountPreferences() {
  return useAuthQuery({
    queryKey: accountKeys.preferences(),
    queryFn: accountApi.getAccountPreferences,
  });
}

export function useUpdateAccountPreferences() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: AccountPreferencesUpdate) =>
      accountApi.updateAccountPreferences(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: accountKeys.preferences() });
      showSuccess('Saved');
    },
  });
}
