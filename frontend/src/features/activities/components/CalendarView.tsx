import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowUpOnSquareIcon, ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline';
import { getCalendarActivities } from '../../../api/activities';
import type { CalendarActivity } from '../../../api/activities';
import { Spinner, Modal } from '../../../components/ui';
import { useGoogleCalendarSync } from '../../../hooks/useGoogleCalendarSync';
import { usePushToGoogleCalendar } from '../../../hooks/usePushToGoogleCalendar';
import clsx from 'clsx';

type ViewMode = 'year' | 'month' | 'week' | 'day' | 'agenda';
type SourceFilter = 'all' | 'manual' | 'google';

// Google-synced events are stored with entity_type="users" (see constants.ENTITY_TYPE_USERS).
const GOOGLE_SYNC_ENTITY_TYPE = 'users';

const ACTIVITY_COLORS: Record<string, string> = {
  call: 'bg-blue-100 text-blue-800 border-blue-200 dark:bg-blue-900/30 dark:text-blue-300 dark:border-blue-800',
  meeting: 'bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-300 dark:border-green-800',
  task: 'bg-orange-100 text-orange-800 border-orange-200 dark:bg-orange-900/30 dark:text-orange-300 dark:border-orange-800',
  email: 'bg-purple-100 text-purple-800 border-purple-200 dark:bg-purple-900/30 dark:text-purple-300 dark:border-purple-800',
  note: 'bg-gray-100 text-gray-800 border-gray-200 dark:bg-gray-700 dark:text-gray-300 dark:border-gray-600',
};

const MONTH_LABELS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WEEKDAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const WEEKDAY_MINI = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

function formatDateKey(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getMonthDays(year: number, month: number): Date[] {
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);
  const startOffset = firstDay.getDay();
  const days: Date[] = [];

  for (let i = startOffset - 1; i >= 0; i--) {
    days.push(new Date(year, month, -i));
  }
  for (let d = 1; d <= lastDay.getDate(); d++) {
    days.push(new Date(year, month, d));
  }
  const remaining = 42 - days.length;
  for (let i = 1; i <= remaining; i++) {
    days.push(new Date(year, month + 1, i));
  }
  return days;
}

function getWeekDays(baseDate: Date): Date[] {
  const day = baseDate.getDay();
  const start = new Date(baseDate);
  start.setDate(start.getDate() - day);
  const days: Date[] = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    days.push(d);
  }
  return days;
}

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

  const renderMonthView = () => {
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
              <div className="mt-1 space-y-0.5 overflow-hidden max-h-[60px]">
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
                      setSelectedActivity(act);
                    }}
                    title={act.subject}
                  >
                    {act.subject}
                  </button>
                ))}
                {dayActivities.length > 3 && (
                  <span className="text-xs text-gray-500 dark:text-gray-400 pl-1">+{dayActivities.length - 3} more</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

  const renderWeekView = () => {
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
                    onClick={() => setSelectedActivity(act)}
                  >
                    <div className="font-medium truncate">{act.subject}</div>
                    {act.scheduled_at && (
                      <div className="text-xs opacity-75">
                        {new Date(act.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
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
  };

  const renderDayView = () => {
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
                onClick={() => setSelectedActivity(act)}
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
  };

  const renderYearView = () => {
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
              onClick={() => {
                setCurrentDate(new Date(year, monthIdx, 1));
                setViewMode('month');
              }}
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
  };

  const renderAgendaView = () => {
    const sortedDays = Object.keys(activitiesByDate).sort();

    if (sortedDays.length === 0) {
      return (
        <div className="text-center py-12 text-gray-500 dark:text-gray-400">
          <p>No activities in this range.</p>
          <p className="text-xs mt-1">Try clearing filters or navigating to a different month.</p>
        </div>
      );
    }

    return (
      <div className="divide-y divide-gray-200 dark:divide-gray-700">
        {sortedDays.map((dayKey) => {
          const acts = activitiesByDate[dayKey] ?? [];
          const d = new Date(`${dayKey}T00:00:00`);
          const label = d.toLocaleDateString(undefined, {
            weekday: 'long',
            month: 'long',
            day: 'numeric',
            year: 'numeric',
          });
          const isToday = dayKey === today;

          return (
            <div key={dayKey} className="py-3 px-4">
              <div className="flex items-center gap-3 mb-2">
                <span className={clsx('text-sm font-semibold', isToday ? 'text-primary-600 dark:text-primary-400' : 'text-gray-900 dark:text-gray-100')}>
                  {label}
                </span>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {acts.length} {acts.length === 1 ? 'event' : 'events'}
                </span>
              </div>
              <div className="space-y-1.5">
                {acts.map((act) => {
                  const isGoogle = act.entity_type === GOOGLE_SYNC_ENTITY_TYPE;
                  return (
                    <button
                      key={act.id}
                      onClick={() => setSelectedActivity(act)}
                      className={clsx(
                        'flex items-start gap-3 w-full text-left p-2 rounded border hover:shadow-sm transition-shadow',
                        ACTIVITY_COLORS[act.activity_type] ?? ACTIVITY_COLORS.note,
                        act.is_completed && 'opacity-50 line-through'
                      )}
                    >
                      <span className="text-xs font-mono mt-0.5 opacity-75 min-w-[48px]">
                        {act.scheduled_at
                          ? new Date(act.scheduled_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                          : 'All day'}
                      </span>
                      <span className="flex-1 min-w-0">
                        <span className="block font-medium truncate">{act.subject}</span>
                        {act.description && (
                          <span className="block text-xs opacity-75 line-clamp-1">{act.description}</span>
                        )}
                      </span>
                      <span className="flex items-center gap-1.5 shrink-0">
                        <span className="text-xs capitalize px-1.5 py-0.5 rounded bg-white/60 dark:bg-black/20">
                          {act.activity_type}
                        </span>
                        {isGoogle && (
                          <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-white/60 dark:bg-black/20" title="Synced from Google Calendar">
                            Google
                          </span>
                        )}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    );
  };

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
            {viewMode === 'year' && renderYearView()}
            {viewMode === 'month' && renderMonthView()}
            {viewMode === 'week' && renderWeekView()}
            {viewMode === 'day' && renderDayView()}
            {viewMode === 'agenda' && renderAgendaView()}
          </>
        )}
      </div>

      {/* Activity Detail Modal */}
      {selectedActivity && (
        <Modal
          isOpen={!!selectedActivity}
          onClose={() => setSelectedActivity(null)}
          title={selectedActivity.subject}
          size="md"
        >
          <div className="space-y-4 p-4">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="font-medium text-gray-500 dark:text-gray-400">Type</span>
                <p className="capitalize text-gray-900 dark:text-gray-100">{selectedActivity.activity_type}</p>
              </div>
              <div>
                <span className="font-medium text-gray-500 dark:text-gray-400">Source</span>
                <p className="text-gray-900 dark:text-gray-100">
                  {selectedActivity.entity_type === GOOGLE_SYNC_ENTITY_TYPE ? 'Google Calendar' : 'CRM'}
                </p>
              </div>
              <div>
                <span className="font-medium text-gray-500 dark:text-gray-400">Priority</span>
                <p className="capitalize text-gray-900 dark:text-gray-100">{selectedActivity.priority}</p>
              </div>
              <div>
                <span className="font-medium text-gray-500 dark:text-gray-400">Status</span>
                <p className="text-gray-900 dark:text-gray-100">{selectedActivity.is_completed ? 'Completed' : 'Open'}</p>
              </div>
              {selectedActivity.scheduled_at && (
                <div>
                  <span className="font-medium text-gray-500 dark:text-gray-400">Scheduled</span>
                  <p className="text-gray-900 dark:text-gray-100">{new Date(selectedActivity.scheduled_at).toLocaleString()}</p>
                </div>
              )}
              {selectedActivity.due_date && (
                <div>
                  <span className="font-medium text-gray-500 dark:text-gray-400">Due Date</span>
                  <p className="text-gray-900 dark:text-gray-100">{new Date(selectedActivity.due_date).toLocaleDateString()}</p>
                </div>
              )}
              {selectedActivity.meeting_location && (
                <div>
                  <span className="font-medium text-gray-500 dark:text-gray-400">Location</span>
                  <p className="text-gray-900 dark:text-gray-100">{selectedActivity.meeting_location}</p>
                </div>
              )}
            </div>
            {selectedActivity.description && (
              <div className="text-sm">
                <span className="font-medium text-gray-500 dark:text-gray-400">Description</span>
                <p className="mt-1 text-gray-700 dark:text-gray-300">{selectedActivity.description}</p>
              </div>
            )}

            {/* Push to Google Calendar footer */}
            {selectedActivity.entity_type !== GOOGLE_SYNC_ENTITY_TYPE && (
              <div className="border-t pt-4 flex flex-col gap-1.5">
                <button
                  type="button"
                  disabled={!connected || isPushing}
                  onClick={() => pushToCalendar(selectedActivity.id)}
                  className={clsx(
                    'inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-md border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500',
                    connected
                      ? 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600'
                      : 'bg-gray-100 dark:bg-gray-800 text-gray-400 dark:text-gray-500 border-gray-200 dark:border-gray-700 cursor-not-allowed'
                  )}
                  aria-label="Push to Google Calendar"
                >
                  {isPushing ? (
                    <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                    </svg>
                  ) : (
                    <ArrowUpOnSquareIcon className="h-4 w-4" aria-hidden="true" />
                  )}
                  Push to Google Calendar
                </button>
                {!connected && (
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    <Link to="/settings" className="underline hover:text-primary-600 dark:hover:text-primary-400">
                      Connect Google Calendar in Settings
                    </Link>
                    {' '}to push events.
                  </p>
                )}
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}

export default CalendarView;
