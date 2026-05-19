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
  const metadataKey = useMemo(() => JSON.stringify(metadata ?? {}), [metadata]);

  useEffect(() => {
    if (!enabled || !entityId || typeof window === 'undefined') return;

    const markActive = () => {
      lastActiveAtRef.current = Date.now();
    };

    const shouldHeartbeat = () => {
      const isVisible =
        typeof document === 'undefined' || document.visibilityState === 'visible';
      const isRecentlyActive = Date.now() - lastActiveAtRef.current <= idleTimeoutMs;
      return isVisible && isRecentlyActive && !inFlightRef.current;
    };

    const heartbeat = () => {
      if (!shouldHeartbeat()) return;
      inFlightRef.current = true;
      auditApi
        .sendWorkSessionHeartbeat({
          entity_type: entityType,
          entity_id: entityId,
          source,
          metadata: metadataKey ? JSON.parse(metadataKey) : undefined,
        })
        .catch((err) => {
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
