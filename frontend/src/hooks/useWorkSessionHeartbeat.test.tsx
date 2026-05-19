import { act, render } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { server } from '../test-setup';
import {
  useWorkSessionHeartbeat,
  WORK_SESSION_HEARTBEAT_INTERVAL_MS,
  WORK_SESSION_IDLE_TIMEOUT_MS,
} from './useWorkSessionHeartbeat';

// MSW-based test (CRM CLAUDE.md: "MUST NOT MOCK ANYTHING"). Each test
// installs a per-case handler that captures the request body so we can
// assert on the wire payload instead of mocking the API module.

interface HeartbeatBody {
  entity_type: string;
  entity_id: number;
  source: string;
  metadata?: Record<string, unknown>;
}

function installHeartbeatHandler() {
  const calls: HeartbeatBody[] = [];
  server.use(
    http.post('*/api/work-sessions/heartbeat', async ({ request }) => {
      const body = (await request.json()) as HeartbeatBody;
      calls.push(body);
      return HttpResponse.json({
        id: 1,
        user_id: 1,
        entity_type: body.entity_type,
        entity_id: body.entity_id,
        started_at: '2026-05-18T12:00:00Z',
        last_seen_at: '2026-05-18T12:00:00Z',
        duration_seconds: 0,
        source: body.source,
      });
    }),
  );
  return calls;
}

function Probe() {
  useWorkSessionHeartbeat({
    entityType: 'contacts',
    entityId: 42,
    metadata: { route: '/contacts/42' },
  });
  return <div>probe</div>;
}

async function flushPromises() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe('useWorkSessionHeartbeat', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-05-18T12:00:00Z'));
  });

  afterEach(() => {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    });
    vi.useRealTimers();
  });

  it('sends an initial heartbeat and repeats on the interval', async () => {
    const calls = installHeartbeatHandler();
    render(<Probe />);
    await flushPromises();

    expect(calls).toHaveLength(1);
    expect(calls[0]).toEqual({
      entity_type: 'contacts',
      entity_id: 42,
      source: 'detail_page',
      metadata: { route: '/contacts/42' },
    });

    await act(async () => {
      vi.advanceTimersByTime(WORK_SESSION_HEARTBEAT_INTERVAL_MS);
    });
    await flushPromises();

    expect(calls).toHaveLength(2);
  });

  it('stops sending after the idle timeout', async () => {
    const calls = installHeartbeatHandler();
    render(<Probe />);
    await flushPromises();

    await act(async () => {
      vi.advanceTimersByTime(WORK_SESSION_IDLE_TIMEOUT_MS);
    });
    await flushPromises();
    const callsAtIdleBoundary = calls.length;

    await act(async () => {
      vi.advanceTimersByTime(WORK_SESSION_HEARTBEAT_INTERVAL_MS * 3);
    });
    await flushPromises();

    expect(calls).toHaveLength(callsAtIdleBoundary);
  });

  it('does not heartbeat while the document is hidden', async () => {
    const calls = installHeartbeatHandler();
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'hidden',
    });

    render(<Probe />);
    await flushPromises();

    await act(async () => {
      vi.advanceTimersByTime(WORK_SESSION_HEARTBEAT_INTERVAL_MS);
    });
    await flushPromises();

    expect(calls).toHaveLength(0);

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    });
  });

  it('stops scheduling after a 403 instead of flooding the network', async () => {
    const calls: HeartbeatBody[] = [];
    server.use(
      http.post('*/api/work-sessions/heartbeat', async ({ request }) => {
        const body = (await request.json()) as HeartbeatBody;
        calls.push(body);
        return HttpResponse.json({ detail: 'forbidden' }, { status: 403 });
      }),
    );

    // Heartbeat hook logs the 403 via console.warn — silence for this
    // test so vitest doesn't surface the expected warning as noise.
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});

    render(<Probe />);
    await flushPromises();
    expect(calls).toHaveLength(1);

    await act(async () => {
      vi.advanceTimersByTime(WORK_SESSION_HEARTBEAT_INTERVAL_MS * 5);
    });
    await flushPromises();

    // After the first 403 the hook latches `stoppedRef` so subsequent
    // intervals are no-ops. Without this guard the heartbeat would
    // hammer the endpoint every 45s for a rep who lost access to the
    // entity — flooding Sentry and silently leaving Time-by-Rep at 0.
    expect(calls).toHaveLength(1);
    warnSpy.mockRestore();
  });
});
