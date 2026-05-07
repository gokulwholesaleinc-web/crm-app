import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * Tab state synced to a URL search param (default `?tab=...`).
 *
 * - Reads the initial tab from the URL on first render, falling back to
 *   `fallback` when the param is missing or not in `allowed`.
 * - Updating the tab calls `setSearchParams(..., { replace: true })` so
 *   tab clicks don't pollute history.
 * - Re-syncs to the URL when the param changes externally (browser
 *   back/forward, programmatic navigation), so the visible tab always
 *   matches the address bar.
 * - When the URL has no `tab` param at mount AND `getSavedDefault`
 *   returns a tab in `allowed`, that saved value seeds the initial
 *   state (one-shot at mount). Subsequent URL changes ignore the
 *   saved default, so address-bar drives the visible tab thereafter.
 *
 * `allowed` should be a stable reference (declare at module scope).
 */
export function useUrlTabState<T extends string>(
  allowed: ReadonlySet<T>,
  fallback: T,
  paramName: string = 'tab',
  getSavedDefault?: () => T | string | null | undefined,
): [T, (next: T) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get(paramName);
  const [activeTab, setActiveTab] = useState<T>(() => {
    if (requested && allowed.has(requested as T)) return requested as T;
    if (requested === null && getSavedDefault) {
      const saved = getSavedDefault();
      if (saved && allowed.has(saved as T)) return saved as T;
    }
    return fallback;
  });

  // On mount, if the URL is bare but we seeded a non-fallback tab from
  // the saved default, write it to the URL once so address-bar matches
  // visible tab and share-links/back-forward behave correctly.
  useEffect(() => {
    if (requested === null && activeTab !== fallback) {
      setSearchParams((prev) => {
        prev.set(paramName, activeTab);
        return prev;
      }, { replace: true });
    }
    // Mount-only seed reflection. Later URL changes are owned by the
    // [requested] effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // External URL change (back/forward, deep link, programmatic nav)
  // should drive the displayed tab — without this, the address bar and
  // the visible tab can diverge after a Back press. When the URL holds
  // an INVALID value, also normalize the URL itself so the docstring's
  // "address bar always matches visible tab" guarantee holds.
  //
  // When `requested === null` (bare URL after a Back press), leave the
  // visible tab alone — resetting to `fallback` here would clobber the
  // saved-default seed on first render and break the entire feature.
  useEffect(() => {
    if (requested === null) return;
    const isValid = allowed.has(requested as T);
    const next = isValid ? (requested as T) : fallback;
    if (next !== activeTab) setActiveTab(next);
    if (!isValid) {
      setSearchParams((prev) => {
        prev.set(paramName, fallback);
        return prev;
      }, { replace: true });
    }
    // `allowed` and `fallback` are expected to be stable references
    // per the docstring; depending on `requested` is sufficient.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requested]);

  const setTab = (next: T) => {
    setActiveTab(next);
    setSearchParams((prev) => {
      prev.set(paramName, next);
      return prev;
    }, { replace: true });
  };

  return [activeTab, setTab];
}
