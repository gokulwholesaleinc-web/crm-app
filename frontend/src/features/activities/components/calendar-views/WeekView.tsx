import clsx from 'clsx';
import type { CalendarActivity } from '../../../../api/activities';
import {
  ACTIVITY_COLORS,
  WEEKDAY_LABELS,
  formatDateKey,
  getWeekDays,
  timeFormatter,
} from './helpers';

interface WeekViewProps {
  currentDate: Date;
  today: string;
  activitiesByDate: Record<string, CalendarActivity[]>;
  onSelectActivity: (activity: CalendarActivity) => void;
}

export function WeekView({ currentDate, today, activitiesByDate, onSelectActivity }: WeekViewProps) {
  const days = getWeekDays(currentDate);

  return (
    <div className="grid grid-cols-7 border-t border-l border-gray-200 dark:border-gray-700">
      {days.map((day) => {
        const key = formatDateKey(day);
        const isToday = key === today;
        const dayActivities = activitiesByDate[key] ?? [];

        return (
          <div key={key} className="border-r border-b border-gray-200 dark:border-gray-700 min-h-[300px] p-2">
            <div className="text-center mb-2">
              <div className="text-xs text-gray-500 dark:text-gray-400 uppercase">{WEEKDAY_LABELS[day.getDay()]}</div>
              <div
                className={clsx(
                  'text-lg font-semibold inline-flex items-center justify-center w-9 h-9 rounded-full',
                  isToday && 'bg-primary-600 text-white',
                  !isToday && 'text-gray-900 dark:text-gray-100'
                )}
              >
                {day.getDate()}
              </div>
            </div>
            <div className="space-y-1">
              {dayActivities.map((act) => (
                <button
                  key={act.id}
                  className={clsx(
                    'block w-full text-left text-xs p-1.5 rounded border',
                    ACTIVITY_COLORS[act.activity_type] ?? ACTIVITY_COLORS.note,
                    act.is_completed && 'opacity-50 line-through'
                  )}
                  onClick={() => onSelectActivity(act)}
                >
                  <div className="font-medium truncate">{act.subject}</div>
                  {act.scheduled_at && (
                    <div className="text-xs opacity-75">
                      {timeFormatter.format(new Date(act.scheduled_at))}
                    </div>
                  )}
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
