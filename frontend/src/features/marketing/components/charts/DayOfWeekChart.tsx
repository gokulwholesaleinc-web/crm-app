import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { DayOfWeekCard } from '../../../../api/marketing';
import { getBrandColor } from '../../../../utils/chartPalette';
import { formatCurrency, formatDecimal, formatNumber } from '../../utils/format';
import { ChartFigure } from '../ChartFigure';

interface Props {
  days: DayOfWeekCard[];
  currency: string;
  /** BLEND: when >1 ad platform contributed, ROAS is withheld (non-additive). */
  conversionsWithheld?: boolean;
}

/** Spend by day of week (Mon..Sun) — a bar chart over ratio-of-sums DOW buckets. */
export function DayOfWeekChart({ days, currency, conversionsWithheld }: Props) {
  const color = getBrandColor('primary', '#2563eb');

  if (days.length === 0) {
    return (
      <ChartFigure title="Spend by day of week">
        <div className="flex h-[240px] items-center justify-center text-sm text-gray-400">
          No data in this period
        </div>
      </ChartFigure>
    );
  }

  const data = days.map((d) => ({ label: d.label, spend: Number(d.spend ?? 0) }));
  const table = {
    columns: [
      { key: 'label', label: 'Day' },
      { key: 'spend', label: 'Spend', numeric: true },
      { key: 'clicks', label: 'Clicks', numeric: true },
      { key: 'roas', label: 'ROAS', numeric: true },
    ],
    rows: days.map((d) => ({
      label: d.label,
      spend: formatCurrency(d.spend, currency),
      clicks: formatNumber(d.clicks),
      roas: conversionsWithheld ? '—' : formatDecimal(d.roas),
    })),
    rowKey: (row: Record<string, unknown>) => String(row.label),
  };

  return (
    <ChartFigure title="Spend by day of week" table={table}>
      <div style={{ height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="currentColor"
              className="text-gray-200 dark:text-gray-700"
            />
            <XAxis dataKey="label" fontSize={11} />
            <YAxis tickFormatter={(v: number) => formatCurrency(v, currency, true)} fontSize={11} width={56} />
            <Tooltip formatter={(value) => formatCurrency(value as number, currency)} />
            <Bar dataKey="spend" fill={color} radius={[4, 4, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </ChartFigure>
  );
}
