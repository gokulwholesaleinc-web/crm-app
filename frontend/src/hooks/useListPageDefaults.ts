import { useCallback, useEffect, useRef } from 'react';
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
 * The hook is intentionally minimal — it only exposes saved getters and
 * record callbacks. URL-driven state (sort/page-size) stays owned by the
 * page; this hook just persists the values the page already knows about.
 *
 * Pair with `useListSortPersistence(page)` for the standard sort-seed +
 * auto-save flow.
 */
export function useListPageDefaults(page: ListPageKey): UseListPageDefaultsResult {
  const { prefs, setPref } = useUserPreferences();
  const saved = prefs.listDefaults?.[page];

  const recordSlice = useCallback(
    (slice: Partial<ListPageDefaults>) => {
      const all = prefs.listDefaults ?? {};
      const cur = all[page] ?? {};
      setPref('listDefaults', { ...all, [page]: { ...cur, ...slice } });
    },
    [page, prefs.listDefaults, setPref],
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
 * visit also opens unsorted.
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
    // Intentionally narrow deps — recordSort/savedSort* identities depend
    // on prefs and would re-run this effect after our own write, which
    // is harmless (idempotent) but pointless.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sortBy, sortDir]);

  return { sortBy, sortDir, toggle };
}
