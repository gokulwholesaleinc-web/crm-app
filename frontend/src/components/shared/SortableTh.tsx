import type { SortDirection } from '../../hooks/useTableSort';

interface SortableThProps {
  field: string;
  label: string;
  sortBy: string | undefined;
  sortDir: SortDirection | undefined;
  onToggle: (field: string) => void;
  align?: 'left' | 'right';
}

const BASE_TH_CLASS =
  'px-6 py-3 text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider';

/**
 * Click-to-sort table header used across list pages. Pair with `useTableSort`.
 * Shows a directional indicator and exposes `aria-sort` for assistive tech.
 */
export function SortableTh({
  field,
  label,
  sortBy,
  sortDir,
  onToggle,
  align = 'left',
}: SortableThProps) {
  const isActive = sortBy === field;
  let ariaSort: 'ascending' | 'descending' | 'none' = 'none';
  if (isActive) {
    ariaSort = sortDir === 'asc' ? 'ascending' : 'descending';
  }
  const indicator = isActive ? (sortDir === 'asc' ? '↑' : '↓') : '';
  const thClass = `${BASE_TH_CLASS} ${align === 'right' ? 'text-right' : 'text-left'}`;
  return (
    <th scope="col" aria-sort={ariaSort} className={thClass}>
      <button
        type="button"
        onClick={() => onToggle(field)}
        className="inline-flex items-center gap-1 uppercase tracking-wider focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded"
      >
        {label}
        <span aria-hidden="true" className="w-3 text-gray-400">
          {indicator}
        </span>
      </button>
    </th>
  );
}
