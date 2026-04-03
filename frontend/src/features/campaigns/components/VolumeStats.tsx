/**
 * Email volume dashboard card showing daily send usage, remaining capacity,
 * and warmup progress when enabled.
 */

import clsx from 'clsx';
import { Spinner } from '../../../components/ui/Spinner';
import { useVolumeStats } from '../../../hooks/useCampaigns';
import {
  EnvelopeIcon,
  FireIcon,
} from '@heroicons/react/24/outline';

function getUsageColor(percentage: number): {
  bar: string;
  text: string;
  bg: string;
} {
  if (percentage >= 90) return { bar: 'bg-red-500', text: 'text-red-600 dark:text-red-400', bg: 'bg-red-50 dark:bg-red-900/20' };
  if (percentage >= 70) return { bar: 'bg-yellow-500', text: 'text-yellow-600 dark:text-yellow-400', bg: 'bg-yellow-50 dark:bg-yellow-900/20' };
  return { bar: 'bg-green-500', text: 'text-green-600 dark:text-green-400', bg: 'bg-green-50 dark:bg-green-900/20' };
}

export function VolumeStats() {
  const { data, isLoading, error } = useVolumeStats();

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-5">
        <div className="flex items-center justify-center py-4">
          <Spinner size="sm" />
          <span className="ml-2 text-sm text-gray-500">Loading volume stats...</span>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return null;
  }

  const percentage = data.daily_limit > 0
    ? Math.round((data.sent_today / data.daily_limit) * 100)
    : 0;
  const color = getUsageColor(percentage);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-5">
      <div className="flex items-center gap-2 mb-4">
        <EnvelopeIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Email Volume Today
        </h3>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {/* Usage progress */}
        <div className="sm:col-span-2">
          <div className="flex items-baseline justify-between mb-2">
            <span className="text-2xl font-bold text-gray-900 dark:text-gray-100 font-variant-numeric tabular-nums">
              {data.sent_today}
            </span>
            <span className="text-sm text-gray-500 dark:text-gray-400">
              of {data.daily_limit} daily limit
            </span>
          </div>
          <div
            className="w-full h-3 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden"
            role="progressbar"
            aria-valuenow={data.sent_today}
            aria-valuemin={0}
            aria-valuemax={data.daily_limit}
            aria-label={`${data.sent_today} of ${data.daily_limit} emails sent today`}
          >
            <div
              className={clsx('h-full rounded-full transition-all duration-300', color.bar)}
              style={{ width: `${Math.min(100, percentage)}%` }}
            />
          </div>
          <p className={clsx('mt-2 text-sm font-medium', color.text)}>
            {data.remaining_today} emails remaining today
          </p>
        </div>

        {/* Warmup indicator */}
        <div className={clsx(
          'rounded-lg p-3',
          data.warmup_enabled
            ? 'bg-orange-50 dark:bg-orange-900/20'
            : 'bg-gray-50 dark:bg-gray-700/50'
        )}>
          {data.warmup_enabled ? (
            <>
              <div className="flex items-center gap-1.5 mb-1">
                <FireIcon className="h-4 w-4 text-orange-500" aria-hidden="true" />
                <span className="text-xs font-semibold text-orange-700 dark:text-orange-400">
                  Warmup Active
                </span>
              </div>
              <p className="text-lg font-bold text-orange-700 dark:text-orange-300" style={{ fontVariantNumeric: 'tabular-nums' }}>
                Day {data.warmup_day}
              </p>
              <p className="text-xs text-orange-600 dark:text-orange-400">
                Limit: {data.warmup_current_limit}/day
              </p>
            </>
          ) : (
            <>
              <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">
                Warmup
              </p>
              <p className="text-sm text-gray-600 dark:text-gray-300">
                Not enabled
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default VolumeStats;
