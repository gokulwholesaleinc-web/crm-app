import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline';
import { getCalendarActivities } from '../../../api/activities';
import type { CalendarActivity } from '../../../api/activities';
import { Spinner, Modal } from '../../../components/ui';
import clsx from 'clsx';

type ViewMode = 'month' | 'week' | 'day';

const ACTIVITY_COLORS: Record<string, string> = {
  call: 'bg-blue-100 text-blue-800 border-blue-200',
  meeting: 'bg-green-100 text-green-800 border-green-200',
  task: 'bg-orange-100 text-orange-800 border-orange-200',
  email: 'bg-purple-100 text-purple-800 border-purple-200',
  note: 'bg-gray-100 text-gray-800 border-gray-200',
};

const WEEKDAY_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

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

  // Fill in days from previous month
  for (let i = startOffset - 1; i >= 0; i--) {
    days.push(new Date(year, month, -i));
  }

  // Current month days
  for (let d = 1; d <= lastDay.getDate(); d++) {
    days.push(new Date(year, month, d));
  }

  // Fill remaining cells
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

  const today = useMemo(() => formatDateKey(new Date()), []);

  // Calculate date range based on view
  const dateRange = useMemo(() => {
    if (viewMode === 'month') {
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
    } else {
      const key = formatDateKey(currentDate);
      return { start: key, end: key };
    }
  }, [viewMode, currentDate]);

  const { data: calendarData, isLoading } = useQuery({
    queryKey: ['calendar', dateRange.start, dateRange.end],
    queryFn: () => getCalendarActivities(dateRange.start, dateRange.end),
  });

  const navigate = (direction: -1 | 1) => {
    const d = new Date(currentDate);
    if (viewMode === 'month') {
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
    if (viewMode === 'month') {
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

  const activitiesByDate = calendarData?.dates ?? {};

  const renderMonthView = () => {
    const year = currentDate.getFullYear();
    const month = currentDate.getMonth();
    const days = getMonthDays(year, month);

    return (
      <div className="grid grid-cols-7 border-t border-l border-gray-200">
        {/* Header row */}
        {WEEKDAY_LABELS.map((label) => (
          <div key={label} className="border-r border-b border-gray-200 bg-gray-50 px-2 py-2 text-center text-xs font-medium text-gray-500 uppercase">
            {label}
          </div>
        ))}
        {/* Day cells */}
        {days.map((day) => {
          const key = formatDateKey(day);
          const isCurrentMonth = day.getMonth() === month;
          const isToday = key === today;
          const dayActivities = activitiesByDate[key] ?? [];

          return (
            <div
              key={key}
              className={clsx(
                'border-r border-b border-gray-200 min-h-[100px] p-1 hover:bg-gray-50 transition-colors',
                !isCurrentMonth && 'bg-gray-50/50'
              )}
            >
              <div className="flex items-center justify-between px-1">
                <span
                  className={clsx(
                    'text-sm font-medium inline-flex items-center justify-center w-7 h-7 rounded-full',
                    isToday && 'bg-primary-600 text-white',
                    !isToday && isCurrentMonth && 'text-gray-900',
                    !isToday && !isCurrentMonth && 'text-gray-400'
                  )}
                >
                  {day.getDate()}
                </span>
                {dayActivities.length > 0 && (
                  <span className="text-xs text-gray-400">{dayActivities.length}</span>
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
                  <span className="text-xs text-gray-500 pl-1">+{dayActivities.length - 3} more</span>
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
      <div className="grid grid-cols-7 border-t border-l border-gray-200">
        {days.map((day) => {
          const key = formatDateKey(day);
          const isToday = key === today;
          const dayActivities = activitiesByDate[key] ?? [];

          return (
            <div key={key} className="border-r border-b border-gray-200 min-h-[300px] p-2">
              <div className="text-center mb-2">
                <div className="text-xs text-gray-500 uppercase">{WEEKDAY_LABELS[day.getDay()]}</div>
                <div
                  className={clsx(
                    'text-lg font-semibold inline-flex items-center justify-center w-9 h-9 rounded-full',
                    isToday && 'bg-primary-600 text-white',
                    !isToday && 'text-gray-900'
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
      <div className="bg-white rounded-lg border border-gray-200 p-4 min-h-[400px]">
        {dayActivities.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <p>No activities scheduled for this day.</p>
            <span className="mt-2 text-primary-600 text-sm font-medium">
              No activities yet
            </span>
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
                  <span className="text-xs capitalize px-2 py-0.5 rounded-full bg-white/50">
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

  return (
    <div className="space-y-4">
      {/* Calendar Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between bg-white rounded-lg shadow p-4">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate(-1)}
            className="p-2 rounded-md hover:bg-gray-100 transition-colors"
            aria-label="Previous"
          >
            <ChevronLeftIcon className="h-5 w-5 text-gray-600" />
          </button>
          <h2 className="text-lg font-semibold text-gray-900 min-w-[200px] text-center">
            {headerLabel}
          </h2>
          <button
            onClick={() => navigate(1)}
            className="p-2 rounded-md hover:bg-gray-100 transition-colors"
            aria-label="Next"
          >
            <ChevronRightIcon className="h-5 w-5 text-gray-600" />
          </button>
          <button
            onClick={goToToday}
            className="ml-2 px-3 py-1.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
          >
            Today
          </button>
        </div>
        <div className="flex items-center gap-2">
          {/* View toggle */}
          <div className="inline-flex rounded-md shadow-sm">
            {(['month', 'week', 'day'] as ViewMode[]).map((mode) => (
              <button
                key={mode}
                onClick={() => setViewMode(mode)}
                className={clsx(
                  'px-3 py-1.5 text-sm font-medium border',
                  mode === 'month' && 'rounded-l-md',
                  mode === 'day' && 'rounded-r-md',
                  viewMode === mode
                    ? 'bg-primary-600 text-white border-primary-600'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
                )}
              >
                {mode.charAt(0).toUpperCase() + mode.slice(1)}
              </button>
            ))}
          </div>
          {/* Legend */}
          <div className="hidden sm:flex items-center gap-2 ml-4 text-xs">
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-blue-200 border border-blue-300" />Call
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-green-200 border border-green-300" />Meeting
            </span>
            <span className="flex items-center gap-1">
              <span className="w-3 h-3 rounded bg-orange-200 border border-orange-300" />Task
            </span>
          </div>
        </div>
      </div>

      {/* Calendar Grid */}
      <div className="bg-white rounded-lg shadow overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <Spinner size="lg" />
          </div>
        ) : (
          <>
            {viewMode === 'month' && renderMonthView()}
            {viewMode === 'week' && renderWeekView()}
            {viewMode === 'day' && renderDayView()}
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
                <span className="font-medium text-gray-500">Type</span>
                <p className="capitalize">{selectedActivity.activity_type}</p>
              </div>
              <div>
                <span className="font-medium text-gray-500">Priority</span>
                <p className="capitalize">{selectedActivity.priority}</p>
              </div>
              <div>
                <span className="font-medium text-gray-500">Status</span>
                <p>{selectedActivity.is_completed ? 'Completed' : 'Open'}</p>
              </div>
              {selectedActivity.scheduled_at && (
                <div>
                  <span className="font-medium text-gray-500">Scheduled</span>
                  <p>{new Date(selectedActivity.scheduled_at).toLocaleString()}</p>
                </div>
              )}
              {selectedActivity.due_date && (
                <div>
                  <span className="font-medium text-gray-500">Due Date</span>
                  <p>{new Date(selectedActivity.due_date).toLocaleDateString()}</p>
                </div>
              )}
              {selectedActivity.meeting_location && (
                <div>
                  <span className="font-medium text-gray-500">Location</span>
                  <p>{selectedActivity.meeting_location}</p>
                </div>
              )}
            </div>
            {selectedActivity.description && (
              <div className="text-sm">
                <span className="font-medium text-gray-500">Description</span>
                <p className="mt-1 text-gray-700">{selectedActivity.description}</p>
              </div>
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}

export default CalendarView;
