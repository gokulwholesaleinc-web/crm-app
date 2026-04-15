import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowPathIcon } from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { getCalendarStatus, syncCalendar } from '../../api/integrations';
import { Button } from '../../components/ui/Button';
import CalendarView from '../activities/components/CalendarView';

function CalendarPage() {
  const queryClient = useQueryClient();

  const { data: calendarStatus } = useQuery({
    queryKey: ['integrations', 'google-calendar', 'status'],
    queryFn: getCalendarStatus,
  });

  const syncMutation = useMutation({
    mutationFn: syncCalendar,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['calendar'] });
      queryClient.invalidateQueries({ queryKey: ['integrations', 'google-calendar', 'status'] });
      toast.success(`Synced ${data.synced} events from Google Calendar`);
    },
    onError: () => {
      toast.error('Failed to sync calendar');
    },
  });

  const connected = calendarStatus?.connected ?? false;

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Calendar</h1>
          <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 mt-1">
            Your activities and Google Calendar events
          </p>
        </div>
        <div className="flex items-center gap-3">
          {connected ? (
            <Button
              variant="primary"
              leftIcon={<ArrowPathIcon className="h-4 w-4" />}
              onClick={() => syncMutation.mutate()}
              disabled={syncMutation.isPending}
              isLoading={syncMutation.isPending}
              aria-label="Sync from Google Calendar"
            >
              Sync from Google
            </Button>
          ) : (
            calendarStatus !== undefined && (
              <Link
                to="/settings"
                className="text-sm text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 font-medium"
              >
                Connect Google Calendar in Settings →
              </Link>
            )
          )}
        </div>
      </div>

      <CalendarView />
    </div>
  );
}

export default CalendarPage;
