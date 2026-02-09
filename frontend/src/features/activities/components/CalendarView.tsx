/**
 * Calendar view for activities - month/week/day views
 * Self-contained component using CSS Grid, no external calendar library.
 */

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline';
import clsx from 'clsx';
import { getCalendarActivities } from '../../../api/activities';
import type { CalendarActivity } from '../../../api/activities';

type CalendarViewMode = 'month' | 'week' | 'day';

const ACTIVITY_TYPE_COLORS: Record<string, string> = {
  call: 'bg-blue-100 text-blue-800 border-blue-200',
  email: 'bg-green-100 text-green-800 border-green-200',
  meeting: 'bg-purple-100 text-purple-800 border-purple-200',
  task: 'bg-orange-100 text-orange-800 border-orange-200',
  note: 'bg-gray-100 text-gray-800 border-gray-200',
};

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function formatDate(d: Date): string {
  return d.toISOString().split('T')[0];
}

function getDaysInMonth(year: number, month: number): Date[] {
  const days: Date[] = [];
  const date = new Date(year, month, 1);
  while (date.getMonth() === month) {
    days.push(new Date(date));
    date.setDate(date.getDate() + 1);
  }
  return days;
}

function getWeekDays(baseDate: Date): Date[] {
  const start = new Date(baseDate);
  start.setDate(start.getDate() - start.getDay());
  const days: Date[] = [];
  for (let i = 0; i < 7; i++) {
    days.push(new Date(start));
    start.setDate(start.getDate() + 1);
  }
  return days;
}

function ActivityBlock({ activity }: { activity: CalendarActivity }) {
  const colorClass = ACTIVITY_TYPE_COLORS[activity.activity_type] || ACTIVITY_TYPE_COLORS.note;

  return (
    <div
      className={clsx(
        'text-xs px-1.5 py-0.5 rounded border truncate cursor-default',
        colorClass,
        activity.is_completed && 'opacity-50 line-through'
      )}
      title={`${activity.activity_type}: ${activity.subject}`}
    >
      {activity.subject}
    </div>
  );
}

export default function CalendarView() {
  const today = new Date();
  const [currentDate, setCurrentDate] = useState(today);
  const [viewMode, setViewMode] = useState<CalendarViewMode>('month');

  const { startDate, endDate } = useMemo(() => {
    if (viewMode === 'month') {
      const start = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
      const end = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0);
      // Pad to full weeks
      start.setDate(start.getDate() - start.getDay());
      end.setDate(end.getDate() + (6 - end.getDay()));
      return { startDate: formatDate(start), endDate: formatDate(end) };
    } else if (viewMode === 'week') {
      const days = getWeekDays(currentDate);
      return { startDate: formatDate(days[0]), endDate: formatDate(days[6]) };
    } else {
      return { startDate: formatDate(currentDate), endDate: formatDate(currentDate) };
    }
  }, [currentDate, viewMode]);

  const { data, isLoading } = useQuery({
    queryKey: ['calendar-activities', startDate, endDate],
    queryFn: () => getCalendarActivities(startDate, endDate),
  });

  const navigate = (direction: number) => {
    const next = new Date(currentDate);
    if (viewMode === 'month') {
      next.setMonth(next.getMonth() + direction);
    } else if (viewMode === 'week') {
      next.setDate(next.getDate() + direction * 7);
    } else {
      next.setDate(next.getDate() + direction);
    }
    setCurrentDate(next);
  };

  const goToToday = () => setCurrentDate(new Date());

  const headerLabel = useMemo(() => {
    if (viewMode === 'month') {
      return currentDate.toLocaleString('default', { month: 'long', year: 'numeric' });
    } else if (viewMode === 'week') {
      const days = getWeekDays(currentDate);
      const start = days[0];
      const end = days[6];
      return `${start.toLocaleDateString('default', { month: 'short', day: 'numeric' })} - ${end.toLocaleDateString('default', { month: 'short', day: 'numeric', year: 'numeric' })}`;
    } else {
      return currentDate.toLocaleDateString('default', { weekday: 'long', month: 'long', day: 'numeric', year: 'numeric' });
    }
  }, [currentDate, viewMode]);

  const activitiesByDate = data?.dates || {};

  const renderMonthView = () => {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    const daysInMonth = getDaysInMonth(year, month);
    const firstDay = daysInMonth[0].getDay();
    const todayStr = formatDate(today);

    // Build grid cells: pad start with previous month days
    const cells: Array<{ date: Date; isCurrentMonth: boolean }> = [];
    for (let i = firstDay - 1; i >= 0; i--) {
      const d = new Date(year, month, -i);
      cells.push({ date: d, isCurrentMonth: false });
    }
    for (const d of daysInMonth) {
      cells.push({ date: d, isCurrentMonth: true });
    }
    // Pad end
    while (cells.length % 7 !== 0) {
      const lastDate = cells[cells.length - 1].date;
      const d = new Date(lastDate);
      d.setDate(d.getDate() + 1);
      cells.push({ date: d, isCurrentMonth: false });
    }

    return (
      <div>
        <div className="grid grid-cols-7 gap-px bg-gray-200 rounded-t-lg overflow-hidden">
          {DAY_NAMES.map((day) => (
            <div key={day} className="bg-gray-50 py-2 text-center text-xs font-medium text-gray-500">
              {day}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-px bg-gray-200 rounded-b-lg overflow-hidden">
          {cells.map(({ date, isCurrentMonth }, idx) => {
            const dateStr = formatDate(date);
            const dayActivities = activitiesByDate[dateStr] || [];
            const isToday = dateStr === todayStr;

            return (
              <div
                key={idx}
                className={clsx(
                  'bg-white min-h-[80px] sm:min-h-[100px] p-1',
                  !isCurrentMonth && 'bg-gray-50'
                )}
              >
                <div
                  className={clsx(
                    'text-xs sm:text-sm font-medium mb-1 w-6 h-6 flex items-center justify-center rounded-full',
                    isToday && 'bg-primary-600 text-white',
                    !isToday && isCurrentMonth && 'text-gray-900',
                    !isToday && !isCurrentMonth && 'text-gray-400'
                  )}
                >
                  {date.getDate()}
                </div>
                <div className="space-y-0.5 overflow-hidden max-h-[60px] sm:max-h-[80px]">
                  {dayActivities.slice(0, 3).map((act) => (
                    <ActivityBlock key={act.id} activity={act} />
                  ))}
                  {dayActivities.length > 3 && (
                    <div className="text-xs text-gray-500 pl-1">
                      +{dayActivities.length - 3} more
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };

  const renderWeekView = () => {
    const days = getWeekDays(currentDate);
    const todayStr = formatDate(today);

    return (
      <div className="grid grid-cols-7 gap-2">
        {days.map((date) => {
          const dateStr = formatDate(date);
          const dayActivities = activitiesByDate[dateStr] || [];
          const isToday = dateStr === todayStr;

          return (
            <div key={dateStr} className="min-h-[200px]">
              <div
                className={clsx(
                  'text-center py-2 rounded-t-lg',
                  isToday ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-700'
                )}
              >
                <div className="text-xs font-medium">{DAY_NAMES[date.getDay()]}</div>
                <div className="text-lg font-bold">{date.getDate()}</div>
              </div>
              <div className="border border-t-0 border-gray-200 rounded-b-lg p-2 space-y-1">
                {dayActivities.map((act) => (
                  <ActivityBlock key={act.id} activity={act} />
                ))}
                {dayActivities.length === 0 && (
                  <div className="text-xs text-gray-400 text-center py-4">No activities</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const renderDayView = () => {
    const dateStr = formatDate(currentDate);
    const dayActivities = activitiesByDate[dateStr] || [];

    return (
      <div className="bg-white rounded-lg border border-gray-200 p-4">
        {dayActivities.length === 0 ? (
          <div className="text-center py-12 text-gray-500">No activities scheduled for this day</div>
        ) : (
          <div className="space-y-3">
            {dayActivities.map((act) => {
              const colorClass = ACTIVITY_TYPE_COLORS[act.activity_type] || ACTIVITY_TYPE_COLORS.note;
              return (
                <div
                  key={act.id}
                  className={clsx('p-3 rounded-lg border', colorClass, act.is_completed && 'opacity-60')}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm">{act.subject}</span>
                    <span className="text-xs capitalize">{act.activity_type}</span>
                  </div>
                  {act.description && (
                    <p className="text-xs mt-1 opacity-75">{act.description}</p>
                  )}
                  <div className="text-xs mt-1 opacity-60">
                    {act.scheduled_at
                      ? new Date(act.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                      : act.due_date
                        ? `Due: ${act.due_date}`
                        : ''}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="space-y-4">
      {/* Calendar Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => navigate(-1)}
            className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors"
            aria-label="Previous"
          >
            <ChevronLeftIcon className="h-5 w-5 text-gray-600" />
          </button>
          <h2 className="text-lg font-semibold text-gray-900 min-w-[200px] text-center">
            {headerLabel}
          </h2>
          <button
            onClick={() => navigate(1)}
            className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors"
            aria-label="Next"
          >
            <ChevronRightIcon className="h-5 w-5 text-gray-600" />
          </button>
          <button
            onClick={goToToday}
            className="ml-2 px-3 py-1 text-sm rounded-lg border border-gray-300 hover:bg-gray-50 transition-colors"
          >
            Today
          </button>
        </div>

        <div className="flex items-center gap-1 bg-gray-100 rounded-lg p-0.5">
          {(['month', 'week', 'day'] as CalendarViewMode[]).map((mode) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              className={clsx(
                'px-3 py-1.5 text-sm font-medium rounded-md transition-colors capitalize',
                viewMode === mode
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              )}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      {/* Activity count */}
      {data && (
        <div className="text-sm text-gray-500">
          {data.total_activities} activit{data.total_activities === 1 ? 'y' : 'ies'} in view
        </div>
      )}

      {/* Calendar Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
        </div>
      ) : viewMode === 'month' ? (
        renderMonthView()
      ) : viewMode === 'week' ? (
        renderWeekView()
      ) : (
        renderDayView()
      )}
    </div>
  );
}
