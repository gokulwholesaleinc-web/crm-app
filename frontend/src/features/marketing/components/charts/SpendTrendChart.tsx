import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { SeriesPoint } from '../../../../api/marketing';
import { getBrandColor } from '../../../../utils/chartPalette';
import { formatCurrency, formatDate, formatNumber } from '../../utils/format';
import { ChartFigure } from '../ChartFigure';

interface Props {
  points: SeriesPoint[];
  currency: string;
}

/** Daily spend line. Deterministic (no animation) for report parity; the most
 *  recent provisional days are disclosed via the figure subtitle + the table. */
export function SpendTrendChart({ points, currency }: Props) {
  const color = getBrandColor('primary', '#2563eb');
  const data = points.map((p) => ({ date: p.date, spend: Number(p.spend ?? 0) }));
  const table = {
    columns: [
      { key: 'date', label: 'Date' },
      { key: 'spend', label: 'Spend', numeric: true },
      { key: 'clicks', label: 'Clicks', numeric: true },
    ],
    rows: points.map((p) => ({
      date: formatDate(p.date) + (p.is_provisional ? ' *' : ''),
      spend: formatCurrency(p.spend, currency),
      clicks: formatNumber(p.clicks),
    })),
  };

  return (
    <ChartFigure title="Daily spend" subtitle="* most recent days are still settling" table={table}>
      <div style={{ height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-gray-200 dark:text-gray-700" />
            <XAxis dataKey="date" tickFormatter={(d: string) => formatDate(d)} fontSize={11} minTickGap={24} />
            <YAxis tickFormatter={(v: number) => formatCurrency(v, currency, true)} fontSize={11} width={56} />
            <Tooltip
              formatter={(value) => formatCurrency(value as number, currency)}
              labelFormatter={(label) => formatDate(label as string, true)}
            />
            <Line type="monotone" dataKey="spend" stroke={color} strokeWidth={2} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartFigure>
  );
}
