import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';

export type SortDirection = 'asc' | 'desc';

export interface UseTableSortResult {
  sortBy: string | undefined;
  sortDir: SortDirection | undefined;
  toggle: (field: string) => void;
}

/**
 * Click-to-sort state held in the URL via `?sort=<field>&dir=<asc|desc>`.
 * First click on a field: desc. Second click: asc. Third click: clear.
 */
export function useTableSort(): UseTableSortResult {
  const [searchParams, setSearchParams] = useSearchParams();
  const sortBy = searchParams.get('sort') || undefined;
  const rawDir = searchParams.get('dir');
  const sortDir: SortDirection | undefined =
    rawDir === 'asc' || rawDir === 'desc' ? rawDir : undefined;

  const toggle = useCallback(
    (field: string) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          const currentField = next.get('sort');
          const currentDir = next.get('dir');
          if (currentField !== field) {
            next.set('sort', field);
            next.set('dir', 'desc');
          } else if (currentDir === 'desc') {
            next.set('dir', 'asc');
          } else {
            next.delete('sort');
            next.delete('dir');
          }
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  return { sortBy, sortDir, toggle };
}
