import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../../api/admin', () => ({
  getPendingUsers: vi.fn(),
  approveUser: vi.fn(),
  rejectUser: vi.fn(),
  getRejectedEmails: vi.fn(),
  unblockRejectedEmail: vi.fn(),
}));

vi.mock('../../store/authStore', () => ({
  useAuthStore: () => ({ user: { id: 1, role: 'admin', is_superuser: false } }),
}));

vi.mock('react-hot-toast', () => ({
  default: { success: vi.fn(), error: vi.fn() },
}));

import {
  getPendingUsers,
  approveUser,
  rejectUser,
  getRejectedEmails,
  unblockRejectedEmail,
} from '../../api/admin';
import UserApprovalsPage from './UserApprovalsPage';

const PENDING_FIXTURES = [
  { id: 1, email: 'alice@example.com', full_name: 'Alice Smith', avatar_url: null, created_at: '2026-04-01T10:00:00Z' },
  { id: 2, email: 'bob@example.com', full_name: 'Bob Jones', avatar_url: null, created_at: '2026-04-02T10:00:00Z' },
];

const REJECTED_FIXTURES = [
  { id: 10, email: 'spammer@bad.com', rejected_by_id: 1, rejected_by_email: 'admin@crm.com', rejected_at: '2026-04-03T10:00:00Z', reason: 'spam' },
];

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <UserApprovalsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getPendingUsers).mockResolvedValue(PENDING_FIXTURES);
  vi.mocked(getRejectedEmails).mockResolvedValue(REJECTED_FIXTURES);
  vi.mocked(approveUser).mockResolvedValue({ id: 1 } as never);
  vi.mocked(rejectUser).mockResolvedValue({ rejected_email_id: 1 });
  vi.mocked(unblockRejectedEmail).mockResolvedValue(undefined);
});

describe('UserApprovalsPage', () => {
  it('renders both sections with fixture data', async () => {
    renderPage();

    await screen.findByText('alice@example.com');
    expect(screen.getByText('bob@example.com')).toBeInTheDocument();
    await screen.findByText('spammer@bad.com');
    expect(screen.getByText('spam')).toBeInTheDocument();
  });

  it('calls approveUser with selected role when Approve is clicked', async () => {
    renderPage();
    await screen.findByText('alice@example.com');

    const selects = screen.getAllByRole('combobox');
    fireEvent.change(selects[0], { target: { value: 'manager' } });

    const approveBtns = screen.getAllByRole('button', { name: /approve/i });
    fireEvent.click(approveBtns[0]);

    await waitFor(() => {
      expect(approveUser).toHaveBeenCalledWith(1, 'manager');
    });
  });

  it('opens reject modal when Reject is clicked', async () => {
    renderPage();
    await screen.findByText('alice@example.com');

    const rejectBtns = screen.getAllByRole('button', { name: /reject/i });
    fireEvent.click(rejectBtns[0]);

    expect(screen.getByRole('heading', { name: /reject alice smith/i })).toBeInTheDocument();
  });

  it('submits reject mutation from modal', async () => {
    renderPage();
    await screen.findByText('alice@example.com');

    const rejectBtns = screen.getAllByRole('button', { name: /reject/i });
    fireEvent.click(rejectBtns[0]);

    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'not trusted' } });

    const confirmBtns = screen.getAllByRole('button', { name: /^reject$/i });
    fireEvent.click(confirmBtns[confirmBtns.length - 1]);

    await waitFor(() => {
      expect(rejectUser).toHaveBeenCalledWith(1, 'not trusted');
    });
  });

  it('calls unblockRejectedEmail when Unblock is clicked', async () => {
    renderPage();
    await screen.findByText('spammer@bad.com');

    const unblockBtn = screen.getByRole('button', { name: /unblock/i });
    fireEvent.click(unblockBtn);

    await waitFor(() => {
      expect(unblockRejectedEmail).toHaveBeenCalledWith(10);
    });
  });
});
