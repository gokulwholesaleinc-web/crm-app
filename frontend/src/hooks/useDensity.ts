import { useEffect } from 'react';
import { useUserPreferences } from './useUserPreferences';

const COMPACT_CLASS = 'density-compact';

/**
 * Reflects the user's density preference as a body-level class so a single
 * scoped CSS rule can tighten list-page tables without each page wiring it up.
 * Mount once near the app root.
 */
export function useDensity(): void {
  const { prefs } = useUserPreferences();
  const isCompact = prefs.density === 'compact';

  useEffect(() => {
    if (typeof document === 'undefined') return;
    const { body } = document;
    if (isCompact) {
      body.classList.add(COMPACT_CLASS);
    } else {
      body.classList.remove(COMPACT_CLASS);
    }
    return () => {
      body.classList.remove(COMPACT_CLASS);
    };
  }, [isCompact]);
}
