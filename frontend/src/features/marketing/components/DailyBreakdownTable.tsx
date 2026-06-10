import { Card } from '../../../components/ui';
import { EmptyState } from '../../../components/ui/EmptyState';
import type { BreakdownRow } from '../../../api/marketing';
import { formatCurrency, formatDate, formatDecimal, formatNumber } from '../utils/format';
import { platformLabel } from '../utils/platformLabel';

interface Props {
  rows: BreakdownRow[];
  currency: string;
}

// Cap the rendered rows so the 'All' preset (≈ days × platforms) can't put a huge
// table in the DOM; disclose the truncation rather than hiding it silently.
const MAX_ROWS = 120;

/** Per-(date, platform) breakdown. Conversions/ROAS here are per-platform (grouped
 *  by platform server-side), so they're meaningful even when multiple ad platforms
 *  are connected — this is where Google vs Meta show up distinctly per day. */
export function DailyBreakdownTable({ rows, currency }: Props) {
  if (rows.length === 0) {
    return (
      <Card padding="lg">
        <EmptyState title="Daily breakdown" description="No spend in this period." />
      </Card>
    );
  }

  const shown = rows.slice(0, MAX_ROWS);
  const cols: Array<{ key: keyof BreakdownRow | 'platform_label'; label: string; numeric?: boolean }> = [
    { key: 'date', label: 'Date' },
    { key: 'platform_label', label: 'Platform' },
    { key: 'spend', label: 'Spend', numeric: true },
    { key: 'clicks', label: 'Clicks', numeric: true },
    { key: 'conversions', label: 'Conv.', numeric: true },
    { key: 'roas', label: 'ROAS', numeric: true },
  ];

  return (
    <Card padding="md">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Daily breakdown</h3>
        {rows.length > MAX_ROWS && (
          <span className="text-xs text-gray-400">
            showing most recent {MAX_ROWS} of {formatNumber(rows.length)}
          </span>
        )}
      </div>
      <div className="max-h-96 overflow-auto">
        <table className="min-w-full text-sm">
          <caption className="sr-only">Daily spend and conversions by platform</caption>
          <thead className="sticky top-0 bg-white dark:bg-gray-800">
            <tr className="border-b border-gray-200 dark:border-gray-700">
              {cols.map((c) => (
                <th
                  key={c.key}
                  scope="col"
                  className={
                    'px-3 py-2 font-medium text-gray-500 ' + (c.numeric ? 'text-right' : 'text-left')
                  }
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr
                key={`${r.date}:${r.platform}`}
                className="border-b border-gray-100 dark:border-gray-700/50"
              >
                <td className="px-3 py-2 text-gray-700 dark:text-gray-300">{formatDate(r.date)}</td>
                <td className="px-3 py-2 text-gray-700 dark:text-gray-300">{platformLabel(r.platform)}</td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                  {/* FE-1: use the row's own currency (multi-currency clients), not one
                      client-wide currency, so EUR spend isn't labelled '$'. */}
                  {formatCurrency(r.spend, r.currency ?? currency)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                  {formatNumber(r.clicks)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                  {formatNumber(r.conversions)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-gray-700 dark:text-gray-300">
                  {formatDecimal(r.roas)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
