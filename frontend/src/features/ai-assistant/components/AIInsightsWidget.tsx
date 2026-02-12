/**
 * AI Insights widget for entity detail pages.
 *
 * Shows activity insights and suggestions for a specific entity.
 */

import { SparklesIcon } from '@heroicons/react/24/outline';
import { Spinner } from '../../../components/ui/Spinner';
import { useEntityInsights } from '../../../hooks/useAI';

interface AIInsightsWidgetProps {
  entityType: string;
  entityId: number;
}

export function AIInsightsWidget({ entityType, entityId }: AIInsightsWidgetProps) {
  const { data, isLoading, error } = useEntityInsights(entityType, entityId);

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-center gap-2 mb-3">
          <SparklesIcon className="h-5 w-5 text-purple-500 dark:text-purple-400" aria-hidden="true" />
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">AI Insights</h3>
        </div>
        <div className="flex items-center justify-center py-4">
          <Spinner size="sm" />
        </div>
      </div>
    );
  }

  if (error || !data) {
    return null;
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-4">
      <div className="flex items-center gap-2 mb-3">
        <SparklesIcon className="h-5 w-5 text-purple-500 dark:text-purple-400" aria-hidden="true" />
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">AI Insights</h3>
      </div>

      {data.insights.length > 0 ? (
        <div className="grid grid-cols-2 gap-2 mb-3">
          {data.insights.map((insight, idx) => (
            <div key={idx} className="p-2 bg-gray-50 dark:bg-gray-700 rounded-lg">
              <p className="text-xs text-gray-500 dark:text-gray-400">{insight.label}</p>
              <p className="text-sm font-semibold text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
                {Intl.NumberFormat().format(insight.value)}
              </p>
            </div>
          ))}
        </div>
      ) : null}

      {data.suggestions.length > 0 ? (
        <div className="space-y-1.5">
          {data.suggestions.map((suggestion, idx) => (
            <div
              key={idx}
              className="flex items-start gap-2 text-xs text-gray-600 dark:text-gray-400"
            >
              <span className="mt-1 h-1.5 w-1.5 rounded-full bg-purple-400 dark:bg-purple-500 flex-shrink-0" aria-hidden="true" />
              <span>{suggestion}</span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
