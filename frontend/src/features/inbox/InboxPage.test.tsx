import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../../api/email', async () => {
  const actual = await vi.importActual<typeof import('../../api/email')>('../../api/email');
  return {
    ...actual,
    emailApi: {
      list: vi.fn(),
      search: vi.fn(),
    },
    getVolumeStats: vi.fn(),
  };
});

import { emailApi, getVolumeStats } from '../../api/email';
import InboxPage from './InboxPage';

const RECENT_FIXTURES = [
  {
    id: 1,
    to_email: 'lead@acme.com',
    subject: 'Quote follow-up',
    body: '<p>Hi there,</p><p>Following up on the quote we sent last week.</p>',
    status: 'sent',
    attempts: 1,
    error: null,
    created_at: '2026-05-08T10:00:00Z',
    sent_at: '2026-05-08T10:00:05Z',
    opened_at: null,
    clicked_at: null,
    open_count: 0,
    click_count: 0,
    entity_type: 'contacts',
    entity_id: 42,
    template_id: null,
    campaign_id: null,
    sent_by_id: 1,
  },
  {
    id: 2,
    to_email: 'orphan@nowhere.com',
    subject: 'Untethered email',
    body: 'plain body',
    status: 'sent',
    attempts: 1,
    error: null,
    created_at: '2026-05-08T11:00:00Z',
    sent_at: '2026-05-08T11:00:05Z',
    opened_at: null,
    clicked_at: null,
    open_count: 0,
    click_count: 0,
    entity_type: null,
    entity_id: null,
    template_id: null,
    campaign_id: null,
    sent_by_id: 1,
  },
];

const SEARCH_FIXTURES = [
  {
    id: 99,
    kind: 'received' as const,
    subject: 'RE: Quote follow-up',
    snippet: 'Sounds good, let us schedule a call.',
    from_email: 'lead@acme.com',
    to_email: 'rep@linkcreative.com',
    sent_at: '2026-05-08T12:00:00Z',
    thread_id: 'gmail-thread-x',
    entity_type: 'contacts',
    entity_id: 42,
  },
];

function renderPage(initialEntry: string = '/inbox') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <InboxPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(emailApi.list).mockResolvedValue({
    items: RECENT_FIXTURES,
    total: RECENT_FIXTURES.length,
    page: 1,
    page_size: 25,
    pages: 1,
  });
  vi.mocked(emailApi.search).mockResolvedValue({
    items: SEARCH_FIXTURES,
    total: SEARCH_FIXTURES.length,
    page: 1,
    page_size: 25,
    pages: 1,
  });
  vi.mocked(getVolumeStats).mockResolvedValue({
    sent_today: 12,
    daily_limit: 100,
    warmup_enabled: false,
    warmup_day: 0,
    warmup_current_limit: 0,
    remaining_today: 88,
  });
});

describe('InboxPage', () => {
  it('renders recent emails by default and strips HTML for the snippet', async () => {
    renderPage();

    await screen.findByText('Quote follow-up');
    expect(
      screen.getByText(/Following up on the quote we sent last week/),
    ).toBeInTheDocument();
    await screen.findByText('12 / 100');
  });

  it('marks orphan rows (no entity) as not navigable', async () => {
    renderPage();
    await screen.findByText('Untethered email');
    expect(screen.getByText('Not linked to a contact yet')).toBeInTheDocument();
  });

  it('switches to search results when a query is typed', async () => {
    renderPage();
    await screen.findByText('Quote follow-up');

    const searchBox = screen.getByPlaceholderText(
      /Search emails by subject, body, sender, or recipient/i,
    );
    fireEvent.change(searchBox, { target: { value: 'follow-up' } });

    await waitFor(() => {
      expect(vi.mocked(emailApi.search)).toHaveBeenCalledWith(
        expect.objectContaining({ q: 'follow-up' }),
      );
    });

    await screen.findByText('RE: Quote follow-up');
    expect(screen.getByText('Sounds good, let us schedule a call.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Failed' })).not.toBeInTheDocument();
  });

  it('renders empty-state copy when search returns no rows', async () => {
    vi.mocked(emailApi.search).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      page_size: 25,
      pages: 0,
    });

    renderPage();
    await screen.findByText('Quote follow-up');

    const searchBox = screen.getByPlaceholderText(
      /Search emails by subject, body, sender, or recipient/i,
    );
    fireEvent.change(searchBox, { target: { value: 'nothing-matches' } });

    await screen.findByText(/No emails found for "nothing-matches"/);
  });

  it('seeds query + status from URL search params', async () => {
    renderPage('/inbox?q=quote&status=sent');

    await waitFor(() => {
      expect(vi.mocked(emailApi.search)).toHaveBeenCalledWith(
        expect.objectContaining({ q: 'quote', page: 1 }),
      );
    });

    const searchBox = screen.getByPlaceholderText(
      /Search emails by subject, body, sender, or recipient/i,
    ) as HTMLInputElement;
    expect(searchBox.value).toBe('quote');
  });

  it('shows Clear-filter affordance when a non-default status returns empty', async () => {
    vi.mocked(emailApi.list).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      page_size: 25,
      pages: 0,
    });

    renderPage('/inbox?status=failed');

    await screen.findByText(/No emails matching Failed/);
    expect(screen.getByRole('button', { name: /Clear filter/i })).toBeInTheDocument();
  });

  it('renders an inline error with the backend detail and a retry control', async () => {
    vi.mocked(emailApi.list).mockRejectedValueOnce({
      detail: 'Gmail token expired — reconnect in Settings.',
      status_code: 401,
    });

    renderPage();

    await screen.findByText(/Gmail token expired/);
    expect(screen.getByRole('button', { name: /Try again/i })).toBeInTheDocument();
  });

  it('flattens FastAPI 422 validation arrays into the error description', async () => {
    vi.mocked(emailApi.search).mockRejectedValueOnce({
      detail: [
        { loc: ['query', 'q'], msg: 'ensure this value has at most 200 characters', type: 'value_error.any_str.max_length' },
      ],
      status_code: 422,
    });

    renderPage('/inbox?q=overflow');

    await screen.findByText(/ensure this value has at most 200 characters/);
  });
});
