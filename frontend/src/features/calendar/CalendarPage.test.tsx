import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import CalendarPage from './CalendarPage';

vi.mock('../../api/integrations', () => ({
  getCalendarStatus: vi.fn(),
  syncCalendar: vi.fn(),
}));

vi.mock('../activities/components/CalendarView', () => ({
  default: () => <div data-testid="calendar-view" />,
}));

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

import { getCalendarStatus } from '../../api/integrations';

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CalendarPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('CalendarPage', () => {
  it('renders the "Calendar" heading', async () => {
    vi.mocked(getCalendarStatus).mockResolvedValue({
      connected: false,
      calendar_id: null,
      last_synced_at: null,
      synced_events_count: 0,
    });

    renderPage();

    expect(screen.getByRole('heading', { name: 'Calendar' })).toBeInTheDocument();
  });

  it('shows "Connect Google Calendar" link and hides Sync button when not connected', async () => {
    vi.mocked(getCalendarStatus).mockResolvedValue({
      connected: false,
      calendar_id: null,
      last_synced_at: null,
      synced_events_count: 0,
    });

    renderPage();

    await screen.findByText(/Connect Google Calendar in Settings/);

    expect(screen.queryByRole('button', { name: /Sync from Google/i })).not.toBeInTheDocument();
    expect(screen.getByText(/Connect Google Calendar in Settings/)).toBeInTheDocument();
  });

  it('shows Sync button and hides connect link when connected', async () => {
    vi.mocked(getCalendarStatus).mockResolvedValue({
      connected: true,
      calendar_id: 'primary',
      last_synced_at: null,
      synced_events_count: 5,
    });

    renderPage();

    const btn = await screen.findByRole('button', { name: /Sync from Google/i });
    expect(btn).toBeInTheDocument();
    expect(screen.queryByText(/Connect Google Calendar in Settings/)).not.toBeInTheDocument();
  });
});
