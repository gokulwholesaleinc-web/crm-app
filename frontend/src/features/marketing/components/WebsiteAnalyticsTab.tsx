import { useQuery, type UseQueryResult } from '@tanstack/react-query';
import { type ReactNode, useMemo } from 'react';
import {
  getAnalytics,
  getSiteHealth,
  getSyncStatus,
  type AnalyticsResponse,
  type ConnectionSyncStatus,
  type GscPage,
  type GscQuery,
  type SiteHealthResponse,
  type SiteHealthSnapshotOut,
  type TopPage,
  type TrafficSource,
} from '../../../api/marketing';
import { Card } from '../../../components/ui';
import { EmptyState } from '../../../components/ui/EmptyState';
import { ChartFigure } from './ChartFigure';
import { Ga4TrendChart } from './charts/Ga4TrendChart';
import { DataTrustBadge, type SourceFreshness } from './DataTrustBadge';
import { KpiCard } from './KpiCard';
import { type RangePreset, presetRange } from '../utils/dateRange';
import { formatDecimal, formatNumber, formatPercent } from '../utils/format';
import { platformLabel } from '../utils/platformLabel';

function syncToSources(connections: ConnectionSyncStatus[]): SourceFreshness[] {
  return connections.map((c) => ({
    source: platformLabel(c.platform),
    lastSyncedAt: c.last_synced_at,
    status: c.status,
  }));
}

/** Loading skeleton / error+retry / data for a single panel query — mirrors the
 *  QueryPanel in ReportingPage so every panel has a consistent error + retry path
 *  and charts don't pop in (CLS). */
function QueryPanel<T>({
  q,
  height = 240,
  render,
}: {
  q: UseQueryResult<T>;
  height?: number;
  render: (data: T) => ReactNode;
}) {
  if (q.isLoading) {
    return (
      <div
        className="animate-pulse rounded-lg border border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800"
        style={{ height }}
        aria-hidden="true"
      />
    );
  }
  if (q.isError) {
    return (
      <Card padding="lg">
        <EmptyState variant="error" title="Couldn't load this panel" description="Something went wrong." />
        <div className="mt-3 flex justify-center">
          <button
            type="button"
            onClick={() => q.refetch()}
            className="rounded-md bg-gray-100 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 dark:bg-gray-700 dark:text-gray-200"
          >
            Retry
          </button>
        </div>
      </Card>
    );
  }
  if (!q.data) return null;
  return <>{render(q.data)}</>;
}

// Cap rendered table rows so a long query/page list can't bloat the DOM; disclose
// the truncation rather than hiding it silently (CLAUDE.md large-list rule).
const MAX_ROWS = 100;

function TrafficSourcesFigure({ sources }: { sources: TrafficSource[] }) {
  if (sources.length === 0) {
    return (
      <Card padding="lg">
        <EmptyState title="Traffic sources" description="No GA4 channel data in this period." />
      </Card>
    );
  }
  const shown = sources.slice(0, MAX_ROWS);
  return (
    <ChartFigure
      title="Where traffic comes from"
      subtitle={sources.length > MAX_ROWS ? `top ${MAX_ROWS} of ${formatNumber(sources.length)} channels` : undefined}
      table={{
        columns: [
          { key: 'channel', label: 'Channel' },
          { key: 'sessions', label: 'Sessions', numeric: true },
          { key: 'users', label: 'Users', numeric: true },
        ],
        rows: shown.map((s) => ({
          channel: s.channel,
          sessions: formatNumber(s.sessions),
          users: formatNumber(s.users),
        })),
        rowKey: (row) => String(row.channel),
      }}
    >
      <SimpleTable
        caption="Traffic by channel"
        cols={[
          { key: 'channel', label: 'Channel' },
          { key: 'sessions', label: 'Sessions', numeric: true },
          { key: 'users', label: 'Users', numeric: true },
        ]}
        rows={shown.map((s) => ({
          rowKey: s.channel,
          channel: <span className="truncate">{s.channel}</span>,
          sessions: formatNumber(s.sessions),
          users: formatNumber(s.users),
        }))}
      />
    </ChartFigure>
  );
}

function Ga4TopPagesFigure({ pages }: { pages: TopPage[] }) {
  if (pages.length === 0) {
    return (
      <Card padding="lg">
        <EmptyState title="Top pages" description="No GA4 page data in this period." />
      </Card>
    );
  }
  const shown = pages.slice(0, MAX_ROWS);
  return (
    <ChartFigure
      title="Most-visited pages"
      subtitle={pages.length > MAX_ROWS ? `top ${MAX_ROWS} of ${formatNumber(pages.length)} pages` : undefined}
      table={{
        columns: [
          { key: 'page', label: 'Page' },
          { key: 'sessions', label: 'Sessions', numeric: true },
          { key: 'users', label: 'Users', numeric: true },
        ],
        rows: shown.map((p) => ({
          page: p.page,
          sessions: formatNumber(p.sessions),
          users: formatNumber(p.users),
        })),
        rowKey: (row) => String(row.page),
      }}
    >
      <SimpleTable
        caption="GA4 top pages by sessions"
        cols={[
          { key: 'page', label: 'Page' },
          { key: 'sessions', label: 'Sessions', numeric: true },
          { key: 'users', label: 'Users', numeric: true },
        ]}
        rows={shown.map((p) => ({
          rowKey: p.page,
          page: (
            <span className="block max-w-xs truncate" title={p.page}>
              {p.page}
            </span>
          ),
          sessions: formatNumber(p.sessions),
          users: formatNumber(p.users),
        }))}
      />
    </ChartFigure>
  );
}

function GscQueriesFigure({ queries }: { queries: GscQuery[] }) {
  if (queries.length === 0) {
    return (
      <Card padding="lg">
        <EmptyState title="Top search queries" description="No Search Console queries in this period." />
      </Card>
    );
  }
  const shown = queries.slice(0, MAX_ROWS);
  return (
    <ChartFigure
      title="Top search queries"
      subtitle={queries.length > MAX_ROWS ? `top ${MAX_ROWS} of ${formatNumber(queries.length)} queries` : undefined}
      table={{
        columns: [
          { key: 'query', label: 'Query' },
          { key: 'clicks', label: 'Clicks', numeric: true },
          { key: 'impressions', label: 'Impressions', numeric: true },
          { key: 'ctr', label: 'CTR', numeric: true },
          { key: 'position', label: 'Avg Position', numeric: true },
        ],
        rows: shown.map((qr) => ({
          query: qr.query,
          clicks: formatNumber(qr.clicks),
          impressions: formatNumber(qr.impressions),
          ctr: formatPercent(qr.ctr),
          position: formatDecimal(qr.position),
        })),
        rowKey: (row) => String(row.query),
      }}
    >
      <SimpleTable
        caption="Search Console top queries"
        cols={[
          { key: 'query', label: 'Query' },
          { key: 'clicks', label: 'Clicks', numeric: true },
          { key: 'impressions', label: 'Impressions', numeric: true },
          { key: 'ctr', label: 'CTR', numeric: true },
          { key: 'position', label: 'Avg Position', numeric: true },
        ]}
        rows={shown.map((qr) => ({
          rowKey: qr.query,
          query: (
            <span className="block max-w-xs truncate" title={qr.query}>
              {qr.query}
            </span>
          ),
          clicks: formatNumber(qr.clicks),
          impressions: formatNumber(qr.impressions),
          ctr: formatPercent(qr.ctr),
          position: formatDecimal(qr.position),
        }))}
      />
    </ChartFigure>
  );
}

function GscPagesFigure({ pages }: { pages: GscPage[] }) {
  if (pages.length === 0) {
    return (
      <Card padding="lg">
        <EmptyState title="Top search pages" description="No Search Console pages in this period." />
      </Card>
    );
  }
  const shown = pages.slice(0, MAX_ROWS);
  return (
    <ChartFigure
      title="Top pages in search"
      subtitle={pages.length > MAX_ROWS ? `top ${MAX_ROWS} of ${formatNumber(pages.length)} pages` : undefined}
      table={{
        columns: [
          { key: 'page', label: 'Page' },
          { key: 'clicks', label: 'Clicks', numeric: true },
          { key: 'impressions', label: 'Impressions', numeric: true },
          { key: 'ctr', label: 'CTR', numeric: true },
          { key: 'position', label: 'Avg Position', numeric: true },
        ],
        rows: shown.map((p) => ({
          page: p.page,
          clicks: formatNumber(p.clicks),
          impressions: formatNumber(p.impressions),
          ctr: formatPercent(p.ctr),
          position: formatDecimal(p.position),
        })),
        rowKey: (row) => String(row.page),
      }}
    >
      <SimpleTable
        caption="Search Console top pages"
        cols={[
          { key: 'page', label: 'Page' },
          { key: 'clicks', label: 'Clicks', numeric: true },
          { key: 'impressions', label: 'Impressions', numeric: true },
          { key: 'ctr', label: 'CTR', numeric: true },
          { key: 'position', label: 'Avg Position', numeric: true },
        ]}
        rows={shown.map((p) => ({
          rowKey: p.page,
          page: (
            // GSC page URLs are long — truncate + min-w-0 so they don't blow out the layout.
            <span className="block max-w-xs truncate" title={p.page}>
              {p.page}
            </span>
          ),
          clicks: formatNumber(p.clicks),
          impressions: formatNumber(p.impressions),
          ctr: formatPercent(p.ctr),
          position: formatDecimal(p.position),
        }))}
      />
    </ChartFigure>
  );
}

interface SimpleCol {
  key: string;
  label: string;
  numeric?: boolean;
}
interface SimpleRow {
  rowKey: string;
  [key: string]: ReactNode;
}

/** A small accessible table (sr-only caption, tabular-nums on numeric cols,
 *  min-w-0/truncate handled by the cell content) used inside ChartFigure for the
 *  GA4/GSC breakdown panels. */
function SimpleTable({ caption, cols, rows }: { caption: string; cols: SimpleCol[]; rows: SimpleRow[] }) {
  return (
    <div className="max-h-96 overflow-auto">
      <table className="min-w-full text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="sticky top-0 bg-white dark:bg-gray-800">
          <tr className="border-b border-gray-200 dark:border-gray-700">
            {cols.map((c) => (
              <th
                key={c.key}
                scope="col"
                className={'px-3 py-2 font-medium text-gray-500 ' + (c.numeric ? 'text-right' : 'text-left')}
              >
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.rowKey} className="border-b border-gray-100 dark:border-gray-700/50">
              {cols.map((c) => (
                <td
                  key={c.key}
                  className={
                    'min-w-0 px-3 py-2 text-gray-700 dark:text-gray-300 ' +
                    (c.numeric ? 'text-right tabular-nums' : 'text-left')
                  }
                >
                  {r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Ga4Section({ analytics }: { analytics: AnalyticsResponse }) {
  const totals = analytics.ga4_totals;
  if (!totals) {
    return (
      <Card padding="lg">
        <EmptyState title="Google Analytics" description="No GA4 data in this period." />
      </Card>
    );
  }

  return (
    <section className="space-y-4" aria-label="Google Analytics">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Google Analytics</h2>

      {/* Data-trust disclosures (A11/H3) — not color alone, announced politely. */}
      {(totals.is_sampled || totals.is_data_golden === false) && (
        <Card padding="md">
          <div className="space-y-1 text-sm text-gray-600 dark:text-gray-300" aria-live="polite">
            {totals.is_sampled && (
              <p>
                <span className="font-medium">Sampled:</span> GA4 returned a sampled subset for this range, so figures
                are estimates.
              </p>
            )}
            {totals.is_data_golden === false && (
              <p>
                <span className="font-medium">Data still finalizing:</span> recent days may not tie out to final
                totals yet.
              </p>
            )}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <KpiCard label="Sessions" value={formatNumber(totals.sessions)} />
        <KpiCard label="Users" value={formatNumber(totals.users)} />
        <KpiCard label="New Users" value={formatNumber(totals.new_users)} />
        <KpiCard label="Engaged Sessions" value={formatNumber(totals.engaged_sessions)} />
        <KpiCard label="Key Events" value={formatNumber(totals.key_events)} />
        <KpiCard label="Engagement Rate" value={formatPercent(totals.engagement_rate)} />
      </div>

      <Ga4TrendChart points={analytics.ga4_series} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <TrafficSourcesFigure sources={analytics.traffic_sources} />
        <Ga4TopPagesFigure pages={analytics.top_pages} />
      </div>
    </section>
  );
}

function GscSection({ analytics }: { analytics: AnalyticsResponse }) {
  const totals = analytics.gsc_totals;
  if (!totals) {
    return (
      <Card padding="lg">
        <EmptyState title="Search Console" description="No Search Console data in this period." />
      </Card>
    );
  }

  return (
    <section className="space-y-4" aria-label="Search Console">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Search Console</h2>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Clicks" value={formatNumber(totals.clicks)} />
        <KpiCard label="Impressions" value={formatNumber(totals.impressions)} />
        <KpiCard label="CTR" value={formatPercent(totals.ctr)} />
        <KpiCard label="Avg Position" value={formatDecimal(totals.position)} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <GscQueriesFigure queries={analytics.gsc_queries} />
        <GscPagesFigure pages={analytics.gsc_pages} />
      </div>
    </section>
  );
}

// PageSpeed scores are 0..100 — render with no decimals; null → em-dash via helper.
function scoreCell(value: SiteHealthSnapshotOut['performance_score']) {
  return formatNumber(value);
}

function SiteHealthSection({ data }: { data: SiteHealthResponse }) {
  const latest = data.latest;
  if (latest.length === 0) {
    return (
      <Card padding="lg">
        <EmptyState title="Site Health" description="No PageSpeed snapshot yet." />
      </Card>
    );
  }

  return (
    <section className="space-y-4" aria-label="Site Health">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">Site Health (PageSpeed)</h2>
      <Card padding="md">
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <caption className="sr-only">PageSpeed scores and Core Web Vitals by URL and strategy</caption>
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th scope="col" className="px-3 py-2 text-left font-medium text-gray-500">
                  URL
                </th>
                <th scope="col" className="px-3 py-2 text-left font-medium text-gray-500">
                  Device
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">
                  Performance
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">
                  SEO
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">
                  Accessibility
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">
                  Best Practices
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">
                  LCP (ms)
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">
                  CLS
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">
                  INP (ms)
                </th>
              </tr>
            </thead>
            <tbody>
              {latest.map((s) => (
                <tr key={`${s.url}:${s.strategy}`} className="border-b border-gray-100 dark:border-gray-700/50">
                  <td className="px-3 py-2 text-gray-700 dark:text-gray-300">
                    <span className="block max-w-xs truncate" title={s.url}>
                      {s.url}
                    </span>
                  </td>
                  <td className="px-3 py-2 capitalize text-gray-700 dark:text-gray-300">{s.strategy}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                    {scoreCell(s.performance_score)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                    {scoreCell(s.seo_score)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                    {scoreCell(s.accessibility_score)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                    {scoreCell(s.best_practices_score)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                    {formatNumber(s.lcp_ms)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                    {formatDecimal(s.cls)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                    {formatNumber(s.inp_ms)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </section>
  );
}

export function WebsiteAnalyticsTab({
  companyId,
  preset,
}: {
  companyId: number;
  preset: Exclude<RangePreset, 'custom'>;
}) {
  const window = useMemo(() => presetRange(preset), [preset]);
  const key = [companyId, window.date_from, window.date_to] as const;

  const analyticsQ = useQuery({
    queryKey: ['mktg-analytics', ...key],
    queryFn: () => getAnalytics(companyId, window),
  });
  const siteHealthQ = useQuery({
    queryKey: ['mktg-site-health', ...key],
    queryFn: () => getSiteHealth(companyId, window),
  });
  const syncQ = useQuery({ queryKey: ['mktg-sync', companyId], queryFn: () => getSyncStatus(companyId) });

  const connections = syncQ.data?.connections ?? [];
  const analytics = analyticsQ.data;

  return (
    <div className="space-y-6">
      {syncQ.data && (
        <DataTrustBadge sources={syncToSources(connections)} timezone={analytics?.data_trust.timezone} />
      )}

      <QueryPanel
        q={analyticsQ}
        height={320}
        render={(data) => {
          if (!data.ga4_configured && !data.gsc_configured) {
            return (
              <Card padding="lg">
                <EmptyState
                  title="No web analytics connected"
                  description="Connect this client's GA4 / Search Console accounts in the admin panel to populate this section."
                />
              </Card>
            );
          }
          return (
            <div className="space-y-8">
              {data.ga4_configured && <Ga4Section analytics={data} />}
              {data.gsc_configured && <GscSection analytics={data} />}
            </div>
          );
        }}
      />

      <QueryPanel q={siteHealthQ} height={160} render={(data) => <SiteHealthSection data={data} />} />
    </div>
  );
}
