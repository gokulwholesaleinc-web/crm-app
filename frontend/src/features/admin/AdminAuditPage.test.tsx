import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, renderWithProviders, screen, waitFor } from '../../test-utils/renderWithProviders';
import AdminAuditPage from './AdminAuditPage';

const MOCK_AUTH_STATE = {
  user: { id: 1, role: 'admin', is_superuser: false },
};

vi.mock('../../store/authStore', () => ({
  useAuthStore: (selector?: (s: typeof MOCK_AUTH_STATE) => unknown) =>
    selector ? selector(MOCK_AUTH_STATE) : MOCK_AUTH_STATE,
}));

vi.mock('../../hooks/useAudit', () => ({
  useAdminAuditSummary: vi.fn(),
  useAdminAuditFeed: vi.fn(),
  useAdminAuditUserDetail: vi.fn(),
  useAdminAuditEntityDetail: vi.fn(),
}));

import {
  useAdminAuditFeed,
  useAdminAuditEntityDetail,
  useAdminAuditSummary,
  useAdminAuditUserDetail,
} from '../../hooks/useAudit';

const summaryFixture = {
  start_at: '2026-05-18T00:00:00Z',
  end_at: '2026-05-18T23:59:59Z',
  totals: {
    audit_events: 1,
    active_crm_seconds: 3660,
    activities: 2,
    calls: 1,
    emails: 1,
    security_events: 1,
  },
  users: [
    {
      user_id: 2,
      user_name: 'Lorenzo Rossi',
      user_email: 'lorenzo@example.com',
      role: 'sales_rep',
      active_crm_seconds: 3660,
      audit_events: 1,
      calls: 1,
      call_duration_minutes: 12,
      emails: 1,
      proposals_touched: 1,
      opportunities_touched: 0,
      last_active_at: '2026-05-18T14:20:00Z',
    },
  ],
  entities: [
    {
      entity_type: 'contacts',
      entity_id: 44,
      label: 'Acme Buyer',
      owner_id: 2,
      owner_name: 'Lorenzo Rossi',
      active_crm_seconds: 3660,
      activity_count: 2,
      audit_count: 1,
      last_touched_at: '2026-05-18T14:20:00Z',
      last_touched_by_id: 2,
      last_touched_by_name: 'Lorenzo Rossi',
    },
  ],
  security: [
    {
      id: 'audit-9',
      severity: 'high',
      category: 'delete',
      description: 'Lorenzo Rossi deleted lead #88',
      user_id: 2,
      user_name: 'Lorenzo Rossi',
      entity_type: 'leads',
      entity_id: 88,
      count: 1,
      created_at: '2026-05-18T14:30:00Z',
    },
  ],
};

const feedFixture = {
  items: [
    {
      id: 10,
      entity_type: 'contacts',
      entity_id: 44,
      action: 'update',
      changes: [{ field: 'status', old_value: 'new', new_value: 'active' }],
      user_id: 2,
      user_name: 'Lorenzo Rossi',
      user_email: 'lorenzo@example.com',
      ip_address: '127.0.0.1',
      created_at: '2026-05-18T14:20:00Z',
    },
  ],
  total: 1,
  page: 1,
  page_size: 50,
  pages: 1,
};

const userDetailFixture = {
  summary: summaryFixture.users[0],
  feed: feedFixture,
  sessions: [
    {
      id: 1,
      user_id: 2,
      user_name: 'Lorenzo Rossi',
      entity_type: 'contacts',
      entity_id: 44,
      started_at: '2026-05-18T13:20:00Z',
      last_seen_at: '2026-05-18T14:20:00Z',
      ended_at: null,
      duration_seconds: 3600,
      source: 'detail_page',
      metadata: null,
    },
  ],
};

const entityDetailFixture = {
  summary: summaryFixture.entities[0],
  feed: feedFixture,
  sessions: userDetailFixture.sessions,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useAdminAuditSummary).mockReturnValue({
    data: summaryFixture,
    isLoading: false,
    refetch: vi.fn(),
  } as never);
  vi.mocked(useAdminAuditFeed).mockReturnValue({
    data: feedFixture,
    isLoading: false,
    refetch: vi.fn(),
  } as never);
  vi.mocked(useAdminAuditUserDetail).mockReturnValue({
    data: userDetailFixture,
    isLoading: false,
  } as never);
  vi.mocked(useAdminAuditEntityDetail).mockReturnValue({
    data: entityDetailFixture,
    isLoading: false,
  } as never);
});

describe('AdminAuditPage', () => {
  it('renders the live feed and opens the event drawer', async () => {
    renderWithProviders(<AdminAuditPage />);

    expect(screen.getByRole('heading', { name: /crm audit/i })).toBeInTheDocument();
    expect(screen.getAllByText('Lorenzo Rossi').length).toBeGreaterThan(0);
    expect(screen.getByText('status')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /details/i }));

    expect(screen.getByRole('dialog', { name: /audit event #10/i })).toBeInTheDocument();
    expect(screen.getByText(/127\.0\.0\.1/)).toBeInTheDocument();
    expect(screen.getByText(/old_value/)).toBeInTheDocument();
  });

  it('renders the time by rep, entities, and security tabs', () => {
    renderWithProviders(<AdminAuditPage />);

    fireEvent.click(screen.getByRole('button', { name: /time by rep/i }));
    expect(screen.getAllByText('Lorenzo Rossi').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/1h 1m/).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /entities/i }));
    expect(screen.getByText('Acme Buyer')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /security/i }));
    expect(screen.getByText(/deleted lead #88/i)).toBeInTheDocument();
  });

  it('opens rep and entity detail drawers', () => {
    renderWithProviders(<AdminAuditPage />);

    fireEvent.click(screen.getByRole('button', { name: /time by rep/i }));
    fireEvent.click(screen.getByRole('button', { name: /inspect/i }));
    expect(screen.getByRole('dialog', { name: /lorenzo rossi/i })).toBeInTheDocument();
    expect(screen.getByText(/recent active-time sessions/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /^close$/i }));

    fireEvent.click(screen.getByRole('button', { name: /entities/i }));
    fireEvent.click(screen.getByRole('button', { name: /inspect/i }));
    expect(screen.getByRole('dialog', { name: /acme buyer/i })).toBeInTheDocument();
  });

  it('resets filters and exports the visible feed', async () => {
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    const createObjectURL = vi.fn(() => 'blob:test');
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: createObjectURL,
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: revokeObjectURL,
    });
    const click = vi.fn();

    renderWithProviders(<AdminAuditPage />);

    fireEvent.change(screen.getByLabelText(/search/i), { target: { value: 'status' } });
    fireEvent.click(screen.getByRole('button', { name: /reset filters/i }));

    await waitFor(() => {
      expect(useAdminAuditFeed).toHaveBeenLastCalledWith(expect.objectContaining({
        search: undefined,
      }));
    });

    const createElement = vi.spyOn(document, 'createElement').mockReturnValue({
      click,
      href: '',
      download: '',
    } as unknown as HTMLAnchorElement);
    fireEvent.click(screen.getByRole('button', { name: /export visible/i }));
    expect(createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();

    createElement.mockRestore();
    Object.defineProperty(URL, 'createObjectURL', {
      configurable: true,
      value: originalCreateObjectURL,
    });
    Object.defineProperty(URL, 'revokeObjectURL', {
      configurable: true,
      value: originalRevokeObjectURL,
    });
  });

  it('passes user filters to the audit hooks', async () => {
    renderWithProviders(<AdminAuditPage />);

    fireEvent.change(screen.getByLabelText(/user/i), { target: { value: '2' } });

    await waitFor(() => {
      expect(useAdminAuditFeed).toHaveBeenLastCalledWith(expect.objectContaining({
        user_id: 2,
      }));
    });
  });
});
