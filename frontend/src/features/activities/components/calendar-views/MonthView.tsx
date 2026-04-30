import clsx from 'clsx';
import type { CalendarActivity } from '../../../../api/activities';
import {
  ACTIVITY_COLORS,
  WEEKDAY_LABELS,
  formatDateKey,
  getMonthDays,
} from './helpers';

interface MonthViewProps {
  currentDate: Date;
  today: string;
  activitiesByDate: Record<string, CalendarActivity[]>;
  onSelectActivity: (activity: CalendarActivity) => void;
  onShowMore?: (date: Date) => void;
}

export function MonthView({ currentDate, today, activitiesByDate, onSelectActivity, onShowMore }: MonthViewProps) {
  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();
  const days = getMonthDays(year, month);

  return (
    <div className="grid grid-cols-7 border-t border-l border-gray-200 dark:border-gray-700">
      {WEEKDAY_LABELS.map((label) => (
        <div key={label} className="border-r border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 px-2 py-2 text-center text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
          {label}
        </div>
      ))}
      {days.map((day) => {
        const key = formatDateKey(day);
        const isCurrentMonth = day.getMonth() === month;
        const isToday = key === today;
        const dayActivities = activitiesByDate[key] ?? [];

        return (
          <div
            key={key}
            className={clsx(
              'border-r border-b border-gray-200 dark:border-gray-700 min-h-[100px] p-1 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors',
              !isCurrentMonth && 'bg-gray-50/50 dark:bg-gray-900/50'
            )}
          >
            <div className="flex items-center justify-between px-1">
              <span
                className={clsx(
                  'text-sm font-medium inline-flex items-center justify-center w-7 h-7 rounded-full',
                  isToday && 'bg-primary-600 text-white',
                  !isToday && isCurrentMonth && 'text-gray-900 dark:text-gray-100',
                  !isToday && !isCurrentMonth && 'text-gray-400 dark:text-gray-600'
                )}
              >
                {day.getDate()}
              </span>
              {dayActivities.length > 0 && (
                <span className="text-xs text-gray-400 dark:text-gray-500">{dayActivities.length}</span>
              )}
            </div>
            <div className="mt-1 space-y-0.5">
              {dayActivities.slice(0, 3).map((act) => (
                <button
                  key={act.id}
                  className={clsx(
                    'block w-full text-left text-xs px-1.5 py-0.5 rounded border truncate',
                    ACTIVITY_COLORS[act.activity_type] ?? ACTIVITY_COLORS.note,
                    act.is_completed && 'opacity-50 line-through'
                  )}
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectActivity(act);
                  }}
                  title={act.subject}
                >
                  {act.subject}
                </button>
              ))}
              {dayActivities.length > 3 && (
                <button
                  type="button"
                  onClick={() => onShowMore?.(day)}
                  className="text-xs text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded pl-1"
                  aria-label={`Show all events for ${day.toLocaleDateString()}`}
                >
                  +{dayActivities.length - 3} more
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
