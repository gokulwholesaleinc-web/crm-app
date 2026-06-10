import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import {
  getSocial,
  getSyncStatus,
  type SocialMetric,
  type SocialPlatform,
} from '../../../api/marketing';
import { Card } from '../../../components/ui';
import { EmptyState } from '../../../components/ui/EmptyState';
import { ChartFigure } from './ChartFigure';
import { DataTrustBadge } from './DataTrustBadge';
import { KpiCard } from './KpiCard';
import { QueryPanel } from './QueryPanel';
import { type RangePreset, presetRange } from '../utils/dateRange';
import { formatDate, formatNumber } from '../utils/format';
import { platformLabel } from '../utils/platformLabel';
import { syncToSources } from '../utils/syncToSources';

// Friendly labels for the known IG/FB day metrics; unknown keys fall back to a
// humanized form (so a new/renamed metric still renders sensibly, not "page_x").
const METRIC_LABELS: Record<string, string> = {
  reach: 'Reach',
  profile_views: 'Profile Views',
  follower_count: 'Followers',
  page_impressions_unique: 'Reach (Unique)',
  page_post_engagements: 'Engagements',
  page_fans: 'Followers',
  page_views_total: 'Page Views',
};

function metricLabel(key: string): string {
  return METRIC_LABELS[key] ?? key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

/** One platform section: a latest-value KPI per metric + an accessible table of
 *  each metric's daily series (no chart — IG metrics span very different
 *  magnitudes, e.g. followers vs profile views, so a shared axis would mislead). */
function PlatformSection({ platform }: { platform: SocialPlatform }) {
  if (platform.metrics.length === 0) {
    return (
      <Card padding="lg">
        <EmptyState
          title={platformLabel(platform.platform)}
          description="No organic metrics in this period."
        />
      </Card>
    );
  }
  return (
    <section className="space-y-4" aria-label={platformLabel(platform.platform)}>
      <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
        {platformLabel(platform.platform)}
      </h2>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {platform.metrics.map((m) => (
          <KpiCard key={m.metric_key} label={metricLabel(m.metric_key)} value={formatNumber(m.latest)} />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {platform.metrics.map((m) => (
          <MetricTrend key={m.metric_key} metric={m} />
        ))}
      </div>
    </section>
  );
}

function MetricTrend({ metric }: { metric: SocialMetric }) {
  const rows = metric.series.map((p) => ({
    date: formatDate(p.date),
    value: formatNumber(p.value),
  }));
  return (
    <ChartFigure
      title={`${metricLabel(metric.metric_key)} over time`}
      table={{
        columns: [
          { key: 'date', label: 'Date' },
          { key: 'value', label: metricLabel(metric.metric_key), numeric: true },
        ],
        rows,
        rowKey: (row) => String(row.date),
      }}
    >
      <div className="max-h-64 overflow-auto">
        <table className="min-w-full text-sm">
          <caption className="sr-only">{metricLabel(metric.metric_key)} daily values</caption>
          <thead className="sticky top-0 bg-white dark:bg-gray-800">
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th scope="col" className="px-3 py-2 text-left font-medium text-gray-500">
                Date
              </th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">
                {metricLabel(metric.metric_key)}
              </th>
            </tr>
          </thead>
          <tbody>
            {metric.series.map((p) => (
              <tr key={p.date} className="border-b border-gray-100 dark:border-gray-700/50">
                <td className="px-3 py-2 text-gray-700 dark:text-gray-300">{formatDate(p.date)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                  {formatNumber(p.value)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ChartFigure>
  );
}

export function SocialTab({
  companyId,
  preset,
}: {
  companyId: number;
  preset: Exclude<RangePreset, 'custom'>;
}) {
  const window = useMemo(() => presetRange(preset), [preset]);
  const key = [companyId, window.date_from, window.date_to] as const;

  const socialQ = useQuery({ queryKey: ['mktg-social', ...key], queryFn: () => getSocial(companyId, window) });
  const syncQ = useQuery({ queryKey: ['mktg-sync', companyId], queryFn: () => getSyncStatus(companyId) });

  const connections = syncQ.data?.connections ?? [];

  return (
    <div className="space-y-8">
      {syncQ.data && (
        <DataTrustBadge sources={syncToSources(connections)} timezone={socialQ.data?.data_trust.timezone} />
      )}

      <QueryPanel
        q={socialQ}
        height={320}
        render={(data) =>
          data.platforms.length === 0 ? (
            <Card padding="lg">
              <EmptyState
                title="No social accounts connected"
                description="Connect this client's Instagram / Facebook accounts in the admin panel to populate this section."
              />
            </Card>
          ) : (
            <div className="space-y-8">
              {data.platforms.map((p) => (
                <PlatformSection key={p.platform} platform={p} />
              ))}
            </div>
          )
        }
      />
    </div>
  );
}
