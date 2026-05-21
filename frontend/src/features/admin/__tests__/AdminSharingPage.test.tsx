import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  fireEvent,
  renderWithProviders,
  screen,
  waitFor,
} from '../../../test-utils/renderWithProviders';
import AdminSharingPage from '../AdminSharingPage';

const mocks = vi.hoisted(() => ({
  currentUser: {
    id: 1,
    full_name: 'Admin User',
    email: 'admin@example.com',
    is_superuser: true,
    role: 'admin',
  },
  listAdminShares: vi.fn(),
  bulkShareAdmin: vi.fn(),
  revokeShare: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  showWarning: vi.fn(),
}));

vi.mock('../../../api/sharing', () => ({
  listAdminShares: mocks.listAdminShares,
  bulkShareAdmin: mocks.bulkShareAdmin,
  revokeShare: mocks.revokeShare,
}));

vi.mock('../../../hooks/useAuth', () => ({
  useUsers: vi.fn(() => ({
    data: [
      {
        id: 1,
        full_name: 'Admin User',
        email: 'admin@example.com',
      },
      {
        id: 2,
        full_name: 'Sales Rep',
        email: 'rep@example.com',
      },
    ],
  })),
}));

vi.mock('../../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

vi.mock('../../../store/authStore', () => ({
  useAuthStore: vi.fn((selector: (state: { user: typeof mocks.currentUser }) => unknown) =>
    selector({ user: mocks.currentUser })
  ),
}));

vi.mock('../../../utils/toast', () => ({
  showSuccess: mocks.showSuccess,
  showError: mocks.showError,
  showWarning: mocks.showWarning,
}));

describe('AdminSharingPage bulk add', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.listAdminShares.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      page_size: 50,
    });
    mocks.bulkShareAdmin.mockResolvedValue({
      created: 3,
      updated: 0,
      skipped: 0,
      failed: 0,
      items: [],
    });
  });

  it('submits parsed IDs to the admin bulk-sharing endpoint', async () => {
    renderWithProviders(<AdminSharingPage />, { initialRoute: '/admin/sharing' });

    fireEvent.change(screen.getByLabelText('Teammate'), {
      target: { value: '2' },
    });
    fireEvent.change(screen.getByLabelText('Record IDs'), {
      target: { value: '42, 43\n44 44' },
    });
    fireEvent.click(screen.getByRole('button', { name: /apply/i }));

    await waitFor(() => {
      expect(mocks.bulkShareAdmin).toHaveBeenCalledWith({
        entity_type: 'contacts',
        entity_ids: [42, 43, 44],
        shared_with_user_id: 2,
        permission_level: 'view',
      });
    });
  });

  it('blocks invalid record IDs before submitting', async () => {
    renderWithProviders(<AdminSharingPage />, { initialRoute: '/admin/sharing' });

    fireEvent.change(screen.getByLabelText('Teammate'), {
      target: { value: '2' },
    });
    fireEvent.change(screen.getByLabelText('Record IDs'), {
      target: { value: '42 nope' },
    });

    const applyButton = screen.getByRole('button', { name: /apply/i });
    expect(applyButton).toBeDisabled();
    expect(screen.getByText(/invalid: nope/i)).toBeTruthy();
    expect(mocks.bulkShareAdmin).not.toHaveBeenCalled();
  });

  it('blocks oversized ranges before submitting', async () => {
    renderWithProviders(<AdminSharingPage />, { initialRoute: '/admin/sharing' });

    fireEvent.change(screen.getByLabelText('Teammate'), {
      target: { value: '2' },
    });
    fireEvent.change(screen.getByLabelText('Record IDs'), {
      target: { value: '1-501' },
    });

    expect(screen.getByRole('button', { name: /apply/i })).toBeDisabled();
    expect(screen.getByText(/limit is 500 records/i)).toBeTruthy();
    expect(mocks.bulkShareAdmin).not.toHaveBeenCalled();
  });

  it('renders failed bulk results as a warning state', async () => {
    mocks.bulkShareAdmin.mockResolvedValueOnce({
      created: 0,
      updated: 0,
      skipped: 0,
      failed: 1,
      items: [
        {
          entity_id: 999,
          status: 'failed',
          detail: 'contacts 999 not found',
        },
      ],
    });

    renderWithProviders(<AdminSharingPage />, { initialRoute: '/admin/sharing' });

    fireEvent.change(screen.getByLabelText('Teammate'), {
      target: { value: '2' },
    });
    fireEvent.change(screen.getByLabelText('Record IDs'), {
      target: { value: '999' },
    });
    fireEvent.click(screen.getByRole('button', { name: /apply/i }));

    expect(await screen.findByText('Bulk sharing finished with issues')).toBeTruthy();
    expect(screen.getByText('Failed IDs: 999')).toBeTruthy();
    expect(mocks.showWarning).toHaveBeenCalledWith('Bulk sharing finished with 1 failed ID');
  });
});
