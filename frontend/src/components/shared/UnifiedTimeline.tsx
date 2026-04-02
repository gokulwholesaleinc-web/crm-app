/**
 * Unified timeline component that shows activities, emails, and sequence events
 * for a given entity. Replaces or supplements the basic activity timeline.
 */

import { useQuery } from '@tanstack/react-query';
import { Spinner } from '../ui/Spinner';
import { getUnifiedTimeline } from '../../api/activities';
import type { UnifiedTimelineEvent } from '../../api/activities';
import {
  EnvelopeIcon,
  EnvelopeOpenIcon,
  CursorArrowRaysIcon,
  PhoneIcon,
  CalendarDaysIcon,
  ClipboardDocumentListIcon,
  ArrowPathIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline';

const EVENT_CONFIG: Record<string, { icon: React.ComponentType<{ className?: string }>; color: string; label: string }> = {
  activity: { icon: ClipboardDocumentListIcon, color: 'text-gray-600 bg-gray-100 dark:text-gray-400 dark:bg-gray-700', label: 'Activity' },
  email_sent: { icon: EnvelopeIcon, color: 'text-blue-600 bg-blue-100 dark:text-blue-400 dark:bg-blue-900/30', label: 'Email Sent' },
  email_opened: { icon: EnvelopeOpenIcon, color: 'text-green-600 bg-green-100 dark:text-green-400 dark:bg-green-900/30', label: 'Email Opened' },
  email_clicked: { icon: CursorArrowRaysIcon, color: 'text-purple-600 bg-purple-100 dark:text-purple-400 dark:bg-purple-900/30', label: 'Email Clicked' },
  sequence_step: { icon: ArrowPathIcon, color: 'text-amber-600 bg-amber-100 dark:text-amber-400 dark:bg-amber-900/30', label: 'Sequence' },
};

function TimelineEventCard({ event }: { event: UnifiedTimelineEvent }) {
  const config = EVENT_CONFIG[event.event_type] || EVENT_CONFIG.activity;
  const Icon = config.icon;

  // Use activity_type from metadata for more specific icons
  const activityType = event.metadata?.activity_type as string | undefined;
  let DisplayIcon = Icon;
  if (event.event_type === 'activity') {
    if (activityType === 'call') DisplayIcon = PhoneIcon;
    else if (activityType === 'meeting') DisplayIcon = CalendarDaysIcon;
    else if (activityType === 'task' && event.metadata?.is_completed) DisplayIcon = CheckCircleIcon;
  }

  const formattedDate = new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(event.timestamp));

  return (
    <div className="flex gap-3 py-3">
      <div className={`flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center ${config.color}`}>
        <DisplayIcon className="h-4 w-4" aria-hidden="true" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
            {event.subject}
          </p>
          <time className="text-xs text-gray-400 dark:text-gray-500 flex-shrink-0">
            {formattedDate}
          </time>
        </div>
        {event.description && (
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 truncate">
            {event.description}
          </p>
        )}
        <span className="inline-block mt-1 text-xs rounded bg-gray-100 dark:bg-gray-700 px-1.5 py-0.5 text-gray-500 dark:text-gray-400">
          {config.label}
        </span>
      </div>
    </div>
  );
}

interface UnifiedTimelineProps {
  entityType: string;
  entityId: number;
  limit?: number;
}

export function UnifiedTimeline({ entityType, entityId, limit = 50 }: UnifiedTimelineProps) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['unified-timeline', entityType, entityId, limit],
    queryFn: () => getUnifiedTimeline(entityType, entityId, limit),
    enabled: !!entityId,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Spinner size="sm" />
      </div>
    );
  }

  if (error || !data?.items?.length) {
    return (
      <div className="text-center py-8 text-sm text-gray-400 dark:text-gray-500">
        No timeline events yet
      </div>
    );
  }

  return (
    <div className="divide-y divide-gray-100 dark:divide-gray-700">
      {data.items.map((event, index) => (
        <TimelineEventCard key={`${event.event_type}-${event.id}-${index}`} event={event} />
      ))}
    </div>
  );
}
