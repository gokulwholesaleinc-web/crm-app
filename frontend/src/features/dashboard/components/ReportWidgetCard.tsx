import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getDashboardWidgetData,
  updateDashboardWidget,
  deleteDashboardWidget,
} from '../../../api/dashboard';
import type { ReportWidget } from '../../../api/dashboard';
import { useAuthStore } from '../../../store/authStore';

const CHART_TYPE_ICONS: Record<string, string> = {
  bar: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
  line: 'M13 7h8m0 0v8m0-8l-8 8-4-4-6 6',
  pie: 'M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z',
  table: 'M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z',
  funnel: 'M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z',
};

const BAR_COLORS = [
  'bg-primary-500', 'bg-green-500', 'bg-blue-500', 'bg-amber-500',
  'bg-rose-500', 'bg-violet-500', 'bg-cyan-500', 'bg-orange-500',
];

interface ReportWidgetCardProps {
  widget: ReportWidget;
}

export function ReportWidgetCard({ widget }: ReportWidgetCardProps) {
  const queryClient = useQueryClient();
  const { isAuthenticated } = useAuthStore();
  const [showMenu, setShowMenu] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard', 'widget-data', widget.id],
    queryFn: () => getDashboardWidgetData(widget.id),
    staleTime: 60 * 1000,
    enabled: isAuthenticated && widget.is_visible,
  });

  const updateMutation = useMutation({
    mutationFn: (payload: { width?: string; is_visible?: boolean }) =>
      updateDashboardWidget(widget.id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard', 'widgets'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteDashboardWidget(widget.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['dashboard', 'widgets'] });
    },
  });

  const iconPath = CHART_TYPE_ICONS[widget.report_chart_type] ?? CHART_TYPE_ICONS.bar;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-gray-200 dark:border-gray-700 relative">
      {/* Header */}
      <div className="px-4 sm:px-6 py-3 sm:py-4 border-b border-gray-200 dark:border-gray-700">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            <svg
              className="h-4 w-4 text-gray-400 shrink-0"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={iconPath} />
            </svg>
            <h3 className="text-sm sm:text-base font-medium text-gray-900 dark:text-gray-100 truncate">
              {widget.report_name}
            </h3>
          </div>
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowMenu(prev => !prev)}
              className="p-1 rounded-md text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
              aria-label="Widget actions"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z" />
              </svg>
            </button>
            {showMenu && (
              <div
                className="absolute right-0 top-full mt-1 w-36 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md shadow-lg z-10"
                onMouseLeave={() => setShowMenu(false)}
              >
                <button
                  type="button"
                  className="w-full px-3 py-2 text-left text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                  onClick={() => {
                    updateMutation.mutate({
                      width: widget.width === 'half' ? 'full' : 'half',
                    });
                    setShowMenu(false);
                  }}
                >
                  {widget.width === 'half' ? 'Full width' : 'Half width'}
                </button>
                <button
                  type="button"
                  className="w-full px-3 py-2 text-left text-sm text-red-600 dark:text-red-400 hover:bg-gray-100 dark:hover:bg-gray-700"
                  onClick={() => {
                    deleteMutation.mutate();
                    setShowMenu(false);
                  }}
                >
                  Remove
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="p-4 sm:p-6">
        {isLoading && (
          <div className="flex items-center justify-center py-8">
            <div className="h-6 w-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {error && (
          <p className="text-sm text-red-500 dark:text-red-400 text-center py-4">
            Failed to load report data
          </p>
        )}

        {data && data.result.data.length === 0 && (
          <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
            No data available
          </p>
        )}

        {data && data.result.data.length > 0 && (
          <div className="space-y-2">
            {data.result.data.slice(0, 8).map((point, index) => {
              const maxValue = Math.max(...data.result.data.map(d => d.value), 1);
              return (
                <div key={point.label} className="flex items-center gap-2">
                  <span className="w-24 text-xs text-gray-600 dark:text-gray-400 truncate">
                    {point.label}
                  </span>
                  <div className="flex-1">
                    <div className="relative h-3 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                      <div
                        className={`absolute h-full ${BAR_COLORS[index % BAR_COLORS.length]} rounded-full`}
                        style={{ width: `${Math.min((point.value / maxValue) * 100, 100)}%` }}
                      />
                    </div>
                  </div>
                  <span className="w-12 text-right text-xs font-medium text-gray-900 dark:text-gray-100">
                    {point.value}
                  </span>
                </div>
              );
            })}
            {data.result.total != null && (
              <div className="pt-2 border-t border-gray-100 dark:border-gray-700 flex justify-between">
                <span className="text-xs font-medium text-gray-500 dark:text-gray-400">Total</span>
                <span className="text-xs font-semibold text-gray-900 dark:text-gray-100">
                  {data.result.total}
                </span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
