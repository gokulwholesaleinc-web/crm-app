import { useMutation } from '@tanstack/react-query';
import { showSuccess, showError } from '../utils/toast';
import { pushToCalendar } from '../api/integrations';

export interface UsePushToGoogleCalendarOptions {
  onSuccess?: (activityId: number) => void;
  // When true, suppresses built-in toasts so the caller can show its own.
  silent?: boolean;
}

export function usePushToGoogleCalendar(options?: UsePushToGoogleCalendarOptions) {
  const mutation = useMutation({
    mutationFn: (activityId: number) => pushToCalendar(activityId),
    onSuccess: (_data, activityId) => {
      if (!options?.silent) {
        showSuccess('Pushed to Google Calendar');
      }
      options?.onSuccess?.(activityId);
    },
    onError: (error: unknown) => {
      if (!options?.silent) {
        const detail =
          (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          'Failed to push';
        showError(detail);
      }
    },
  });

  return {
    push: (activityId: number) => mutation.mutate(activityId),
    pushAsync: (activityId: number) => mutation.mutateAsync(activityId),
    isPushing: mutation.isPending,
  };
}
