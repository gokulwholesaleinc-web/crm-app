import { useState, useEffect } from 'react';

/**
 * Returns a debounced version of the provided value.
 * The debounced value only updates after the specified delay
 * has passed without the value changing.
 */
export function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);

  return debounced;
}
