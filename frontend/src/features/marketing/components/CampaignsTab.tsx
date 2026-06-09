import { useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import {
  getAdGroups,
  getCampaigns,
  getSyncStatus,
  type AdGroupRow,
  type CampaignRow,
} from '../../../api/marketing';
import { Card } from '../../../components/ui';
import { EmptyState } from '../../../components/ui/EmptyState';
import { DataTrustBadge } from './DataTrustBadge';
import { KpiCard } from './KpiCard';
import { QueryPanel } from './QueryPanel';
import { type RangePreset, presetRange } from '../utils/dateRange';
import { formatCurrency, formatDecimal, formatNumber, formatPercent } from '../utils/format';
import { platformLabel } from '../utils/platformLabel';
import { syncToSources } from '../utils/syncToSources';

// Cap rendered rows so a long campaign/ad-group list can't bloat the DOM; the
// truncation is disclosed in the header rather than hidden silently.
const MAX_ROWS = 100;

/** Coerce a Numish to a number for client-side summing of per-platform rows. */
function toNum(v: CampaignRow['spend']): number {
  if (v === null || v === undefined || v === '') return 0;
  const n = typeof v === 'string' ? Number(v) : v;
  return Number.isFinite(n) ? n : 0;
}

function CampaignTable({ campaigns, currency }: { campaigns: CampaignRow[]; currency: string }) {
  if (campaigns.length === 0) {
    return (
      <Card padding="lg">
        <EmptyState title="Campaigns" description="No campaign activity in this period." />
      </Card>
    );
  }
  const shown = campaigns.slice(0, MAX_ROWS);
  return (
    <Card padding="md">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Campaign breakdown</h3>
        {campaigns.length > MAX_ROWS && (
          <span className="text-xs text-gray-400">
            showing {MAX_ROWS} of {formatNumber(campaigns.length)}
          </span>
        )}
      </div>
      <div className="max-h-96 overflow-auto">
        <table className="min-w-full text-sm">
          <caption className="sr-only">Campaign performance by platform</caption>
          <thead className="sticky top-0 bg-white dark:bg-gray-800">
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th scope="col" className="px-3 py-2 text-left font-medium text-gray-500">Campaign</th>
              <th scope="col" className="px-3 py-2 text-left font-medium text-gray-500">Platform</th>
              <th scope="col" className="px-3 py-2 text-left font-medium text-gray-500">Status</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">Clicks</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">Impressions</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">Conversions</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">Cost</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">CPC</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">Conv. Rate</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">ROAS</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((c, i) => (
              <tr
                key={`${c.connection_id}:${c.campaign_id ?? i}`}
                className="border-b border-gray-100 dark:border-gray-700/50"
              >
                <td className="px-3 py-2 text-gray-700 dark:text-gray-300">
                  <span className="block max-w-[14rem] truncate" title={c.name ?? c.campaign_id ?? undefined}>
                    {c.name ?? c.campaign_id ?? '—'}
                  </span>
                </td>
                <td className="px-3 py-2 text-gray-700 dark:text-gray-300">{platformLabel(c.platform)}</td>
                <td className="px-3 py-2 capitalize text-gray-700 dark:text-gray-300">{c.status ?? '—'}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">{formatNumber(c.clicks)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">{formatNumber(c.impressions)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">{formatNumber(c.conversions)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                  {formatCurrency(c.spend, currency)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                  {formatCurrency(c.cpc, currency)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">{formatPercent(c.conversion_rate)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">{formatDecimal(c.roas)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function AdGroupTable({ adgroups, currency }: { adgroups: AdGroupRow[]; currency: string }) {
  if (adgroups.length === 0) {
    return (
      <Card padding="lg">
        <EmptyState title="Ad groups" description="No ad group activity in this period." />
      </Card>
    );
  }
  const shown = adgroups.slice(0, MAX_ROWS);
  return (
    <Card padding="md">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Ad group breakdown</h3>
        {adgroups.length > MAX_ROWS && (
          <span className="text-xs text-gray-400">
            showing {MAX_ROWS} of {formatNumber(adgroups.length)}
          </span>
        )}
      </div>
      <div className="max-h-96 overflow-auto">
        <table className="min-w-full text-sm">
          <caption className="sr-only">Ad group performance by campaign</caption>
          <thead className="sticky top-0 bg-white dark:bg-gray-800">
            <tr className="border-b border-gray-200 dark:border-gray-700">
              <th scope="col" className="px-3 py-2 text-left font-medium text-gray-500">Ad Group</th>
              <th scope="col" className="px-3 py-2 text-left font-medium text-gray-500">Campaign</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">Clicks</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">Impressions</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">Conversions</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">Cost</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">CPC</th>
              <th scope="col" className="px-3 py-2 text-right font-medium text-gray-500">ROAS</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((a, i) => (
              <tr
                key={`${a.connection_id}:${a.adgroup_id ?? i}`}
                className="border-b border-gray-100 dark:border-gray-700/50"
              >
                <td className="px-3 py-2 text-gray-700 dark:text-gray-300">
                  <span className="block max-w-[14rem] truncate" title={a.name ?? a.adgroup_id ?? undefined}>
                    {a.name ?? a.adgroup_id ?? '—'}
                  </span>
                </td>
                <td className="px-3 py-2 text-gray-700 dark:text-gray-300">
                  <span className="block max-w-[12rem] truncate" title={a.campaign_id ?? undefined}>
                    {a.campaign_id ?? '—'}
                  </span>
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">{formatNumber(a.clicks)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">{formatNumber(a.impressions)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">{formatNumber(a.conversions)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                  {formatCurrency(a.spend, currency)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                  {formatCurrency(a.cpc, currency)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">{formatDecimal(a.roas)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function CampaignsTab({
  companyId,
  preset,
}: {
  companyId: number;
  preset: Exclude<RangePreset, 'custom'>;
}) {
  const window = useMemo(() => presetRange(preset), [preset]);
  const key = [companyId, window.date_from, window.date_to] as const;

  const campaignsQ = useQuery({
    queryKey: ['mktg-campaigns', ...key],
    queryFn: () => getCampaigns(companyId, window),
  });
  const adGroupsQ = useQuery({
    queryKey: ['mktg-adgroups', ...key],
    queryFn: () => getAdGroups(companyId, window),
  });
  const syncQ = useQuery({ queryKey: ['mktg-sync', companyId], queryFn: () => getSyncStatus(companyId) });

  const connections = syncQ.data?.connections ?? [];
  const currency = connections.find((c) => c.currency)?.currency ?? 'USD';
  const campaigns = campaignsQ.data;

  // Sum per-campaign rows for a displayed total. These are per-platform rows, so a
  // simple sum of the displayed rows is the right "total" for this view.
  const { totalSpend, totalConversions } = useMemo(() => {
    const rows = campaigns?.campaigns ?? [];
    let spend = 0;
    let conv = 0;
    for (const r of rows) {
      spend += toNum(r.spend);
      conv += toNum(r.conversions);
    }
    return { totalSpend: spend, totalConversions: conv };
  }, [campaigns]);

  const loading = campaignsQ.isLoading;

  return (
    <div className="space-y-6">
      {syncQ.data && (
        <DataTrustBadge sources={syncToSources(connections)} timezone={campaigns?.data_trust.timezone} />
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <KpiCard
          label="Active Campaigns"
          value={loading ? '—' : formatNumber(campaigns?.active_campaigns ?? 0)}
          isLoading={loading}
        />
        <KpiCard label="Total Spend" value={loading ? '—' : formatCurrency(totalSpend, currency)} isLoading={loading} />
        <KpiCard
          label="Total Conversions"
          value={loading ? '—' : formatNumber(totalConversions)}
          isLoading={loading}
        />
      </div>

      <QueryPanel q={campaignsQ} render={(data) => <CampaignTable campaigns={data.campaigns} currency={currency} />} />
      <QueryPanel q={adGroupsQ} render={(data) => <AdGroupTable adgroups={data.adgroups} currency={currency} />} />
    </div>
  );
}
