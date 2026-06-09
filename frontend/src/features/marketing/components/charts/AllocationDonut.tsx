import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import type { AllocationSlice } from '../../../../api/marketing';
import { getChartPalette } from '../../../../utils/chartPalette';
import { formatCurrency } from '../../utils/format';
import { ChartFigure } from '../ChartFigure';

const PLATFORM_LABEL: Record<string, string> = {
  google_ads: 'Google Ads',
  meta_ads: 'Meta',
  instagram: 'Instagram',
  facebook: 'Facebook',
  tiktok: 'TikTok',
  linkedin: 'LinkedIn',
};

interface Props {
  slices: AllocationSlice[];
  currency: string;
  withheldReason: string | null;
}

/** Spend-by-platform donut. When currencies differ across the client's accounts
 *  the blended total is withheld (A9) — we show a reason, not a fake sum. */
export function AllocationDonut({ slices, currency, withheldReason }: Props) {
  const palette = getChartPalette();
  const data = slices
    .map((s) => ({ name: PLATFORM_LABEL[s.platform] ?? s.platform, value: Number(s.spend ?? 0) }))
    .filter((d) => d.value > 0);

  const table = {
    columns: [
      { key: 'name', label: 'Platform' },
      { key: 'spend', label: 'Spend', numeric: true },
    ],
    rows: slices.map((s) => ({
      name: PLATFORM_LABEL[s.platform] ?? s.platform,
      spend: formatCurrency(s.spend, currency),
    })),
  };

  return (
    <ChartFigure title="Spend allocation" subtitle="Share of spend by platform" table={withheldReason ? undefined : table}>
      {withheldReason ? (
        <div className="flex h-[240px] items-center justify-center px-6 text-center text-sm text-gray-500 dark:text-gray-400">
          Blended spend is withheld because this client's accounts report in
          different currencies. Per-platform spend is still shown above.
        </div>
      ) : data.length === 0 ? (
        <div className="flex h-[240px] items-center justify-center text-sm text-gray-400">No spend in this period</div>
      ) : (
        <div style={{ height: 240 }}>
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data} dataKey="value" nameKey="name" innerRadius={56} outerRadius={88} paddingAngle={2} isAnimationActive={false}>
                {data.map((_, i) => (
                  <Cell key={i} fill={palette[i % palette.length]} />
                ))}
              </Pie>
              <Tooltip formatter={(value, name) => [formatCurrency(value as number, currency), name as string]} />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}
    </ChartFigure>
  );
}
