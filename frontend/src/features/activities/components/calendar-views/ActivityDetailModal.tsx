import { Link } from 'react-router-dom';

const DATETIME_FMT = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });
const DATE_FMT = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' });
import { ArrowUpOnSquareIcon } from '@heroicons/react/24/outline';
import { Modal } from '../../../../components/ui';
import type { CalendarActivity } from '../../../../api/activities';
import { GOOGLE_SYNC_ENTITY_TYPE } from './helpers';
import clsx from 'clsx';

interface ActivityDetailModalProps {
  activity: CalendarActivity;
  onClose: () => void;
  connected: boolean;
  isPushing: boolean;
  onPush: (id: number) => void;
}

export function ActivityDetailModal({
  activity,
  onClose,
  connected,
  isPushing,
  onPush,
}: ActivityDetailModalProps) {
  return (
    <Modal isOpen onClose={onClose} title={activity.subject} size="md">
      <div className="space-y-4 p-4">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <span className="font-medium text-gray-500 dark:text-gray-400">Type</span>
            <p className="capitalize text-gray-900 dark:text-gray-100">{activity.activity_type}</p>
          </div>
          <div>
            <span className="font-medium text-gray-500 dark:text-gray-400">Source</span>
            <p className="text-gray-900 dark:text-gray-100">
              {activity.entity_type === GOOGLE_SYNC_ENTITY_TYPE ? 'Google Calendar' : 'CRM'}
            </p>
          </div>
          <div>
            <span className="font-medium text-gray-500 dark:text-gray-400">Priority</span>
            <p className="capitalize text-gray-900 dark:text-gray-100">{activity.priority}</p>
          </div>
          <div>
            <span className="font-medium text-gray-500 dark:text-gray-400">Status</span>
            <p className="text-gray-900 dark:text-gray-100">{activity.is_completed ? 'Completed' : 'Open'}</p>
          </div>
          {activity.scheduled_at && (
            <div>
              <span className="font-medium text-gray-500 dark:text-gray-400">Scheduled</span>
              <p className="text-gray-900 dark:text-gray-100">{DATETIME_FMT.format(new Date(activity.scheduled_at))}</p>
            </div>
          )}
          {activity.due_date && (
            <div>
              <span className="font-medium text-gray-500 dark:text-gray-400">Due Date</span>
              <p className="text-gray-900 dark:text-gray-100">{DATE_FMT.format(new Date(activity.due_date))}</p>
            </div>
          )}
          {activity.meeting_location && (
            <div>
              <span className="font-medium text-gray-500 dark:text-gray-400">Location</span>
              <p className="text-gray-900 dark:text-gray-100">{activity.meeting_location}</p>
            </div>
          )}
        </div>
        {activity.description && (
          <div className="text-sm">
            <span className="font-medium text-gray-500 dark:text-gray-400">Description</span>
            <p className="mt-1 text-gray-700 dark:text-gray-300">{activity.description}</p>
          </div>
        )}

        {activity.entity_type !== GOOGLE_SYNC_ENTITY_TYPE && (
          <div className="border-t pt-4 flex flex-col gap-1.5">
            <button
              type="button"
              disabled={!connected || isPushing}
              onClick={() => onPush(activity.id)}
              className={clsx(
                'inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500',
                connected
                  ? 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600'
                  : 'bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500 border-gray-200 dark:border-gray-700 cursor-not-allowed'
              )}
              aria-label="Push to Google Calendar"
            >
              {isPushing ? (
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                </svg>
              ) : (
                <ArrowUpOnSquareIcon className="h-4 w-4" aria-hidden="true" />
              )}
              Push to Google Calendar
            </button>
            {!connected && (
              <p className="text-xs text-gray-500 dark:text-gray-400">
                <Link to="/settings" className="underline hover:text-primary-600 dark:hover:text-primary-400">
                  Connect Google Calendar in Settings
                </Link>
                {' '}to push events.
              </p>
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}
