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
  listContacts: vi.fn(),
  listCompanies: vi.fn(),
  listLeads: vi.fn(),
  listProposals: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  showWarning: vi.fn(),
}));

vi.mock('../../../api/sharing', () => ({
  listAdminShares: mocks.listAdminShares,
  bulkShareAdmin: mocks.bulkShareAdmin,
  revokeShare: mocks.revokeShare,
}));

vi.mock('../../../api/contacts', () => ({
  listContacts: mocks.listContacts,
}));

vi.mock('../../../api/companies', () => ({
  listCompanies: mocks.listCompanies,
}));

vi.mock('../../../api/leads', () => ({
  listLeads: mocks.listLeads,
}));

vi.mock('../../../api/proposals', () => ({
  listProposals: mocks.listProposals,
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
      created: 1,
      updated: 0,
      skipped: 0,
      failed: 0,
      items: [],
    });
    mocks.listContacts.mockResolvedValue({
      items: [
        { id: 42, full_name: 'Alex Adams', email: 'alex@example.com' },
        { id: 43, full_name: 'Bob Brown', email: 'bob@example.com' },
      ],
      total: 2,
      page: 1,
      page_size: 25,
    });
    mocks.listCompanies.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
    mocks.listLeads.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
    mocks.listProposals.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 25 });
  });

  it('submits picker-selected record IDs to the bulk endpoint', async () => {
    renderWithProviders(<AdminSharingPage />, { initialRoute: '/admin/sharing' });

    fireEvent.change(screen.getByLabelText('Teammate'), {
      target: { value: '2' },
    });

    // Drive the picker by typing into its search input — that fires the
    // debounced contacts list call. With a 200ms debounce we wait for the
    // mocked match to surface before clicking it.
    const search = await screen.findByPlaceholderText(/Search contact records by name/i);
    fireEvent.change(search, { target: { value: 'Al' } });
    const match = await screen.findByText('Alex Adams');
    fireEvent.click(match);

    fireEvent.click(screen.getByRole('button', { name: /apply/i }));

    await waitFor(() => {
      expect(mocks.bulkShareAdmin).toHaveBeenCalledWith({
        entity_type: 'contacts',
        entity_ids: [42],
        shared_with_user_id: 2,
        permission_level: 'view',
      });
    });
  });

  it('disables Apply until at least one record is selected', async () => {
    renderWithProviders(<AdminSharingPage />, { initialRoute: '/admin/sharing' });

    fireEvent.change(screen.getByLabelText('Teammate'), {
      target: { value: '2' },
    });

    expect(screen.getByRole('button', { name: /apply/i })).toBeDisabled();
    expect(mocks.bulkShareAdmin).not.toHaveBeenCalled();
  });

  it('renders failed bulk results with detail + Retry failed records button', async () => {
    mocks.bulkShareAdmin.mockResolvedValueOnce({
      created: 0,
      updated: 0,
      skipped: 0,
      failed: 1,
      items: [
        {
          entity_id: 42,
          status: 'failed',
          detail: 'contacts 42 not found',
        },
      ],
    });

    renderWithProviders(<AdminSharingPage />, { initialRoute: '/admin/sharing' });

    fireEvent.change(screen.getByLabelText('Teammate'), {
      target: { value: '2' },
    });

    const search = await screen.findByPlaceholderText(/Search contact records by name/i);
    fireEvent.change(search, { target: { value: 'Al' } });
    const match = await screen.findByText('Alex Adams');
    fireEvent.click(match);

    fireEvent.click(screen.getByRole('button', { name: /apply/i }));

    expect(await screen.findByText('Bulk sharing finished with issues')).toBeTruthy();
    // Failed-records list shows the human label (also present in the chip
    // above, so >= 2 matches), not just a bare id.
    expect(screen.getAllByText(/Alex Adams/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/contacts 42 not found/)).toBeTruthy();
    expect(screen.getByRole('button', { name: /retry failed records/i })).toBeTruthy();
    expect(mocks.showWarning).toHaveBeenCalledWith(
      'Bulk sharing finished with 1 failed ID',
    );
  });
});
