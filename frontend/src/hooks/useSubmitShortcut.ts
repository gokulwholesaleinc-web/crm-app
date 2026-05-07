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
 * Convenience wrapper for the common form pattern: attach a ref to a `<form>`
 * and have Cmd/Ctrl+Enter call `requestSubmit()` on it. Returns the ref.
 */
export function useFormSubmitShortcut(): RefObject<HTMLFormElement> {
  const formRef = useRef<HTMLFormElement>(null);
  const submit = useCallback(() => {
    formRef.current?.requestSubmit();
  }, []);
  useSubmitShortcut(formRef, submit);
  return formRef;
}
