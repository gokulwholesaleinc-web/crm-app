import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { fireEvent, renderWithProviders, screen, waitFor } from '../../test-utils/renderWithProviders';
import { server } from '../../test-setup';
import { useAuthStore, type User } from '../../store/authStore';
import AdminAuditPage from './AdminAuditPage';

// MSW-based test (CRM CLAUDE.md: "MUST NOT MOCK ANYTHING"). Handlers
// intercept the four /api/admin/audit/* endpoints the page calls; the
// captured request URLs let us assert filter-passthrough on the wire
// instead of mocking the hook module.

const TEST_USER: User = {
  id: 1,
  email: 'admin@example.com',
  full_name: 'Audit Admin',
  is_active: true,
  is_superuser: false,
  role: 'admin',
  created_at: '2026-05-18T00:00:00.000Z',
};

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

interface CapturedRequests {
  summary: URL[];
  feed: URL[];
  userDetail: URL[];
  entityDetail: URL[];
}

function installAuditHandlers(): CapturedRequests {
  const captured: CapturedRequests = {
    summary: [],
    feed: [],
    userDetail: [],
    entityDetail: [],
  };
  server.use(
    http.get('*/api/admin/audit/summary', ({ request }) => {
      captured.summary.push(new URL(request.url));
      return HttpResponse.json(summaryFixture);
    }),
    http.get('*/api/admin/audit/feed', ({ request }) => {
      captured.feed.push(new URL(request.url));
      return HttpResponse.json(feedFixture);
    }),
    http.get('*/api/admin/audit/users/:userId', ({ request }) => {
      captured.userDetail.push(new URL(request.url));
      return HttpResponse.json(userDetailFixture);
    }),
    http.get('*/api/admin/audit/entities/:entityType/:entityId', ({ request }) => {
      captured.entityDetail.push(new URL(request.url));
      return HttpResponse.json(entityDetailFixture);
    }),
  );
  return captured;
}

beforeEach(() => {
  act(() => {
    useAuthStore.setState({
      user: TEST_USER,
      token: 'token',
      isAuthenticated: true,
      isLoading: false,
    });
  });
});

afterEach(() => {
  vi.restoreAllMocks();
  act(() => {
    useAuthStore.setState({
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,
    });
  });
});

describe('AdminAuditPage', () => {
  it('renders the live feed and opens the event drawer', async () => {
    installAuditHandlers();
    renderWithProviders(<AdminAuditPage />);

    expect(screen.getByRole('heading', { name: /crm audit/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText('Lorenzo Rossi').length).toBeGreaterThan(0);
    });
    expect(screen.getByText('status')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /details/i }));

    expect(screen.getByRole('dialog', { name: /audit event #10/i })).toBeInTheDocument();
    expect(screen.getByText(/127\.0\.0\.1/)).toBeInTheDocument();
    expect(screen.getByText(/old_value/)).toBeInTheDocument();
  });

  it('renders the time by rep, entities, and security tabs', async () => {
    installAuditHandlers();
    renderWithProviders(<AdminAuditPage />);

    await waitFor(() => {
      expect(screen.getAllByText('Lorenzo Rossi').length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole('button', { name: /time by rep/i }));
    expect(screen.getAllByText('Lorenzo Rossi').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/1h 1m/).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: /entities/i }));
    expect(screen.getByText('Acme Buyer')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /security/i }));
    expect(screen.getByText(/deleted lead #88/i)).toBeInTheDocument();
  });

  it('opens rep and entity detail drawers', async () => {
    installAuditHandlers();
    renderWithProviders(<AdminAuditPage />);

    await waitFor(() => {
      expect(screen.getAllByText('Lorenzo Rossi').length).toBeGreaterThan(0);
    });

    fireEvent.click(screen.getByRole('button', { name: /time by rep/i }));
    fireEvent.click(screen.getByRole('button', { name: /inspect/i }));
    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: /lorenzo rossi/i })).toBeInTheDocument();
    });
    // Drawer body comes from the userDetail request — wait for the MSW
    // handler to resolve before asserting.
    await waitFor(() => {
      expect(screen.getByText(/recent active-time sessions/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /^close$/i }));

    fireEvent.click(screen.getByRole('button', { name: /entities/i }));
    fireEvent.click(screen.getByRole('button', { name: /inspect/i }));
    await waitFor(() => {
      expect(screen.getByRole('dialog', { name: /acme buyer/i })).toBeInTheDocument();
    });
  });

  it('passes user filter to the audit feed request', async () => {
    const captured = installAuditHandlers();
    renderWithProviders(<AdminAuditPage />);

    await waitFor(() => {
      expect(captured.feed.length).toBeGreaterThan(0);
    });

    fireEvent.change(screen.getByLabelText(/user/i), { target: { value: '2' } });

    await waitFor(() => {
      const last = captured.feed.at(-1);
      expect(last?.searchParams.get('user_id')).toBe('2');
    });
  });

  it('exports the visible feed and labels the row count', async () => {
    installAuditHandlers();
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

    await waitFor(() => {
      // Button label now embeds the visible/total counts so admins
      // can't confuse "Export visible" with "Export all matching".
      expect(screen.getByRole('button', { name: /export visible \(1\/1\)/i })).toBeInTheDocument();
    });

    // Spy on createElement AFTER render so React's tree construction
    // (which itself calls createElement under the hood) isn't affected.
    // Only the anchor synthesized inside downloadVisibleFeedCsv hits
    // this stub.
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
});
