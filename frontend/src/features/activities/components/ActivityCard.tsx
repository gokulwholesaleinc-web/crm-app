/**
 * Activity display card with type-specific icons
 */

import { format, formatDistanceToNow } from 'date-fns';
import clsx from 'clsx';
import {
  PhoneIcon,
  EnvelopeIcon,
  CalendarIcon,
  ClipboardDocumentCheckIcon,
  DocumentTextIcon,
  CheckCircleIcon,
  ClockIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { CheckCircleIcon as CheckCircleSolidIcon } from '@heroicons/react/24/solid';
import type { Activity, TimelineItem } from '../../../types';

type ActivityData = Activity | TimelineItem;

interface ActivityCardProps {
  activity: ActivityData;
  onComplete?: (id: number) => void;
  onEdit?: (activity: ActivityData) => void;
  onDelete?: (id: number) => void;
  compact?: boolean;
}

const activityIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  call: PhoneIcon,
  email: EnvelopeIcon,
  meeting: CalendarIcon,
  task: ClipboardDocumentCheckIcon,
  note: DocumentTextIcon,
};

const defaultColors = { bg: 'bg-gray-50', text: 'text-gray-600', border: 'border-gray-200' };

const activityColors: Record<string, { bg: string; text: string; border: string }> = {
  call: { bg: 'bg-blue-50', text: 'text-blue-600', border: 'border-blue-200' },
  email: { bg: 'bg-purple-50', text: 'text-purple-600', border: 'border-purple-200' },
  meeting: { bg: 'bg-green-50', text: 'text-green-600', border: 'border-green-200' },
  task: { bg: 'bg-yellow-50', text: 'text-yellow-600', border: 'border-yellow-200' },
  note: defaultColors,
};

const priorityColors: Record<string, string> = {
  low: 'text-gray-500',
  normal: 'text-blue-500',
  high: 'text-orange-500',
  urgent: 'text-red-500',
};

export function ActivityCard({
  activity,
  onComplete,
  onEdit,
  onDelete,
  compact = false,
}: ActivityCardProps) {
  const Icon = activityIcons[activity.activity_type] ?? DocumentTextIcon;
  const colors = activityColors[activity.activity_type] ?? defaultColors;

  const isOverdue =
    !activity.is_completed &&
    activity.due_date &&
    new Date(activity.due_date) < new Date();

  const formatDate = (dateString: string | null | undefined) => {
    if (!dateString) return null;
    try {
      return format(new Date(dateString), 'MMM d, yyyy h:mm a');
    } catch {
      return dateString;
    }
  };

  const getRelativeTime = (dateString: string) => {
    try {
      return formatDistanceToNow(new Date(dateString), { addSuffix: true });
    } catch {
      return dateString;
    }
  };

  const renderCallDetails = () => {
    if (activity.activity_type !== 'call') return null;
    const parts = [];
    if (activity.call_duration_minutes) {
      parts.push(`${activity.call_duration_minutes} min`);
    }
    if (activity.call_outcome) {
      parts.push(activity.call_outcome.replace('_', ' '));
    }
    return parts.length > 0 ? (
      <span className="text-xs text-gray-500 ml-2">{parts.join(' - ')}</span>
    ) : null;
  };

  const renderMeetingDetails = () => {
    if (activity.activity_type !== 'meeting' || !activity.meeting_location) return null;
    return (
      <span className="text-xs text-gray-500 ml-2">@ {activity.meeting_location}</span>
    );
  };

  if (compact) {
    return (
      <div
        className={clsx(
          'flex items-start gap-3 p-3 rounded-lg border transition-colors',
          colors.border,
          activity.is_completed ? 'bg-gray-50 opacity-75' : colors.bg
        )}
      >
        <div className={clsx('p-1.5 rounded-full', colors.bg)}>
          <Icon className={clsx('h-4 w-4', colors.text)} />
        </div>
        <div className="flex-1 min-w-0">
          <p
            className={clsx(
              'text-sm font-medium truncate',
              activity.is_completed && 'line-through text-gray-500'
            )}
          >
            {activity.subject}
          </p>
          <p className="text-xs text-gray-500 mt-0.5">
            {activity.created_at && getRelativeTime(activity.created_at)}
          </p>
        </div>
        {!activity.is_completed && onComplete && (
          <button
            onClick={() => onComplete(activity.id)}
            className="p-1 rounded hover:bg-gray-200 transition-colors"
            title="Mark as complete"
          >
            <CheckCircleIcon className="h-5 w-5 text-gray-400 hover:text-green-500" />
          </button>
        )}
        {activity.is_completed && (
          <CheckCircleSolidIcon className="h-5 w-5 text-green-500" />
        )}
      </div>
    );
  }

  return (
    <div
      className={clsx(
        'bg-white rounded-lg shadow-sm border p-4 transition-all hover:shadow-md',
        activity.is_completed && 'opacity-75'
      )}
    >
      <div className="flex items-start gap-4">
        <div className={clsx('p-2 rounded-lg', colors.bg)}>
          <Icon className={clsx('h-5 w-5', colors.text)} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h4
              className={clsx(
                'font-medium text-gray-900 truncate',
                activity.is_completed && 'line-through text-gray-500'
              )}
            >
              {activity.subject}
            </h4>
            <div className="flex items-center gap-2 flex-shrink-0">
              {activity.priority && activity.priority !== 'normal' && (
                <span className={clsx('text-xs font-medium', priorityColors[activity.priority])}>
                  {activity.priority.toUpperCase()}
                </span>
              )}
              {isOverdue && (
                <span className="flex items-center gap-1 text-xs text-red-600">
                  <ExclamationTriangleIcon className="h-4 w-4" />
                  Overdue
                </span>
              )}
            </div>
          </div>

          {activity.description && (
            <p className="text-sm text-gray-600 mt-1 line-clamp-2">{activity.description}</p>
          )}

          <div className="flex flex-wrap items-center gap-3 mt-2 text-xs text-gray-500">
            {activity.scheduled_at && (
              <span className="flex items-center gap-1">
                <ClockIcon className="h-3.5 w-3.5" />
                {formatDate(activity.scheduled_at)}
              </span>
            )}
            {activity.due_date && (
              <span className={clsx('flex items-center gap-1', isOverdue && 'text-red-600')}>
                <CalendarIcon className="h-3.5 w-3.5" />
                Due: {formatDate(activity.due_date)}
              </span>
            )}
            {renderCallDetails()}
            {renderMeetingDetails()}
          </div>

          {activity.completed_at && (
            <p className="text-xs text-green-600 mt-2 flex items-center gap-1">
              <CheckCircleSolidIcon className="h-3.5 w-3.5" />
              Completed {formatDate(activity.completed_at)}
            </p>
          )}
        </div>

        <div className="flex items-center gap-1">
          {!activity.is_completed && onComplete && (
            <button
              onClick={() => onComplete(activity.id)}
              className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors"
              title="Mark as complete"
            >
              <CheckCircleIcon className="h-5 w-5 text-gray-400 hover:text-green-500" />
            </button>
          )}
          {activity.is_completed && (
            <CheckCircleSolidIcon className="h-5 w-5 text-green-500" />
          )}
          {onEdit && (
            <button
              onClick={() => onEdit(activity)}
              className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors text-gray-400 hover:text-gray-600"
              title="Edit"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                />
              </svg>
            </button>
          )}
          {onDelete && (
            <button
              onClick={() => onDelete(activity.id)}
              className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors text-gray-400 hover:text-red-500"
              title="Delete"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default ActivityCard;
