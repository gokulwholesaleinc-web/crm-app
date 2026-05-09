import { useCallback, useEffect, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTableSort } from './useTableSort';
import {
  useUserPreferences,
  type ListPageKey,
  type ListPageDefaults,
  type SortDirection,
} from './useUserPreferences';

export interface UseListPageDefaultsResult {
  savedPageSize: number | undefined;
  savedSortBy: string | undefined;
  savedSortDir: SortDirection | undefined;
  recordPageSize: (n: number) => void;
  recordSort: (
    sortBy: string | undefined,
    sortDir: SortDirection | undefined,
  ) => void;
}

/**
 * Reads/writes the per-list-page slice of `prefs.listDefaults` for `page`.
 *
 * Writes route through `setPref` with the updater-function form so the
 * merge happens against the latest on-disk blob, never against this
 * hook's potentially-stale React-state snapshot. That keeps a sibling
 * page's slice from being clobbered when two pages save in the same
 * commit, and keeps cross-tab writes safe.
 */
export function useListPageDefaults(page: ListPageKey): UseListPageDefaultsResult {
  const { prefs, setPref } = useUserPreferences();
  const saved = prefs.listDefaults?.[page];

  const recordSlice = useCallback(
    (slice: Partial<ListPageDefaults>) => {
      setPref('listDefaults', (prev) => {
        const all = prev ?? {};
        const cur = all[page] ?? {};
        return { ...all, [page]: { ...cur, ...slice } };
      });
    },
    [page, setPref],
  );

  const recordPageSize = useCallback(
    (n: number) => recordSlice({ pageSize: n }),
    [recordSlice],
  );

  const recordSort = useCallback(
    (sortBy: string | undefined, sortDir: SortDirection | undefined) =>
      recordSlice({ sortBy, sortDir }),
    [recordSlice],
  );

  return {
    savedPageSize: saved?.pageSize,
    savedSortBy: saved?.sortBy,
    savedSortDir: saved?.sortDir,
    recordPageSize,
    recordSort,
  };
}

export interface UseListSortPersistenceResult {
  sortBy: string | undefined;
  sortDir: SortDirection | undefined;
  toggle: (field: string) => void;
}

/**
 * Drop-in replacement for `useTableSort()` that:
 *   - On first render, if URL has no `?sort=&dir=`, seeds them from the
 *     user's saved default (so back/forward + share-link still work).
 *   - On subsequent URL sort changes, persists them back to prefs.
 *
 * URL always wins over saved defaults — saved is only consulted on the
 * very first render and only when the URL is bare. Toggling sort off
 * (third click clears the URL params) persists `undefined` so the next
 * visit also opens unsorted, matching what the user just chose.
 */
export function useListSortPersistence(
  page: ListPageKey,
): UseListSortPersistenceResult {
  const { savedSortBy, savedSortDir, recordSort } = useListPageDefaults(page);
  const [, setSearchParams] = useSearchParams();
  const { sortBy, sortDir, toggle } = useTableSort();

  const hasSeeded = useRef(false);

  useEffect(() => {
    if (hasSeeded.current) return;
    hasSeeded.current = true;
    if (!sortBy && !sortDir && savedSortBy && savedSortDir) {
      setSearchParams(
        (prev) => {
          prev.set('sort', savedSortBy);
          prev.set('dir', savedSortDir);
          return prev;
        },
        { replace: true },
      );
    }
    // Seed runs once on mount; later re-syncs are owned by useTableSort.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!hasSeeded.current) return;
    if (sortBy !== savedSortBy || sortDir !== savedSortDir) {
      recordSort(sortBy, sortDir);
    }
    // Intentionally narrow deps. recordSort is stable now (updater form
    // in useUserPreferences), but tracking savedSort* would re-fire the
    // effect after our own write — harmless because of the equality
    // check, but pointless.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sortBy, sortDir]);

  return { sortBy, sortDir, toggle };
}

/**
 * Bundled state + persistence for a list page's `pageSize`. Returns a
 * tuple matching `useState`'s shape. Setting the size both updates local
 * state and records the preference.
 */
export function useListPageSizeState(
  page: ListPageKey,
  fallback = 25,
): [number, (n: number) => void] {
  const { savedPageSize, recordPageSize } = useListPageDefaults(page);
  const [pageSize, setPageSize] = useState(savedPageSize ?? fallback);
  const set = useCallback(
    (n: number) => {
      setPageSize(n);
      recordPageSize(n);
    },
    [recordPageSize],
  );
  return [pageSize, set];
}
