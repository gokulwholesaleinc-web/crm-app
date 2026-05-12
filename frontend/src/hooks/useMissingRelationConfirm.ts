import { useRef, useState } from 'react';

/**
 * Stages a payload that's missing both contact_id and company_id and lets a
 * MissingRelationDialog confirm or cancel it. Centralising the gate means each
 * form only owns its missing-relation check, not the dialog wiring.
 */
export function useMissingRelationConfirm<T>(submit: (data: T) => void) {
  const [pending, setPending] = useState<T | null>(null);
  // Idempotency guard: two synchronous clicks on "Save anyway" both see
  // `pending !== null` before React flushes setPending(null), so without
  // this ref the same payload would be submitted twice.
  const submittingRef = useRef(false);
  return {
    isOpen: pending !== null,
    request: (data: T) => {
      submittingRef.current = false;
      setPending(data);
    },
    onCancel: () => {
      submittingRef.current = false;
      setPending(null);
    },
    onConfirm: () => {
      if (submittingRef.current) return;
      const payload = pending;
      if (!payload) return;
      submittingRef.current = true;
      setPending(null);
      submit(payload);
    },
  };
}
