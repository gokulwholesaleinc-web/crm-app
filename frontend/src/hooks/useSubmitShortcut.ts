import { useCallback, useEffect, useRef, type RefObject } from 'react';

/**
 * Cmd/Ctrl+Enter triggers `onSubmit` when focus is inside `targetRef`.
 * Scoped to the element so multiple forms on a page don't fight.
 */
export function useSubmitShortcut(
  targetRef: RefObject<HTMLElement | null>,
  onSubmit: () => void,
): void {
  useEffect(() => {
    const target = targetRef.current;
    if (!target) return;
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
        event.preventDefault();
        onSubmit();
      }
    };
    target.addEventListener('keydown', handler);
    return () => target.removeEventListener('keydown', handler);
  }, [targetRef, onSubmit]);
}

/**
 * Convenience wrapper for the common form pattern: returns a callback ref
 * to attach to a `<form>`. Cmd/Ctrl+Enter inside the form calls
 * `requestSubmit()` on it.
 *
 * Returns a callback ref (not a RefObject) so the listener re-attaches
 * every time the form node remounts — important for modals that keep
 * the parent component mounted but unmount the form-bearing JSX when
 * the modal is closed (e.g. EmailComposeModal).
 */
export function useFormSubmitShortcut(): (node: HTMLFormElement | null) => void {
  const cleanupRef = useRef<(() => void) | null>(null);

  return useCallback((node: HTMLFormElement | null) => {
    cleanupRef.current?.();
    cleanupRef.current = null;
    if (!node) return;
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
        event.preventDefault();
        node.requestSubmit();
      }
    };
    node.addEventListener('keydown', handler);
    cleanupRef.current = () => node.removeEventListener('keydown', handler);
  }, []);
}
