import clsx from 'clsx';
import type { CalendarActivity } from '../../../../api/activities';
import { ACTIVITY_COLORS, GOOGLE_SYNC_ENTITY_TYPE } from './helpers';

interface AgendaViewProps {
  today: string;
  activitiesByDate: Record<string, CalendarActivity[]>;
  onSelectActivity: (activity: CalendarActivity) => void;
}

export function AgendaView({ today, activitiesByDate, onSelectActivity }: AgendaViewProps) {
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
                    onClick={() => onSelectActivity(act)}
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
}
