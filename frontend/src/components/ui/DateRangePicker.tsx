import { useState } from 'react';
import clsx from 'clsx';

export type DateRangePreset = 'today' | 'this_week' | 'this_month' | 'this_quarter' | 'this_year' | 'all_time';

export interface DateRange {
  dateFrom: string | null;
  dateTo: string | null;
}

interface DateRangePickerProps {
  value?: DateRangePreset;
  onChange: (range: DateRange, preset: DateRangePreset) => void;
}

const PRESETS: { key: DateRangePreset; label: string }[] = [
  { key: 'today', label: 'Today' },
  { key: 'this_week', label: 'This Week' },
  { key: 'this_month', label: 'This Month' },
  { key: 'this_quarter', label: 'This Quarter' },
  { key: 'this_year', label: 'This Year' },
  { key: 'all_time', label: 'All Time' },
];

function formatDate(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getDateRange(preset: DateRangePreset): DateRange {
  const today = new Date();

  switch (preset) {
    case 'today':
      return { dateFrom: formatDate(today), dateTo: formatDate(today) };

    case 'this_week': {
      const day = today.getDay();
      const monday = new Date(today);
      monday.setDate(today.getDate() - ((day + 6) % 7));
      return { dateFrom: formatDate(monday), dateTo: formatDate(today) };
    }

    case 'this_month': {
      const monthStart = new Date(today.getFullYear(), today.getMonth(), 1);
      return { dateFrom: formatDate(monthStart), dateTo: formatDate(today) };
    }

    case 'this_quarter': {
      const quarterMonth = Math.floor(today.getMonth() / 3) * 3;
      const quarterStart = new Date(today.getFullYear(), quarterMonth, 1);
      return { dateFrom: formatDate(quarterStart), dateTo: formatDate(today) };
    }

    case 'this_year': {
      const yearStart = new Date(today.getFullYear(), 0, 1);
      return { dateFrom: formatDate(yearStart), dateTo: formatDate(today) };
    }

    case 'all_time':
    default:
      return { dateFrom: null, dateTo: null };
  }
}

export function DateRangePicker({ value = 'all_time', onChange }: DateRangePickerProps) {
  const [active, setActive] = useState<DateRangePreset>(value);

  const handleClick = (preset: DateRangePreset) => {
    setActive(preset);
    onChange(getDateRange(preset), preset);
  };

  return (
    <div className="flex flex-wrap gap-1" role="group" aria-label="Date range filter">
      {PRESETS.map(({ key, label }) => (
        <button
          key={key}
          type="button"
          onClick={() => handleClick(key)}
          className={clsx(
            'px-3 py-1.5 text-xs sm:text-sm font-medium rounded-md transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-1',
            active === key
              ? 'bg-primary-500 text-white shadow-sm'
              : 'bg-white text-gray-600 border border-gray-300 hover:bg-gray-50 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-600 dark:hover:bg-gray-700'
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
