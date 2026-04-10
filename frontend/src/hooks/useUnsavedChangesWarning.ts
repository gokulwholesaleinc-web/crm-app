import { useEffect } from 'react';

/**
 * Wire the browser's `beforeunload` prompt whenever a form has unsaved
 * edits. When `isDirty` is true and the user tries to close the tab,
 * refresh, or navigate to a different origin, the browser shows its
 * native "Leave site? Changes you made may not be saved." prompt.
 *
 * This does NOT catch in-app react-router navigations — those are a
 * separate concern requiring `useBlocker` from a v6.4+ data router.
 * The current app uses the declarative `<Routes>` API, so tab-close
 * protection is as much as we can layer on without a router rewrite.
 * The overwhelmingly common data-loss case (accidental refresh or tab
 * close) is what this guards against.
 *
 * Callers are responsible for deriving `isDirty`:
 * - react-hook-form: pass `formState.isDirty`
 * - uncontrolled `useState` forms: compare to initial values once and
 *   cache the flag, or flip a `touched` sentinel on first edit
 *
 * @param isDirty truthy when the form has edits that would be lost
 */
export function useUnsavedChangesWarning(isDirty: boolean): void {
  useEffect(() => {
    if (!isDirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      // Modern browsers ignore the message string and show their own,
      // but setting returnValue is the documented opt-in for Chrome,
      // Safari, and Firefox. preventDefault alone is not sufficient
      // on Chromium.
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty]);
}
