/**
 * Hook for pushing a CRM activity to Google Calendar.
 * Wraps the pushToCalendar API call with toast feedback.
 */

import { useMutation } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { pushToCalendar } from '../api/integrations';

export interface UsePushToGoogleCalendarOptions {
  /** Called after a successful push */
  onSuccess?: (activityId: number) => void;
  /**
   * When true, suppresses built-in toasts so the caller can show its own.
   * Errors are still propagated as thrown exceptions.
   */
  silent?: boolean;
}

export function usePushToGoogleCalendar(options?: UsePushToGoogleCalendarOptions) {
  const mutation = useMutation({
    mutationFn: (activityId: number) => pushToCalendar(activityId),
    onSuccess: (_data, activityId) => {
      if (!options?.silent) {
        toast.success('Pushed to Google Calendar');
      }
      options?.onSuccess?.(activityId);
    },
    onError: (error: unknown) => {
      if (!options?.silent) {
        const detail =
          (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
          'Failed to push';
        toast.error(detail);
      }
    },
  });

  return {
    push: (activityId: number) => mutation.mutate(activityId),
    pushAsync: (activityId: number) => mutation.mutateAsync(activityId),
    isPushing: mutation.isPending,
  };
}
