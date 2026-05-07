import { useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';

interface HistoryState {
  idx?: number;
}

interface NavLocationState {
  from?: string;
}

/**
 * Returns a click handler for "back" buttons that respects how the user got
 * to the current page rather than always sending them to a hard-coded list.
 *
 * Resolution order:
 *   1. `location.state.from` — set explicitly by callers that know the origin
 *   2. in-app history (react-router stores idx>0 on PUSH navigations) — go back one
 *   3. `fallbackPath` — typed-URL / fresh-tab / cross-origin entry
 */
export function useSmartBack(fallbackPath: string) {
  const navigate = useNavigate();
  const location = useLocation();

  return useCallback(() => {
    const fromState = (location.state as NavLocationState | null)?.from;
    if (fromState) {
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
