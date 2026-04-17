import clsx from 'clsx';
import type { CalendarActivity } from '../../../../api/activities';
import {
  MONTH_LABELS,
  WEEKDAY_MINI,
  formatDateKey,
  getMonthDays,
} from './helpers';

interface YearViewProps {
  currentDate: Date;
  today: string;
  activitiesByDate: Record<string, CalendarActivity[]>;
  onSelectMonth: (year: number, month: number) => void;
}

export function YearView({ currentDate, today, activitiesByDate, onSelectMonth }: YearViewProps) {
  const year = currentDate.getFullYear();

  const countsByMonth: number[] = Array(12).fill(0);
  for (const [key, acts] of Object.entries(activitiesByDate)) {
    const [y, m] = key.split('-').map(Number);
    if (y === year && typeof m === 'number') countsByMonth[m - 1] = (countsByMonth[m - 1] ?? 0) + acts.length;
  }
  const maxCount = Math.max(1, ...countsByMonth);

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 p-3">
      {MONTH_LABELS.map((label, monthIdx) => {
        const days = getMonthDays(year, monthIdx);
        const count = countsByMonth[monthIdx] ?? 0;
        const intensity = count / maxCount;
        const isCurrentMonth = year === new Date().getFullYear() && monthIdx === new Date().getMonth();

        return (
          <button
            key={label}
            onClick={() => onSelectMonth(year, monthIdx)}
            className={clsx(
              'text-left bg-white dark:bg-gray-800 border rounded-lg p-3 transition-colors hover:border-primary-400 dark:hover:border-primary-500',
              isCurrentMonth ? 'border-primary-500 dark:border-primary-500' : 'border-gray-200 dark:border-gray-700'
            )}
          >
            <div className="flex items-center justify-between mb-2">
              <span className={clsx('font-semibold', isCurrentMonth ? 'text-primary-600 dark:text-primary-400' : 'text-gray-900 dark:text-gray-100')}>
                {label}
              </span>
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {count} {count === 1 ? 'event' : 'events'}
              </span>
            </div>
            <div className="grid grid-cols-7 gap-px text-[10px]">
              {WEEKDAY_MINI.map((d, i) => (
                <div key={`${d}-${i}`} className="text-center text-gray-400 dark:text-gray-500 font-medium">
                  {d}
                </div>
              ))}
              {days.map((day, i) => {
                const key = formatDateKey(day);
                const isInMonth = day.getMonth() === monthIdx;
                const dayCount = (activitiesByDate[key] ?? []).length;
                const isToday = key === today;
                const heat = isInMonth && dayCount > 0 ? Math.min(1, dayCount / 5) : 0;

                return (
                  <div
                    key={`${key}-${i}`}
                    className={clsx(
                      'h-5 rounded flex items-center justify-center',
                      !isInMonth && 'text-gray-300 dark:text-gray-600',
                      isInMonth && dayCount === 0 && 'text-gray-500 dark:text-gray-400',
                      isToday && 'ring-1 ring-primary-500'
                    )}
                    style={
                      heat > 0
                        ? { backgroundColor: `rgba(37, 99, 235, ${0.15 + heat * 0.55})`, color: 'white' }
                        : undefined
                    }
                    title={dayCount > 0 ? `${dayCount} on ${key}` : undefined}
                  >
                    {day.getDate()}
                  </div>
                );
              })}
            </div>
            <div className="mt-2 h-1 rounded bg-gray-100 dark:bg-gray-700 overflow-hidden">
              <div
                className="h-full bg-primary-500"
                style={{ width: `${Math.round(intensity * 100)}%` }}
              />
            </div>
          </button>
        );
      })}
    </div>
  );
}
