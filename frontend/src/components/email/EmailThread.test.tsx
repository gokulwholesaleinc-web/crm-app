import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, fireEvent } from '../../test-utils/renderWithProviders';
import { EmailThread } from './EmailThread';
import type { ThreadEmailItem, ThreadResponse } from '../../types/email';

const mockUseEmailThread = vi.fn();

vi.mock('../../hooks/useEmail', () => ({
  useEmailThread: (...args: unknown[]) => mockUseEmailThread(...args),
}));

function makeEmail(overrides: Partial<ThreadEmailItem>): ThreadEmailItem {
  return {
    id: 1,
    direction: 'outbound',
    from_email: 'me@example.com',
    to_email: 'them@example.com',
    cc: null,
    subject: 'test',
    body: 'body',
    body_html: null,
    timestamp: '2026-04-15T21:40:00Z',
    status: 'sent',
    open_count: 0,
    attachments: null,
    thread_id: 'thread-abc',
    ...overrides,
  };
}

function threadResponse(items: ThreadEmailItem[]): ThreadResponse {
  return { items, total: items.length, page: 1, page_size: 50, pages: 1 };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('EmailThread', () => {
  it('renders a thread-level Reply button even when the thread is outbound-only', () => {
    mockUseEmailThread.mockReturnValue({
      data: threadResponse([
        makeEmail({ id: 1, direction: 'outbound', timestamp: '2026-04-17T10:55:00Z' }),
        makeEmail({ id: 2, direction: 'outbound', timestamp: '2026-04-15T21:40:00Z' }),
      ]),
      isLoading: false,
    });

    const onReply = vi.fn();
    renderWithProviders(
      <EmailThread entityType="contacts" entityId={1883} onReply={onReply} />
    );

    expect(screen.getByRole('button', { name: /Reply to thread: test/i })).toBeInTheDocument();
  });

  it('clicking thread-level Reply fires onReply with the newest message', () => {
    const newest = makeEmail({ id: 2, direction: 'outbound', timestamp: '2026-04-17T10:55:00Z' });
    const older = makeEmail({ id: 1, direction: 'outbound', timestamp: '2026-04-15T21:40:00Z' });

    mockUseEmailThread.mockReturnValue({
      data: threadResponse([newest, older]),
      isLoading: false,
    });

    const onReply = vi.fn();
    renderWithProviders(
      <EmailThread entityType="contacts" entityId={1883} onReply={onReply} />
    );

    fireEvent.click(screen.getByRole('button', { name: /Reply to thread/i }));

    expect(onReply).toHaveBeenCalledTimes(1);
    expect(onReply).toHaveBeenCalledWith(newest);
  });

  it('thread-level Reply picks the newest message across mixed directions', () => {
    const inboundFirst = makeEmail({
      id: 1,
      direction: 'inbound',
      from_email: 'them@example.com',
      to_email: 'me@example.com',
      timestamp: '2026-04-15T21:40:00Z',
    });
    const outboundReply = makeEmail({
      id: 2,
      direction: 'outbound',
      timestamp: '2026-04-17T10:55:00Z',
    });

    mockUseEmailThread.mockReturnValue({
      data: threadResponse([outboundReply, inboundFirst]),
      isLoading: false,
    });

    const onReply = vi.fn();
    renderWithProviders(
      <EmailThread entityType="contacts" entityId={1883} onReply={onReply} />
    );

    fireEvent.click(screen.getByRole('button', { name: /Reply to thread/i }));

    expect(onReply).toHaveBeenCalledWith(outboundReply);
  });

  it('does not render Reply button when onReply is not provided', () => {
    mockUseEmailThread.mockReturnValue({
      data: threadResponse([makeEmail({})]),
      isLoading: false,
    });

    renderWithProviders(<EmailThread entityType="contacts" entityId={1883} />);

    expect(screen.queryByRole('button', { name: /Reply to thread/i })).not.toBeInTheDocument();
  });

  it('clicking Reply does not toggle the thread expansion', () => {
    mockUseEmailThread.mockReturnValue({
      data: threadResponse([makeEmail({ id: 1 })]),
      isLoading: false,
    });

    const onReply = vi.fn();
    renderWithProviders(
      <EmailThread entityType="contacts" entityId={1883} onReply={onReply} />
    );

    const header = screen.getByRole('button', { name: /test/i, expanded: true });
    fireEvent.click(screen.getByRole('button', { name: /Reply to thread/i }));

    // Header remains expanded because Reply click does not propagate to the toggle.
    expect(header).toHaveAttribute('aria-expanded', 'true');
  });
});
