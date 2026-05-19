import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { showSuccess, showError } from '../utils/toast';
import { extractApiErrorDetail } from '../utils/errors';
import { getCalendarStatus, syncCalendar } from '../api/integrations';
import type { CalendarConnectionState, CalendarSyncStatus } from '../api/integrations';
import type { ApiError } from '../types';

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
      // Three distinct failure modes the user can recover from in
      // different ways — surface them differently:
      //
      //   - 409 needs_reconnect — Google permanently revoked us. Flip
      //     the status query so the UI shows "Reconnect Google
      //     Calendar" instead of "Sync". (401 would trigger the
      //     apiClient's global auth-unauthorized logout — we route
      //     around it with 409 + X-Calendar-State header.)
      //   - No status_code — network/CORS/offline. Tell the user to
      //     check their connection so they don't waste time on a
      //     "Failed to sync" message they'd otherwise interpret as a
      //     backend bug.
      //   - Other — bubble the server detail straight through.
      const apiErr = err as Partial<ApiError> | null;
      if (apiErr?.status_code === 409) {
        queryClient.invalidateQueries({ queryKey: ['integrations', 'google-calendar', 'status'] });
        showError(
          extractApiErrorDetail(err) ||
            'Google revoked our access — reconnect Google Calendar in Settings.',
        );
        return;
      }
      if (apiErr?.status_code === undefined) {
        showError('Network error reaching the CRM — check your connection and retry.');
        return;
      }
      showError(extractApiErrorDetail(err) || 'Failed to sync calendar');
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
