import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';
import { useGoogleCalendarSync } from './useGoogleCalendarSync';

vi.mock('../api/integrations', () => ({
  getCalendarStatus: vi.fn(),
  syncCalendar: vi.fn(),
}));

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

import { getCalendarStatus, syncCalendar } from '../api/integrations';
import toast from 'react-hot-toast';

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useGoogleCalendarSync', () => {
  it('wires status query to the correct query key', async () => {
    vi.mocked(getCalendarStatus).mockResolvedValue({
      connected: true,
      calendar_id: 'primary',
      last_synced_at: null,
      synced_events_count: 3,
    });

    const { result } = renderHook(() => useGoogleCalendarSync(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isLoadingStatus).toBe(false));

    expect(getCalendarStatus).toHaveBeenCalledTimes(1);
    expect(result.current.status?.synced_events_count).toBe(3);
  });

  it('derives connected correctly from status', async () => {
    vi.mocked(getCalendarStatus).mockResolvedValue({
      connected: false,
      calendar_id: null,
      last_synced_at: null,
      synced_events_count: 0,
    });

    const { result } = renderHook(() => useGoogleCalendarSync(), {
      wrapper: makeWrapper(),
    });

    await waitFor(() => expect(result.current.isLoadingStatus).toBe(false));

    expect(result.current.connected).toBe(false);
  });

  it('invalidates both query keys on sync success', async () => {
    vi.mocked(getCalendarStatus).mockResolvedValue({
      connected: true,
      calendar_id: 'primary',
      last_synced_at: null,
      synced_events_count: 0,
    });
    vi.mocked(syncCalendar).mockResolvedValue({ synced: 5, events: [] });

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(client, 'invalidateQueries');

    const wrapper = ({ children }: { children: React.ReactNode }) =>
      createElement(QueryClientProvider, { client }, children);

    const { result } = renderHook(() => useGoogleCalendarSync(), { wrapper });

    await waitFor(() => expect(result.current.isLoadingStatus).toBe(false));

    result.current.sync();

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: ['integrations', 'google-calendar'] })
      )
    );

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ['calendar'] })
    );
    expect(toast.success).toHaveBeenCalledWith('Synced 5 events from Google Calendar');
  });
});
