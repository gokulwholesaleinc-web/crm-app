import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { Ga4SeriesPoint } from '../../../../api/marketing';
import { getBrandColor } from '../../../../utils/chartPalette';
import { formatDate, formatNumber } from '../../utils/format';
import { ChartFigure } from '../ChartFigure';

interface Props {
  points: Ga4SeriesPoint[];
}

/** Daily GA4 sessions + users line. Deterministic (no animation) for report
 *  parity; mirrors SpendTrendChart's shape with two series. */
export function Ga4TrendChart({ points }: Props) {
  const sessionsColor = getBrandColor('primary', '#2563eb');
  const usersColor = getBrandColor('secondary', '#06b6d4');

  if (points.length === 0) {
    return (
      <ChartFigure title="Sessions and users over time">
        <div className="flex h-[240px] items-center justify-center text-sm text-gray-400">
          No GA4 traffic in this period
        </div>
      </ChartFigure>
    );
  }

  const data = points.map((p) => ({
    date: p.date,
    sessions: Number(p.sessions ?? 0),
    users: Number(p.users ?? 0),
  }));

  const table = {
    columns: [
      { key: 'date', label: 'Date' },
      { key: 'sessions', label: 'Sessions', numeric: true },
      { key: 'users', label: 'Users', numeric: true },
    ],
    rows: points.map((p) => ({
      date: formatDate(p.date),
      sessions: formatNumber(p.sessions),
      users: formatNumber(p.users),
    })),
    rowKey: (row: Record<string, unknown>) => String(row.date),
  };

  return (
    <ChartFigure title="Sessions and users over time" table={table}>
      <div style={{ height: 240 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="text-gray-200 dark:text-gray-700" />
            <XAxis dataKey="date" tickFormatter={(d: string) => formatDate(d)} fontSize={11} minTickGap={24} />
            <YAxis tickFormatter={(v: number) => formatNumber(v, true)} fontSize={11} width={48} />
            <Tooltip
              formatter={(value, name) => [formatNumber(value as number), name]}
              labelFormatter={(label) => formatDate(label as string, true)}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="sessions"
              name="Sessions"
              stroke={sessionsColor}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="users"
              name="Users"
              stroke={usersColor}
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </ChartFigure>
  );
}
