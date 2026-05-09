import { useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

interface HistoryState {
  idx?: number;
}

interface NavLocationState {
  // Other places in the codebase (PrivateRoute, OAuth callback) put a Location
  // object on `state.from` for post-login redirects. We only honor string
  // paths; anything else falls through to the in-app-history check.
  from?: unknown;
}

function isSafeInternalPath(value: unknown): value is string {
  return (
    typeof value === 'string' &&
    value.startsWith('/') &&
    !value.startsWith('//')
  );
}

/**
 * Returns a click handler for "back" buttons that respects how the user got
 * to the current page rather than always sending them to a hard-coded list.
 *
 * Resolution order:
 *   1. `location.state.from` — must be a same-origin path string
 *   2. in-app history (react-router stores idx>0 on PUSH navigations) — go back one
 *   3. `fallbackPath` — typed-URL / fresh-tab / cross-origin entry
 */
export function useSmartBack(fallbackPath: string) {
  const navigate = useNavigate();
  const location = useLocation();

  return useCallback(() => {
    const fromState = (location.state as NavLocationState | null)?.from;
    if (isSafeInternalPath(fromState)) {
      navigate(fromState);
      return;
    }
    const idx = (window.history.state as HistoryState | null)?.idx ?? 0;
    if (idx > 0) {
      navigate(-1);
      return;
    }
    navigate(fallbackPath);
  }, [navigate, location.state, fallbackPath]);
}
