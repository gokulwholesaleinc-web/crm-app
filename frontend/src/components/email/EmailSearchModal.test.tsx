import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, waitFor, fireEvent } from '../../test-utils/renderWithProviders';
import { EmailSearchModal } from './EmailSearchModal';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

const mockSearch = vi.fn();
vi.mock('../../api/email', () => ({
  emailApi: {
    search: (...args: unknown[]) => mockSearch(...args),
  },
}));

const BASE_RESULT = {
  id: 1,
  kind: 'received' as const,
  subject: 'Hello from contact',
  snippet: 'Test snippet',
  from_email: 'contact@example.com',
  to_email: 'me@example.com',
  sent_at: '2026-01-01T12:00:00Z',
  thread_id: null,
  entity_type: 'contacts',
  entity_id: 42,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockSearch.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25, pages: 0 });
});

describe('EmailSearchModal', () => {
  it('renders the search input when isOpen is true', () => {
    renderWithProviders(<EmailSearchModal isOpen={true} onClose={vi.fn()} />);
    expect(screen.getByPlaceholderText(/search emails/i)).toBeInTheDocument();
  });

  it('does not render when isOpen is false', () => {
    renderWithProviders(<EmailSearchModal isOpen={false} onClose={vi.fn()} />);
    expect(screen.queryByPlaceholderText(/search emails/i)).not.toBeInTheDocument();
  });

  it('fires debounced search after typing in the input', async () => {
    renderWithProviders(<EmailSearchModal isOpen={true} onClose={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText(/search emails/i), {
      target: { value: 'hello' },
    });
    await waitFor(() => expect(mockSearch).toHaveBeenCalledWith(
      expect.objectContaining({ q: 'hello' })
    ), { timeout: 600 });
  });

  it('clicking a result navigates to entity emails tab and calls onClose', async () => {
    mockSearch.mockResolvedValueOnce({ items: [BASE_RESULT], total: 1, page: 1, page_size: 25, pages: 1 });
    const onClose = vi.fn();
    renderWithProviders(<EmailSearchModal isOpen={true} onClose={onClose} />);

    fireEvent.change(screen.getByPlaceholderText(/search emails/i), {
      target: { value: 'hello' },
    });
    await waitFor(() => screen.getByText('Hello from contact'));

    fireEvent.click(screen.getByText('Hello from contact'));
    expect(mockNavigate).toHaveBeenCalledWith(
      '/contacts/42?tab=emails&email=received%3A1'
    );
    expect(onClose).toHaveBeenCalled();
  });

  it('ESC key closes the modal via Headless UI Dialog', async () => {
    const onClose = vi.fn();
    renderWithProviders(<EmailSearchModal isOpen={true} onClose={onClose} />);
    fireEvent.keyDown(document.body, { key: 'Escape' });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('shows no-results message when search returns empty', async () => {
    mockSearch.mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 25, pages: 0 });
    renderWithProviders(<EmailSearchModal isOpen={true} onClose={vi.fn()} />);

    fireEvent.change(screen.getByPlaceholderText(/search emails/i), {
      target: { value: 'notfound' },
    });
    await waitFor(() =>
      screen.getByText(/no emails found/i)
    );
  });
});
