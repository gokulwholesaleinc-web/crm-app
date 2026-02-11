/**
 * Timeline component showing activities
 */

import { format, isToday, isYesterday } from 'date-fns';
import clsx from 'clsx';
import {
  PhoneIcon,
  EnvelopeIcon,
  CalendarIcon,
  ClipboardDocumentCheckIcon,
  DocumentTextIcon,
} from '@heroicons/react/24/outline';
import { CheckCircleIcon } from '@heroicons/react/24/solid';
import { Spinner } from '../../../components/ui/Spinner';
import type { TimelineItem } from '../../../types';

interface ActivityTimelineProps {
  items: TimelineItem[];
  isLoading?: boolean;
  onActivityClick?: (activity: TimelineItem) => void;
  onComplete?: (id: number) => void;
  emptyMessage?: string;
}

const activityIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  call: PhoneIcon,
  email: EnvelopeIcon,
  meeting: CalendarIcon,
  task: ClipboardDocumentCheckIcon,
  note: DocumentTextIcon,
};

const defaultColors = { bg: 'bg-gray-500', ring: 'ring-gray-100', text: 'text-gray-600' };

const activityColors: Record<string, { bg: string; ring: string; text: string }> = {
  call: { bg: 'bg-blue-500', ring: 'ring-blue-100', text: 'text-blue-600' },
  email: { bg: 'bg-purple-500', ring: 'ring-purple-100', text: 'text-purple-600' },
  meeting: { bg: 'bg-green-500', ring: 'ring-green-100', text: 'text-green-600' },
  task: { bg: 'bg-yellow-500', ring: 'ring-yellow-100', text: 'text-yellow-600' },
  note: defaultColors,
};

function formatDateHeader(dateString: string): string {
  const date = new Date(dateString);
  if (isToday(date)) return 'Today';
  if (isYesterday(date)) return 'Yesterday';
  return format(date, 'EEEE, MMMM d, yyyy');
}

function formatTime(dateString: string): string {
  try {
    return format(new Date(dateString), 'h:mm a');
  } catch {
    return '';
  }
}

interface GroupedActivities {
  date: string;
  dateLabel: string;
  items: TimelineItem[];
}

function groupByDate(items: TimelineItem[]): GroupedActivities[] {
  const groups: Map<string, TimelineItem[]> = new Map();

  items.forEach((item) => {
    const dateKey = format(new Date(item.created_at), 'yyyy-MM-dd');
    const existing = groups.get(dateKey) || [];
    groups.set(dateKey, [...existing, item]);
  });

  return Array.from(groups.entries())
    .map(([date, groupItems]) => ({
      date,
      dateLabel: formatDateHeader(date),
      items: [...groupItems].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      ),
    }))
    .sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
}

function TimelineEntry({
  item,
  isLast,
  onActivityClick,
  onComplete,
}: {
  item: TimelineItem;
  isLast: boolean;
  onActivityClick?: (activity: TimelineItem) => void;
  onComplete?: (id: number) => void;
}) {
  const Icon = activityIcons[item.activity_type] ?? DocumentTextIcon;
  const colors = activityColors[item.activity_type] ?? defaultColors;

  return (
    <div className="relative pb-4 sm:pb-6">
      {!isLast && (
        <span
          className="absolute left-3 sm:left-4 top-8 sm:top-10 -ml-px h-full w-0.5 bg-gray-200 dark:bg-gray-700"
          aria-hidden="true"
        />
      )}
      <div className="relative flex items-start space-x-2 sm:space-x-3">
        <div className="relative flex-shrink-0">
          <div
            className={clsx(
              'flex h-6 w-6 sm:h-8 sm:w-8 items-center justify-center rounded-full ring-2 sm:ring-4',
              item.is_completed ? 'bg-green-500 ring-green-100' : colors.bg,
              colors.ring
            )}
          >
            {item.is_completed ? (
              <CheckCircleIcon className="h-3 w-3 sm:h-4 sm:w-4 text-white" />
            ) : (
              <Icon className="h-3 w-3 sm:h-4 sm:w-4 text-white" />
            )}
          </div>
        </div>
        <div className="min-w-0 flex-1">
          <div
            className={clsx(
              'bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-2.5 sm:p-3 shadow-sm transition-all',
              onActivityClick && 'cursor-pointer hover:shadow-md hover:border-gray-300 dark:hover:border-gray-600 active:bg-gray-50 dark:active:bg-gray-700'
            )}
            onClick={() => onActivityClick?.(item)}
          >
            {/* Header - stacks on mobile */}
            <div className="flex flex-col xs:flex-row xs:items-center xs:justify-between gap-1 xs:gap-2">
              <div className="flex items-center gap-1.5 sm:gap-2 flex-wrap">
                <span
                  className={clsx(
                    'text-[10px] sm:text-xs font-medium px-1.5 sm:px-2 py-0.5 rounded-full',
                    item.is_completed
                      ? 'bg-green-100 text-green-700'
                      : `${colors.text} bg-opacity-10`
                  )}
                  style={
                    !item.is_completed
                      ? { backgroundColor: `${colors.text.replace('text-', '')}15` }
                      : undefined
                  }
                >
                  {item.activity_type.charAt(0).toUpperCase() + item.activity_type.slice(1)}
                </span>
                {item.priority !== 'normal' && (
                  <span
                    className={clsx(
                      'text-[10px] sm:text-xs font-medium',
                      item.priority === 'high' && 'text-orange-500',
                      item.priority === 'urgent' && 'text-red-500',
                      item.priority === 'low' && 'text-gray-400'
                    )}
                  >
                    {item.priority.toUpperCase()}
                  </span>
                )}
              </div>
              <span className="text-[10px] sm:text-xs text-gray-500">{formatTime(item.created_at)}</span>
            </div>
            <p
              className={clsx(
                'mt-1 text-xs sm:text-sm font-medium text-gray-900 dark:text-gray-100',
                item.is_completed && 'line-through text-gray-500'
              )}
            >
              {item.subject}
            </p>
            {item.description && (
              <p className="mt-1 text-xs sm:text-sm text-gray-600 dark:text-gray-400 line-clamp-2">{item.description}</p>
            )}
            {(item.call_duration_minutes || item.call_outcome || item.meeting_location) && (
              <div className="mt-1.5 sm:mt-2 flex flex-wrap gap-1.5 sm:gap-2 text-[10px] sm:text-xs text-gray-500">
                {item.call_duration_minutes && (
                  <span className="bg-gray-100 dark:bg-gray-700 px-1.5 sm:px-2 py-0.5 rounded">
                    {item.call_duration_minutes} min
                  </span>
                )}
                {item.call_outcome && (
                  <span className="bg-gray-100 dark:bg-gray-700 px-1.5 sm:px-2 py-0.5 rounded">
                    {item.call_outcome.replace('_', ' ')}
                  </span>
                )}
                {item.meeting_location && (
                  <span className="bg-gray-100 px-1.5 sm:px-2 py-0.5 rounded truncate max-w-[150px] sm:max-w-none">
                    @ {item.meeting_location}
                  </span>
                )}
              </div>
            )}
            {!item.is_completed && onComplete && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onComplete(item.id);
                }}
                className="mt-2 text-xs text-gray-500 hover:text-green-600 active:text-green-700 transition-colors py-1 -my-1"
              >
                Mark as complete
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function ActivityTimeline({
  items,
  isLoading,
  onActivityClick,
  onComplete,
  emptyMessage = 'No activities yet',
}: ActivityTimelineProps) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8 sm:py-12">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!items || items.length === 0) {
    return (
      <div className="text-center py-8 sm:py-12">
        <DocumentTextIcon className="mx-auto h-10 w-10 sm:h-12 sm:w-12 text-gray-400" />
        <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">No activities</h3>
        <p className="mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">{emptyMessage}</p>
      </div>
    );
  }

  const groupedActivities = groupByDate(items);

  return (
    <div className="flow-root">
      {groupedActivities.map((group, groupIndex) => (
        <div key={group.date} className={groupIndex > 0 ? 'mt-4 sm:mt-6' : ''}>
          <h3 className="text-xs sm:text-sm font-semibold text-gray-900 dark:text-gray-100 mb-3 sm:mb-4 sticky top-0 bg-gray-50 dark:bg-gray-900 py-1 -mx-1 px-1 z-10">
            {group.dateLabel}
          </h3>
          <div className="pl-1 sm:pl-2">
            {group.items.map((item, itemIndex) => (
              <TimelineEntry
                key={item.id}
                item={item}
                isLast={itemIndex === group.items.length - 1}
                onActivityClick={onActivityClick}
                onComplete={onComplete}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default ActivityTimeline;
