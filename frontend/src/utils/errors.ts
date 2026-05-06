/**
 * Helpers for surfacing actionable backend error messages on the UI.
 *
 * The axios response interceptor in `api/client.ts` flattens every error
 * into `{ detail, status_code }` (the `ApiError` shape) and rejects with
 * that — so the rejection at the call site is NOT an axios error and
 * `err.response` is always undefined. Use these helpers instead of
 * `(err as AxiosError).response?.data?.detail`.
 */

import type { ApiError } from '../types/common';

/**
 * Pull a user-actionable string off whatever the mutation/promise rejected
 * with. Handles:
 *   - the flattened `ApiError` shape produced by `api/client.ts`
 *   - FastAPI 422 detail-as-list (first field message wins)
 *   - bare Error objects (returns `.message`)
 *
 * Returns `null` when nothing useful is available so callers can fall
 * back to their own default message.
 */
export function extractApiErrorDetail(err: unknown): string | null {
  if (!err || typeof err !== 'object') return null;
  const e = err as Partial<ApiError> & { detail?: unknown; message?: unknown };
  const detail = e.detail;

  if (typeof detail === 'string') {
    const trimmed = detail.trim();
    if (trimmed) return trimmed;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string; loc?: unknown[] } | undefined;
    if (first) {
      const last = first.loc?.[first.loc.length - 1];
      const where = typeof last === 'string' ? last : undefined;
      const msg = first.msg || 'invalid value';
      return where ? `${where}: ${msg}` : msg;
    }
  }

  if (typeof e.message === 'string' && e.message.trim()) {
    return e.message.trim();
  }

  return null;
}
