import { ReactNode, useId, useState } from 'react';
import clsx from 'clsx';

export interface ChartTableColumn {
  key: string;
  label: string;
  /** Right-align numeric columns; they also get tabular-nums. */
  numeric?: boolean;
}

export interface ChartFigureProps {
  /** States the *insight*, not just "Line chart" — becomes the figure aria-label. */
  title: string;
  subtitle?: string;
  children: ReactNode;
  /** The same aggregated data behind the chart, exposed as an accessible table
   *  (WCAG: a non-visual path to the data; doubles as the PDF data source).
   *  `rowKey` yields a stable React key per row (avoids index-as-key reconciliation
   *  glitches); defaults to the row index. */
  table?: {
    columns: ChartTableColumn[];
    rows: Array<Record<string, ReactNode>>;
    rowKey?: (row: Record<string, ReactNode>, index: number) => string;
  };
  className?: string;
}

/**
 * Wraps a chart in a `<figure>` + `<figcaption>` with an aria-label stating the
 * insight, and offers a "Show data as table" toggle that reveals an accessible
 * `<table>` of the underlying values (§C chart-a11y rule). The chart itself is
 * passed as children so this stays charting-library agnostic.
 */
export function ChartFigure({ title, subtitle, children, table, className }: ChartFigureProps) {
  const [showTable, setShowTable] = useState(false);
  const tableId = useId();

  return (
    <figure
      aria-label={title}
      className={clsx(
        'flex flex-col rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800',
        className,
      )}
    >
      <figcaption className="mb-2 flex items-start justify-between gap-2">
        <span className="min-w-0">
          <span className="block truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
            {title}
          </span>
          {subtitle && (
            <span className="block truncate text-xs text-gray-400">{subtitle}</span>
          )}
        </span>
        {table && (
          <button
            type="button"
            onClick={() => setShowTable((v) => !v)}
            aria-expanded={showTable}
            aria-controls={tableId}
            className="shrink-0 rounded px-2 py-1 text-xs font-medium text-gray-500 hover:bg-gray-100 hover:text-gray-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 dark:text-gray-400 dark:hover:bg-gray-700"
          >
            {showTable ? 'Show chart' : 'Show data as table'}
          </button>
        )}
      </figcaption>

      {/* Chart is hidden (not unmounted) when the table is shown so toggling is cheap. */}
      <div className={clsx(showTable && table ? 'hidden' : 'block')}>{children}</div>

      {table && (
        <div id={tableId} className={clsx('overflow-x-auto', showTable ? 'block' : 'hidden')}>
          {/* Rows render only while expanded so a long table (e.g. the 'All' preset)
              isn't kept in the DOM alongside the chart (CLAUDE.md large-list rule). */}
          {showTable && (
            <table className="min-w-full text-sm">
              <caption className="sr-only">{title}</caption>
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  {table.columns.map((col) => (
                    <th
                      key={col.key}
                      scope="col"
                      className={clsx(
                        'px-3 py-2 font-medium text-gray-500',
                        col.numeric ? 'text-right' : 'text-left',
                      )}
                    >
                      {col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {table.rows.map((row, i) => (
                  <tr
                    key={table.rowKey ? table.rowKey(row, i) : i}
                    className="border-b border-gray-100 dark:border-gray-700/50"
                  >
                    {table.columns.map((col) => (
                      <td
                        key={col.key}
                        className={clsx(
                          'px-3 py-2 text-gray-700 dark:text-gray-300',
                          col.numeric ? 'text-right tabular-nums' : 'text-left',
                        )}
                      >
                        {row[col.key]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </figure>
  );
}
