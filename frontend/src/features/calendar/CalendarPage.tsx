import { Link } from 'react-router-dom';
import { ArrowPathIcon } from '@heroicons/react/24/outline';
import { useGoogleCalendarSync } from '../../hooks/useGoogleCalendarSync';
import { Button } from '../../components/ui/Button';
import CalendarView from '../activities/components/CalendarView';

function CalendarPage() {
  const { connected, isLoadingStatus, sync, isSyncing } = useGoogleCalendarSync();

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
          {!isLoadingStatus && (connected ? (
            <Button
              variant="primary"
              leftIcon={<ArrowPathIcon className="h-4 w-4" />}
              onClick={sync}
              disabled={isSyncing}
              isLoading={isSyncing}
            >
              Sync from Google
            </Button>
          ) : (
            <Link
              to="/settings"
              className="text-sm text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 font-medium"
            >
              Connect Google Calendar in Settings →
            </Link>
          ))}
        </div>
      </div>

      <CalendarView />
    </div>
  );
}

export default CalendarPage;
