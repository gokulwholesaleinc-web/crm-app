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
      items: groupItems.sort(
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
    <div className="relative pb-6">
      {!isLast && (
        <span
          className="absolute left-4 top-10 -ml-px h-full w-0.5 bg-gray-200"
          aria-hidden="true"
        />
      )}
      <div className="relative flex items-start space-x-3">
        <div className="relative">
          <div
            className={clsx(
              'flex h-8 w-8 items-center justify-center rounded-full ring-4',
              item.is_completed ? 'bg-green-500 ring-green-100' : colors.bg,
              colors.ring
            )}
          >
            {item.is_completed ? (
              <CheckCircleIcon className="h-4 w-4 text-white" />
            ) : (
              <Icon className="h-4 w-4 text-white" />
            )}
          </div>
        </div>
        <div className="min-w-0 flex-1">
          <div
            className={clsx(
              'bg-white rounded-lg border border-gray-200 p-3 shadow-sm transition-all',
              onActivityClick && 'cursor-pointer hover:shadow-md hover:border-gray-300'
            )}
            onClick={() => onActivityClick?.(item)}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span
                  className={clsx(
                    'text-xs font-medium px-2 py-0.5 rounded-full',
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
                      'text-xs font-medium',
                      item.priority === 'high' && 'text-orange-500',
                      item.priority === 'urgent' && 'text-red-500',
                      item.priority === 'low' && 'text-gray-400'
                    )}
                  >
                    {item.priority.toUpperCase()}
                  </span>
                )}
              </div>
              <span className="text-xs text-gray-500">{formatTime(item.created_at)}</span>
            </div>
            <p
              className={clsx(
                'mt-1 text-sm font-medium text-gray-900',
                item.is_completed && 'line-through text-gray-500'
              )}
            >
              {item.subject}
            </p>
            {item.description && (
              <p className="mt-1 text-sm text-gray-600 line-clamp-2">{item.description}</p>
            )}
            {(item.call_duration_minutes || item.call_outcome || item.meeting_location) && (
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-gray-500">
                {item.call_duration_minutes && (
                  <span className="bg-gray-100 px-2 py-0.5 rounded">
                    {item.call_duration_minutes} min
                  </span>
                )}
                {item.call_outcome && (
                  <span className="bg-gray-100 px-2 py-0.5 rounded">
                    {item.call_outcome.replace('_', ' ')}
                  </span>
                )}
                {item.meeting_location && (
                  <span className="bg-gray-100 px-2 py-0.5 rounded">@ {item.meeting_location}</span>
                )}
              </div>
            )}
            {!item.is_completed && onComplete && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onComplete(item.id);
                }}
                className="mt-2 text-xs text-gray-500 hover:text-green-600 transition-colors"
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
      <div className="flex items-center justify-center py-12">
        <Spinner size="lg" />
      </div>
    );
  }

  if (!items || items.length === 0) {
    return (
      <div className="text-center py-12">
        <DocumentTextIcon className="mx-auto h-12 w-12 text-gray-400" />
        <h3 className="mt-2 text-sm font-medium text-gray-900">No activities</h3>
        <p className="mt-1 text-sm text-gray-500">{emptyMessage}</p>
      </div>
    );
  }

  const groupedActivities = groupByDate(items);

  return (
    <div className="flow-root">
      {groupedActivities.map((group, groupIndex) => (
        <div key={group.date} className={groupIndex > 0 ? 'mt-6' : ''}>
          <h3 className="text-sm font-semibold text-gray-900 mb-4">{group.dateLabel}</h3>
          <div className="pl-2">
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
