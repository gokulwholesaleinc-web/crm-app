/**
 * Tests for the EntitySharing component.
 * Network layer is mocked via vi.mock on the hooks/api modules.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, fireEvent, waitFor } from '../../../test-utils/renderWithProviders';
import { EntitySharing } from '../EntitySharing';

// ---- mock hooks --------------------------------------------------------

const mockMutateAsync = vi.fn().mockResolvedValue({});
const mockRevokeMutate = vi.fn();

vi.mock('../../../hooks/useSharing', () => ({
  useEntityShares: vi.fn(),
  useShareEntity: vi.fn(() => ({
    mutateAsync: mockMutateAsync,
    isPending: false,
  })),
  useRevokeShare: vi.fn(() => ({
    mutate: mockRevokeMutate,
    isPending: false,
  })),
}));

vi.mock('../../../hooks/useAuth', () => ({
  useUsers: vi.fn(() => ({
    data: [
      { id: 1, full_name: 'Alice Smith', email: 'alice@example.com' },
      { id: 2, full_name: 'Bob Jones', email: 'bob@example.com' },
    ],
  })),
}));

// Pull the mocked hook so tests can control its return value
import { useEntityShares } from '../../../hooks/useSharing';
const mockedUseEntityShares = vi.mocked(useEntityShares);

// ---- helpers -----------------------------------------------------------

function renderSharing(props?: Partial<Parameters<typeof EntitySharing>[0]>) {
  return renderWithProviders(
    <EntitySharing
      entityType="leads"
      entityId={42}
      canManage={true}
      {...props}
    />
  );
}

// ---- tests -------------------------------------------------------------

describe('EntitySharing', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockMutateAsync.mockResolvedValue({});
  });

  it('renders empty state when shares list is empty', () => {
    mockedUseEntityShares.mockReturnValue({
      data: { items: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof useEntityShares>);

    renderSharing();
    expect(screen.getByText('Not shared yet.')).toBeTruthy();
  });

  it('shows "Shared with N people" badge with correct count', () => {
    mockedUseEntityShares.mockReturnValue({
      data: {
        items: [
          { id: 10, entity_type: 'leads', entity_id: 42, shared_with_user_id: 1, shared_by_user_id: 99, permission_level: 'view' },
          { id: 11, entity_type: 'leads', entity_id: 42, shared_with_user_id: 2, shared_by_user_id: 99, permission_level: 'edit' },
        ],
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useEntityShares>);

    renderSharing();
    expect(screen.getByText(/Shared with 2 people/i)).toBeTruthy();
  });

  it('revoke button only renders when canManage=true', () => {
    mockedUseEntityShares.mockReturnValue({
      data: {
        items: [
          { id: 10, entity_type: 'leads', entity_id: 42, shared_with_user_id: 1, shared_by_user_id: 99, permission_level: 'view' },
        ],
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useEntityShares>);

    // canManage=true → revoke button present
    const { unmount } = renderSharing({ canManage: true });
    expect(screen.getAllByRole('button', { name: /revoke/i }).length).toBeGreaterThan(0);
    unmount();

    // canManage=false → revoke button absent
    renderSharing({ canManage: false });
    expect(screen.queryByRole('button', { name: /revoke/i })).toBeNull();
  });

  it('clicking Add Share invokes the create mutation with correct body', async () => {
    mockedUseEntityShares.mockReturnValue({
      data: { items: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof useEntityShares>);

    renderSharing({ canManage: true });

    // Open the form
    fireEvent.click(screen.getByRole('button', { name: /share/i }));

    // The SearchableSelect renders a Combobox input; type to filter and pick the first user
    const comboInput = screen.getByPlaceholderText('Search users...');
    fireEvent.change(comboInput, { target: { value: 'Alice' } });

    // Find option and click it
    const option = await screen.findByText(/Alice Smith/i);
    fireEvent.click(option);

    // Submit — pick the last "Share" button (the form submit, not the toggle)
    const shareBtns = screen.getAllByRole('button', { name: /^Share$/i });
    const submitBtn = shareBtns[shareBtns.length - 1] as HTMLElement;
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(mockMutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({
          entity_type: 'leads',
          entity_id: 42,
          shared_with_user_id: 1,
        })
      );
    });
  });

  it('permission picker has all three options', () => {
    mockedUseEntityShares.mockReturnValue({
      data: { items: [] },
      isLoading: false,
    } as unknown as ReturnType<typeof useEntityShares>);

    renderSharing({ canManage: true });

    // Open the form to reveal the permission select
    fireEvent.click(screen.getByRole('button', { name: /share/i }));

    const permSelect = screen.getByLabelText(/permission/i) as HTMLSelectElement;
    const optionValues = Array.from(permSelect.options).map((o) => o.value);

    expect(optionValues).toContain('view');
    expect(optionValues).toContain('edit');
    expect(optionValues).toContain('assignee');
  });
});
