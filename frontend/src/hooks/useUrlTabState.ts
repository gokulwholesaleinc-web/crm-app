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
 *
 * `allowed` should be a stable reference (declare at module scope).
 */
export function useUrlTabState<T extends string>(
  allowed: ReadonlySet<T>,
  fallback: T,
  paramName: string = 'tab',
): [T, (next: T) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get(paramName);
  const [activeTab, setActiveTab] = useState<T>(() =>
    requested && allowed.has(requested as T) ? (requested as T) : fallback,
  );

  // External URL change (back/forward, deep link, programmatic nav)
  // should drive the displayed tab — without this, the address bar and
  // the visible tab can diverge after a Back press.
  useEffect(() => {
    const next = requested && allowed.has(requested as T) ? (requested as T) : fallback;
    if (next !== activeTab) setActiveTab(next);
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
