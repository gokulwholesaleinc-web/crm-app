import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { listCompanies } from '../../api/companies';
import {
  getAllocation,
  getOverview,
  getSeries,
  getSyncStatus,
  type ConnectionSyncStatus,
} from '../../api/marketing';
import { Card, SearchableSelect } from '../../components/ui';
import { EmptyState } from '../../components/ui/EmptyState';
import { AllocationDonut } from './components/charts/AllocationDonut';
import { SpendTrendChart } from './components/charts/SpendTrendChart';
import { DataTrustBadge, type SourceFreshness } from './components/DataTrustBadge';
import { KpiCard } from './components/KpiCard';
import { formatCardValue, toKpiDelta } from './utils/cardMapping';
import { isValidPreset, PRESET_LABELS, presetRange, type RangePreset } from './utils/dateRange';

const PLATFORM_LABEL: Record<string, string> = {
  google_ads: 'Google Ads',
  ga4: 'GA4',
  gsc: 'Search Console',
  pagespeed: 'PageSpeed',
  meta_ads: 'Meta',
};

type TabKey = 'paid' | 'analytics' | 'campaigns';
const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'paid', label: 'Paid Media' },
  { key: 'analytics', label: 'Website Analytics' },
  { key: 'campaigns', label: 'Campaigns' },
];

export default function ReportingPage() {
  const [params, setParams] = useSearchParams();
  const companyId = params.get('company') ? Number(params.get('company')) : null;
  const presetParam = params.get('range');
  const preset: Exclude<RangePreset, 'custom'> =
    isValidPreset(presetParam) && presetParam !== 'custom' ? (presetParam as Exclude<RangePreset, 'custom'>) : '30d';
  const tab = (params.get('tab') as TabKey) || 'paid';

  const { data: companiesData } = useQuery({
    queryKey: ['reporting-companies'],
    queryFn: () => listCompanies({ page_size: 200 }),
  });
  const companies = companiesData?.items ?? [];

  // Default to the first client once the list loads and nothing is selected.
  const effectiveCompanyId = companyId ?? companies[0]?.id ?? null;

  const update = (next: Record<string, string>) => {
    const merged = new URLSearchParams(params);
    Object.entries(next).forEach(([k, v]) => merged.set(k, v));
    setParams(merged, { replace: true });
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <header className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">Marketing Analytics</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Spend vs platform-attributed conversion value, per client.
          </p>
        </div>
        <div className="w-full sm:w-72">
          <SearchableSelect
            label="Client"
            value={effectiveCompanyId}
            onChange={(v) => v !== null && update({ company: String(v) })}
            options={companies.map((c) => ({ value: c.id, label: c.name }))}
            placeholder="Select a client…"
          />
        </div>
      </header>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        {(Object.keys(PRESET_LABELS) as Array<keyof typeof PRESET_LABELS>).map((p) => (
          <button
            key={p}
            type="button"
            onClick={() => update({ range: p })}
            aria-pressed={preset === p}
            className={
              'rounded-md px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 ' +
              (preset === p
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-700 dark:text-gray-200 dark:hover:bg-gray-600')
            }
          >
            {PRESET_LABELS[p]}
          </button>
        ))}
      </div>

      <nav className="mb-6 flex gap-1 border-b border-gray-200 dark:border-gray-700" aria-label="Report sections">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => update({ tab: t.key })}
            aria-current={tab === t.key ? 'page' : undefined}
            className={
              'border-b-2 px-4 py-2 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 ' +
              (tab === t.key
                ? 'border-blue-600 text-blue-700 dark:text-blue-400'
                : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300')
            }
          >
            {t.label}
          </button>
        ))}
      </nav>

      {effectiveCompanyId === null ? (
        <EmptyState title="No client selected" description="Choose a client to view their marketing analytics." />
      ) : tab === 'paid' ? (
        <PaidMediaTab companyId={effectiveCompanyId} preset={preset} />
      ) : (
        <Card padding="lg">
          <EmptyState
            title={`${TABS.find((t) => t.key === tab)?.label} view`}
            description="Connect this client's GA4 / Ads accounts in the admin panel to populate this section."
          />
        </Card>
      )}
    </div>
  );
}

function syncToSources(connections: ConnectionSyncStatus[]): SourceFreshness[] {
  return connections.map((c) => ({
    source: PLATFORM_LABEL[c.platform] ?? c.platform,
    lastSyncedAt: c.last_synced_at,
    status: c.status,
  }));
}

function PaidMediaTab({ companyId, preset }: { companyId: number; preset: Exclude<RangePreset, 'custom'> }) {
  const window = useMemo(() => presetRange(preset), [preset]);

  const overviewQ = useQuery({
    queryKey: ['mktg-overview', companyId, window.date_from, window.date_to],
    queryFn: () => getOverview(companyId, window),
  });
  const seriesQ = useQuery({
    queryKey: ['mktg-series', companyId, window.date_from, window.date_to],
    queryFn: () => getSeries(companyId, window),
  });
  const allocationQ = useQuery({
    queryKey: ['mktg-allocation', companyId, window.date_from, window.date_to],
    queryFn: () => getAllocation(companyId, window),
  });
  const syncQ = useQuery({
    queryKey: ['mktg-sync', companyId],
    queryFn: () => getSyncStatus(companyId),
  });

  const connections = syncQ.data?.connections ?? [];
  const currency = connections.find((c) => c.currency)?.currency ?? 'USD';
  const overview = overviewQ.data;
  const cards = overview?.cards ?? [];
  const loading = overviewQ.isLoading;

  return (
    <div className="space-y-6">
      {syncQ.data && (
        <DataTrustBadge
          sources={syncToSources(connections)}
          timezone={overview?.data_trust.timezone}
        />
      )}

      {overviewQ.isError ? (
        <Card padding="lg">
          <EmptyState variant="error" title="Couldn't load overview" description="Try again in a moment." />
        </Card>
      ) : overview?.withheld_reason ? (
        <Card padding="lg">
          <EmptyState
            title="Blended KPIs withheld"
            description="This client's accounts report in more than one currency, so blended totals aren't shown. Per-platform spend is available below."
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {(loading ? Array.from({ length: 5 }) : cards).map((c, i) => {
            const card = c as (typeof cards)[number] | undefined;
            return (
              <KpiCard
                key={card?.key ?? i}
                label={card?.label ?? '—'}
                value={card ? formatCardValue(card, currency) : '—'}
                delta={card ? toKpiDelta(card) : null}
                timeframe={card?.timeframe ?? undefined}
                isLoading={loading}
              />
            );
          })}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {seriesQ.data && <SpendTrendChart points={seriesQ.data.points} currency={currency} />}
        </div>
        <div>
          {allocationQ.data && (
            <AllocationDonut
              slices={allocationQ.data.slices}
              currency={currency}
              withheldReason={allocationQ.data.withheld_reason}
            />
          )}
        </div>
      </div>
    </div>
  );
}
