import { useEffect, useMemo, useRef } from 'react';
import { auditApi } from '../api/audit';

export const WORK_SESSION_HEARTBEAT_INTERVAL_MS = 45_000;
export const WORK_SESSION_IDLE_TIMEOUT_MS = 5 * 60_000;

interface UseWorkSessionHeartbeatOptions {
  entityType: string;
  entityId: number | undefined;
  enabled?: boolean;
  source?: string;
  metadata?: Record<string, unknown>;
  intervalMs?: number;
  idleTimeoutMs?: number;
}

/** Serialize metadata defensively. Non-serializable values (Date,
 *  function, circular ref, BigInt) would otherwise throw inside
 *  useMemo and crash the entire detail-page render. */
function safeSerializeMetadata(metadata: Record<string, unknown> | undefined): string {
  if (!metadata) return '{}';
  try {
    return JSON.stringify(metadata);
  } catch (err) {
    if (typeof console !== 'undefined') {
      console.warn('[work-session] metadata not serializable, dropping', err);
    }
    return '{}';
  }
}

/**
 * Coarse active-time heartbeat for CRM detail pages.
 *
 * This intentionally tracks only entity context and duration. It never records
 * keystrokes, screenshots, field focus, or page content.
 */
export function useWorkSessionHeartbeat({
  entityType,
  entityId,
  enabled = true,
  source = 'detail_page',
  metadata,
  intervalMs = WORK_SESSION_HEARTBEAT_INTERVAL_MS,
  idleTimeoutMs = WORK_SESSION_IDLE_TIMEOUT_MS,
}: UseWorkSessionHeartbeatOptions) {
  const lastActiveAtRef = useRef(Date.now());
  const inFlightRef = useRef(false);
  // Latches once the backend rejects this user for this entity (403/404)
  // so we stop scheduling instead of flooding the console every 45s with
  // permission errors the user can't act on.
  const stoppedRef = useRef(false);
  const metadataKey = useMemo(() => safeSerializeMetadata(metadata), [metadata]);

  useEffect(() => {
    if (!enabled || !entityId || typeof window === 'undefined') return;
    stoppedRef.current = false;

    const markActive = () => {
      lastActiveAtRef.current = Date.now();
    };

    const shouldHeartbeat = () => {
      if (stoppedRef.current) return false;
      const isVisible =
        typeof document === 'undefined' || document.visibilityState === 'visible';
      const isRecentlyActive = Date.now() - lastActiveAtRef.current <= idleTimeoutMs;
      return isVisible && isRecentlyActive && !inFlightRef.current;
    };

    const heartbeat = () => {
      if (!shouldHeartbeat()) return;
      inFlightRef.current = true;
      let payloadMetadata: Record<string, unknown> | undefined;
      try {
        payloadMetadata = metadataKey ? JSON.parse(metadataKey) : undefined;
      } catch {
        payloadMetadata = undefined;
      }
      auditApi
        .sendWorkSessionHeartbeat({
          entity_type: entityType,
          entity_id: entityId,
          source,
          metadata: payloadMetadata,
        })
        .catch((err) => {
          const status = (err as { status_code?: number } | undefined)?.status_code;
          if (status === 403 || status === 404) {
            // User lost (or never had) access to this entity. Don't
            // keep retrying — the response will never change without a
            // share/role mutation, and a polling 403 floods Sentry +
            // silently leaves "Time by Rep" at zero with no signal.
            stoppedRef.current = true;
            console.warn(
              `[work-session] no access to ${entityType}/${entityId}; stopping heartbeat`,
              err,
            );
            return;
          }
          console.warn('[work-session] heartbeat failed', err);
        })
        .finally(() => {
          inFlightRef.current = false;
        });
    };

    const activityEvents = ['pointerdown', 'mousemove', 'keydown', 'scroll', 'touchstart'];
    activityEvents.forEach((eventName) => {
      window.addEventListener(eventName, markActive, { passive: true });
    });
    document.addEventListener('visibilitychange', heartbeat);

    heartbeat();
    const intervalId = window.setInterval(heartbeat, intervalMs);

    return () => {
      window.clearInterval(intervalId);
      document.removeEventListener('visibilitychange', heartbeat);
      activityEvents.forEach((eventName) => {
        window.removeEventListener(eventName, markActive);
      });
    };
  }, [enabled, entityType, entityId, source, metadataKey, intervalMs, idleTimeoutMs]);
}
