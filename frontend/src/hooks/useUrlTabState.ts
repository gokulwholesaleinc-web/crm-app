import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';

/**
 * Tab state synced to a URL search param (default `?tab=...`).
 *
 * - Reads the initial tab from the URL on first render, falling back to
 *   `fallback` when the param is missing or not in `allowed`.
 * - Updating the tab calls `setSearchParams(..., { replace: true })` so
 *   tab clicks don't pollute history.
 *
 * `allowed` should be a stable reference (declare at module scope).
 */
export function useUrlTabState<T extends string>(
  allowed: ReadonlySet<T>,
  fallback: T,
  paramName: string = 'tab',
): [T, (next: T) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState<T>(() => {
    const requested = searchParams.get(paramName);
    return requested && allowed.has(requested as T) ? (requested as T) : fallback;
  });

  const setTab = (next: T) => {
    setActiveTab(next);
    setSearchParams((prev) => {
      prev.set(paramName, next);
      return prev;
    }, { replace: true });
  };

  return [activeTab, setTab];
}
