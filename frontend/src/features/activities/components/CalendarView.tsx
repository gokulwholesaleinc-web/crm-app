import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline';
import { getCalendarActivities } from '../../../api/activities';
import type { CalendarActivity } from '../../../api/activities';
import { Spinner } from '../../../components/ui';
import { useGoogleCalendarSync } from '../../../hooks/useGoogleCalendarSync';
import { usePushToGoogleCalendar } from '../../../hooks/usePushToGoogleCalendar';
import clsx from 'clsx';
import {
  formatDateKey,
  getWeekDays,
  GOOGLE_SYNC_ENTITY_TYPE,
  type ViewMode,
  type SourceFilter,
} from './calendar-views/helpers';
import { YearView } from './calendar-views/YearView';
import { MonthView } from './calendar-views/MonthView';
import { WeekView } from './calendar-views/WeekView';
import { DayView } from './calendar-views/DayView';
import { AgendaView } from './calendar-views/AgendaView';
import { ActivityDetailModal } from './calendar-views/ActivityDetailModal';

function CalendarView() {
  const [viewMode, setViewMode] = useState<ViewMode>('month');
  const [currentDate, setCurrentDate] = useState(new Date());
  const [selectedActivity, setSelectedActivity] = useState<CalendarActivity | null>(null);
  const [activityTypeFilter, setActivityTypeFilter] = useState<string>('all');
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all');

  const { connected } = useGoogleCalendarSync();
  const { push: pushToCalendar, isPushing } = usePushToGoogleCalendar({
    onSuccess: () => setSelectedActivity(null),
  });

  const today = formatDateKey(new Date());

  const dateRange = useMemo(() => {
    if (viewMode === 'year') {
      const year = currentDate.getFullYear();
      return { start: `${year}-01-01`, end: `${year}-12-31` };
    } else if (viewMode === 'month') {
      const year = currentDate.getFullYear();
      const month = currentDate.getMonth();
      const start = new Date(year, month, 1);
      start.setDate(start.getDate() - start.getDay());
      const end = new Date(year, month + 1, 0);
      end.setDate(end.getDate() + (6 - end.getDay()));
      return { start: formatDateKey(start), end: formatDateKey(end) };
    } else if (viewMode === 'week') {
      const days = getWeekDays(currentDate);
      return { start: formatDateKey(days[0]!), end: formatDateKey(days[6]!) };
    } else if (viewMode === 'agenda') {
      const year = currentDate.getFullYear();
      const month = currentDate.getMonth();
      const start = new Date(year, month - 1, 1);
      const end = new Date(year, month + 2, 0);
      return { start: formatDateKey(start), end: formatDateKey(end) };
    } else {
      const key = formatDateKey(currentDate);
      return { start: key, end: key };
    }
  }, [viewMode, currentDate]);

  const apiActivityType = activityTypeFilter === 'all' ? undefined : activityTypeFilter;

  const { data: calendarData, isLoading } = useQuery({
    queryKey: ['calendar', dateRange.start, dateRange.end, apiActivityType],
    queryFn: () => getCalendarActivities(dateRange.start, dateRange.end, apiActivityType),
  });

  const activitiesByDate = useMemo(() => {
    const raw = calendarData?.dates ?? {};
    if (sourceFilter === 'all') return raw;
    const filtered: Record<string, CalendarActivity[]> = {};
    for (const [day, acts] of Object.entries(raw)) {
      const kept = acts.filter((a) =>
        sourceFilter === 'google'
          ? a.entity_type === GOOGLE_SYNC_ENTITY_TYPE
          : a.entity_type !== GOOGLE_SYNC_ENTITY_TYPE
      );
      if (kept.length) filtered[day] = kept;
    }
    return filtered;
  }, [calendarData, sourceFilter]);

  const visibleTotal = useMemo(
    () => Object.values(activitiesByDate).reduce((n, acts) => n + acts.length, 0),
    [activitiesByDate]
  );

  const navigate = (direction: -1 | 1) => {
    const d = new Date(currentDate);
    if (viewMode === 'year') {
      d.setFullYear(d.getFullYear() + direction);
    } else if (viewMode === 'month' || viewMode === 'agenda') {
      d.setMonth(d.getMonth() + direction);
    } else if (viewMode === 'week') {
      d.setDate(d.getDate() + direction * 7);
    } else {
      d.setDate(d.getDate() + direction);
    }
    setCurrentDate(d);
  };

  const goToToday = () => setCurrentDate(new Date());

  const headerLabel = useMemo(() => {
    if (viewMode === 'year') {
      return String(currentDate.getFullYear());
    } else if (viewMode === 'month' || viewMode === 'agenda') {
      return currentDate.toLocaleString(undefined, { month: 'long', year: 'numeric' });
    } else if (viewMode === 'week') {
      const days = getWeekDays(currentDate);
      const s = days[0]!.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
      const e = days[6]!.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
      return `${s} - ${e}`;
    } else {
      return currentDate.toLocaleDateString(undefined, {
        weekday: 'long',
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      });
    }
  }, [viewMode, currentDate]);

  return (
    <div className="space-y-4">
      {/* Calendar Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between bg-white dark:bg-gray-800 rounded-lg shadow dark:border dark:border-gray-700 p-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(-1)}
            className="p-2 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            aria-label="Previous"
          >
            <ChevronLeftIcon className="h-5 w-5 text-gray-600 dark:text-gray-400" />
          </button>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 min-w-[200px] text-center">
            {headerLabel}
          </h2>
          <button
            onClick={() => navigate(1)}
            className="p-2 rounded-md hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            aria-label="Next"
          >
            <ChevronRightIcon className="h-5 w-5 text-gray-600 dark:text-gray-400" />
          </button>
          <button
            onClick={goToToday}
            className="ml-2 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
          >
            Today
          </button>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="inline-flex rounded-md shadow-sm">
            {(['year', 'month', 'week', 'day', 'agenda'] as ViewMode[]).map((mode, idx, arr) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={clsx(
                  'px-3 py-1.5 text-sm font-medium border',
                  idx === 0 && 'rounded-l-md',
                  idx === arr.length - 1 && 'rounded-r-md',
                  viewMode === mode
                    ? 'bg-primary-600 text-white border-primary-600'
                    : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600'
                )}
              >
                {mode.charAt(0).toUpperCase() + mode.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Filter row */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between bg-white dark:bg-gray-800 rounded-lg shadow dark:border dark:border-gray-700 px-4 py-3">
        <div className="flex items-center gap-3 flex-wrap">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
            Type
            <select
              value={activityTypeFilter}
              onChange={(e) => setActivityTypeFilter(e.target.value)}
              className="ml-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 border border-gray-300 dark:border-gray-600 rounded-md px-2 py-1"
            >
              <option value="all">All</option>
              <option value="call">Call</option>
              <option value="meeting">Meeting</option>
              <option value="task">Task</option>
              <option value="email">Email</option>
              <option value="note">Note</option>
            </select>
          </label>
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
            Source
            <select
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value as SourceFilter)}
              className="ml-2 text-sm bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 border border-gray-300 dark:border-gray-600 rounded-md px-2 py-1"
            >
              <option value="all">All</option>
              <option value="manual">CRM only</option>
              <option value="google">Google only</option>
            </select>
          </label>
          {(activityTypeFilter !== 'all' || sourceFilter !== 'all') && (
            <button
              onClick={() => {
                setActivityTypeFilter('all');
                setSourceFilter('all');
              }}
              className="text-xs text-primary-600 dark:text-primary-400 hover:underline"
            >
              Clear filters
            </button>
          )}
        </div>
        <div className="text-xs text-gray-500 dark:text-gray-400">
          {isLoading ? 'Loading…' : `${visibleTotal} ${visibleTotal === 1 ? 'event' : 'events'} in view`}
        </div>
      </div>

      {/* Calendar Grid */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow dark:border dark:border-gray-700 overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <Spinner size="lg" />
          </div>
        ) : (
          <>
            {viewMode === 'year' && (
              <YearView
                currentDate={currentDate}
                today={today}
                activitiesByDate={activitiesByDate}
                onSelectMonth={(year, month) => {
                  setCurrentDate(new Date(year, month, 1));
                  setViewMode('month');
                }}
              />
            )}
            {viewMode === 'month' && (
              <MonthView
                currentDate={currentDate}
                today={today}
                activitiesByDate={activitiesByDate}
                onSelectActivity={setSelectedActivity}
              />
            )}
            {viewMode === 'week' && (
              <WeekView
                currentDate={currentDate}
                today={today}
                activitiesByDate={activitiesByDate}
                onSelectActivity={setSelectedActivity}
              />
            )}
            {viewMode === 'day' && (
              <DayView
                currentDate={currentDate}
                activitiesByDate={activitiesByDate}
                onSelectActivity={setSelectedActivity}
              />
            )}
            {viewMode === 'agenda' && (
              <AgendaView
                today={today}
                activitiesByDate={activitiesByDate}
                onSelectActivity={setSelectedActivity}
              />
            )}
          </>
        )}
      </div>

      {/* Activity Detail Modal */}
      {selectedActivity && (
        <ActivityDetailModal
          activity={selectedActivity}
          onClose={() => setSelectedActivity(null)}
          connected={connected}
          isPushing={isPushing}
          onPush={pushToCalendar}
        />
      )}
    </div>
  );
}

export default CalendarView;
