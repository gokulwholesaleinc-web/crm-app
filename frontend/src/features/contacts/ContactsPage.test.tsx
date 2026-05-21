import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen } from '../../test-utils/renderWithProviders';
import { useAuthStore, type User } from '../../store/authStore';
import ContactsPage from './ContactsPage';
import type { SavedFilter } from '../../api/filters';

const mocks = vi.hoisted(() => ({
  deleteSavedFilter: vi.fn(),
  useContacts: vi.fn(),
  useCreateContact: vi.fn(),
  useUpdateContact: vi.fn(),
  useCheckDuplicates: vi.fn(),
  useSavedFilters: vi.fn(),
  useDeleteSavedFilter: vi.fn(),
}));

vi.mock('../../hooks/useContacts', () => ({
  useContacts: mocks.useContacts,
  useCreateContact: mocks.useCreateContact,
  useUpdateContact: mocks.useUpdateContact,
}));

vi.mock('../../hooks/useDedup', () => ({
  useCheckDuplicates: mocks.useCheckDuplicates,
}));

vi.mock('../../hooks/useFilters', () => ({
  useSavedFilters: mocks.useSavedFilters,
  useDeleteSavedFilter: mocks.useDeleteSavedFilter,
}));

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

vi.mock('../../utils/toast', () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

const TEST_USER: User = {
  id: 7,
  email: 'owner@example.com',
  full_name: 'List Owner',
  is_active: true,
  is_superuser: false,
  role: 'sales_rep',
  created_at: '2026-05-20T00:00:00.000Z',
};

function savedFilter(overrides: Partial<SavedFilter>): SavedFilter {
  return {
    id: 1,
    name: 'Owned Smart List',
    entity_type: 'contacts',
    filters: {
      operator: 'and',
      conditions: [{ field: 'email', op: 'is_not_empty' }],
    },
    user_id: TEST_USER.id,
    is_default: false,
    is_public: false,
    created_at: '2026-05-20T00:00:00.000Z',
    updated_at: '2026-05-20T00:00:00.000Z',
    ...overrides,
  };
}

describe('ContactsPage smart list controls', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      user: TEST_USER,
      token: 'token',
      isAuthenticated: true,
      isLoading: false,
    });
    mocks.useContacts.mockReturnValue({
      data: { items: [], total: 0, pages: 1 },
      isLoading: false,
      error: null,
    });
    mocks.useCreateContact.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mocks.useUpdateContact.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mocks.useCheckDuplicates.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
    mocks.useDeleteSavedFilter.mockReturnValue({
      mutateAsync: mocks.deleteSavedFilter,
      isPending: false,
    });
  });

  it('only shows delete buttons for smart lists owned by the current user', () => {
    mocks.useSavedFilters.mockReturnValue({
      data: [
        savedFilter({ id: 1, name: 'My Smart List', user_id: TEST_USER.id }),
        savedFilter({ id: 2, name: 'Shared Smart List', user_id: 99, is_public: true }),
      ],
    });

    renderWithProviders(<ContactsPage />);

    expect(screen.getByRole('button', { name: 'My Smart List' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Shared Smart List/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete My Smart List smart list' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Delete Shared Smart List smart list' })).not.toBeInTheDocument();
  });
});
