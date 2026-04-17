import clsx from 'clsx';
import type { CalendarActivity } from '../../../../api/activities';
import { ACTIVITY_COLORS, formatDateKey } from './helpers';

interface DayViewProps {
  currentDate: Date;
  activitiesByDate: Record<string, CalendarActivity[]>;
  onSelectActivity: (activity: CalendarActivity) => void;
}

export function DayView({ currentDate, activitiesByDate, onSelectActivity }: DayViewProps) {
  const key = formatDateKey(currentDate);
  const dayActivities = activitiesByDate[key] ?? [];

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 min-h-[400px]">
      {dayActivities.length === 0 ? (
        <div className="text-center py-12 text-gray-500 dark:text-gray-400">
          <p>No activities scheduled for this day.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {dayActivities.map((act) => (
            <button
              key={act.id}
              className={clsx(
                'block w-full text-left p-3 rounded-lg border',
                ACTIVITY_COLORS[act.activity_type] ?? ACTIVITY_COLORS.note,
                act.is_completed && 'opacity-50'
              )}
              onClick={() => onSelectActivity(act)}
            >
              <div className="flex items-center justify-between">
                <span className="font-medium">{act.subject}</span>
                <span className="text-xs capitalize px-2 py-0.5 rounded-full bg-white/50 dark:bg-black/20">
                  {act.activity_type}
                </span>
              </div>
              {act.description && (
                <p className="text-sm mt-1 opacity-75 line-clamp-2">{act.description}</p>
              )}
              <div className="flex items-center gap-4 mt-2 text-xs opacity-75">
                {act.scheduled_at && (
                  <span>
                    {new Date(act.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                )}
                {act.meeting_location && <span>{act.meeting_location}</span>}
                <span className="capitalize">{act.priority} priority</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
