import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  useWorkSessionHeartbeat,
  WORK_SESSION_HEARTBEAT_INTERVAL_MS,
  WORK_SESSION_IDLE_TIMEOUT_MS,
} from './useWorkSessionHeartbeat';

vi.mock('../api/audit', () => ({
  auditApi: {
    sendWorkSessionHeartbeat: vi.fn(),
  },
}));

import { auditApi } from '../api/audit';

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
    vi.mocked(auditApi.sendWorkSessionHeartbeat).mockResolvedValue({
      id: 1,
      user_id: 1,
      entity_type: 'contacts',
      entity_id: 42,
      started_at: '2026-05-18T12:00:00Z',
      last_seen_at: '2026-05-18T12:00:00Z',
      duration_seconds: 0,
      source: 'detail_page',
    });
  });

  afterEach(() => {
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    });
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('sends an initial heartbeat and repeats on the interval', async () => {
    render(<Probe />);
    await flushPromises();

    expect(auditApi.sendWorkSessionHeartbeat).toHaveBeenCalledTimes(1);
    expect(auditApi.sendWorkSessionHeartbeat).toHaveBeenLastCalledWith({
      entity_type: 'contacts',
      entity_id: 42,
      source: 'detail_page',
      metadata: { route: '/contacts/42' },
    });

    await act(async () => {
      vi.advanceTimersByTime(WORK_SESSION_HEARTBEAT_INTERVAL_MS);
    });
    await flushPromises();

    expect(auditApi.sendWorkSessionHeartbeat).toHaveBeenCalledTimes(2);
  });

  it('stops sending after the idle timeout', async () => {
    render(<Probe />);
    await flushPromises();

    await act(async () => {
      vi.advanceTimersByTime(WORK_SESSION_IDLE_TIMEOUT_MS);
    });
    await flushPromises();
    const callsAtIdleBoundary = vi.mocked(auditApi.sendWorkSessionHeartbeat).mock.calls.length;

    await act(async () => {
      vi.advanceTimersByTime(WORK_SESSION_HEARTBEAT_INTERVAL_MS * 3);
    });
    await flushPromises();

    expect(auditApi.sendWorkSessionHeartbeat).toHaveBeenCalledTimes(callsAtIdleBoundary);
  });

  it('does not heartbeat while the document is hidden', async () => {
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

    expect(auditApi.sendWorkSessionHeartbeat).not.toHaveBeenCalled();

    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    });
  });
});
