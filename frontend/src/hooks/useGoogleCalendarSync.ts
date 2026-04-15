import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { getCalendarStatus, syncCalendar } from '../api/integrations';
import type { CalendarSyncStatus } from '../api/integrations';

export function useGoogleCalendarSync(): {
  status: CalendarSyncStatus | undefined;
  connected: boolean;
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
      toast.success(`Synced ${data.synced} events from Google Calendar`);
    },
    onError: () => {
      toast.error('Failed to sync calendar');
    },
  });

  return {
    status,
    connected: status?.connected ?? false,
    isLoadingStatus,
    sync: () => syncMutation.mutate(),
    isSyncing: syncMutation.isPending,
  };
}
