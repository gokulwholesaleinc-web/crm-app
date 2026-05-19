import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { showSuccess, showError } from '../utils/toast';
import { getCalendarStatus, syncCalendar } from '../api/integrations';
import type { CalendarConnectionState, CalendarSyncStatus } from '../api/integrations';
import type { ApiError } from '../types';

function asApiError(err: unknown): ApiError | null {
  if (typeof err !== 'object' || err === null) return null;
  const candidate = err as Partial<ApiError>;
  return typeof candidate.detail === 'string' ? (candidate as ApiError) : null;
}

export function useGoogleCalendarSync(): {
  status: CalendarSyncStatus | undefined;
  connected: boolean;
  state: CalendarConnectionState;
  isLoadingStatus: boolean;
  sync: () => void;
  isSyncing: boolean;
} {
  const queryClient = useQueryClient();

  const { data: status, isLoading: isLoadingStatus } = useQuery({
    queryKey: ['integrations', 'google-calendar', 'status'],
    queryFn: getCalendarStatus,
  });

  const syncMutation = useMutation({
    mutationFn: syncCalendar,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'google-calendar'] });
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
      showSuccess(`Synced ${data.synced} events from Google Calendar`);
    },
    onError: (err) => {
      // 401 from /sync = backend marked is_active=false. Invalidate the
      // status query so the UI flips from "Sync" to "Reconnect Google
      // Calendar" immediately, and surface the server's specific detail
      // instead of the previous generic "Failed to sync calendar"
      // string that left the user wondering whether to retry or reauth.
      const apiErr = asApiError(err);
      if (apiErr?.status_code === 401) {
        queryClient.invalidateQueries({ queryKey: ['integrations', 'google-calendar', 'status'] });
        showError(
          apiErr.detail ||
            'Google revoked our access — reconnect Google Calendar in Settings.',
        );
        return;
      }
      showError(apiErr?.detail || 'Failed to sync calendar');
    },
  });

  return {
    status,
    connected: status?.connected ?? false,
    state: status?.state ?? 'disconnected',
    isLoadingStatus,
    sync: () => syncMutation.mutate(),
    isSyncing: syncMutation.isPending,
  };
}
