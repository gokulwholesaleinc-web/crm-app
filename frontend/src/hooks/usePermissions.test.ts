import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';
import type { User } from '../store/authStore';

// Mock authStore so we can control user state without hitting localStorage
vi.mock('../store/authStore', () => {
  let _state: {
    user: User | null;
    isAuthenticated: boolean;
    isLoading: boolean;
    updateUser: ReturnType<typeof vi.fn>;
  } = {
    user: null,
    isAuthenticated: false,
    isLoading: false,
    updateUser: vi.fn(),
  };
  return {
    useAuthStore: (selector: (state: typeof _state) => unknown) =>
      selector(_state),
    __setUser: (u: User | null) => {
      _state = { ..._state, user: u, isAuthenticated: !!u };
    },
    __resetAuth: () => {
      _state = {
        user: null,
        isAuthenticated: false,
        isLoading: false,
        updateUser: vi.fn(),
      };
    },
  };
});

// Mock rolesApi so useMyPermissions doesn't need a real server
vi.mock('../api/roles', () => ({
  rolesApi: {
    listRoles: vi.fn(),
    getMyPermissions: vi.fn(),
    assignRole: vi.fn(),
  },
}));

import { usePermissions, useMyPermissions } from './usePermissions';
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const { __setUser, __resetAuth } = await import('../store/authStore') as any;
import { rolesApi } from '../api/roles';

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
}

const BASE_USER: User = {
  id: 1,
  email: 'test@example.com',
  full_name: 'Test User',
  is_active: true,
  is_superuser: false,
  role: 'sales_rep',
  created_at: '2026-01-01T00:00:00Z',
};

beforeEach(() => {
  vi.clearAllMocks();
  __resetAuth();
});

describe('usePermissions', () => {
  it('defaults to sales_rep permissions when no user is set', () => {
    const { result } = renderHook(() => usePermissions(), { wrapper: makeWrapper() });

    expect(result.current.role).toBe('sales_rep');
    expect(result.current.isAdmin).toBe(false);
    expect(result.current.isManager).toBe(false);
    expect(rolesApi.getMyPermissions).not.toHaveBeenCalled();
  });

  it('denies non-superuser permissions while the server query is still loading', () => {
    vi.mocked(rolesApi.getMyPermissions).mockReturnValue(new Promise(() => {}));
    __setUser({ ...BASE_USER, role: 'admin' });

    const { result } = renderHook(() => usePermissions(), { wrapper: makeWrapper() });

    // Role labels still come from the auth store (so the sidebar can show
    // "Admin" while loading), but the permission checks themselves
    // deny-by-default until /api/roles/me/permissions resolves. Without
    // this gate an auth-store role of "admin" would briefly grant full
    // CRUD on a stale browser tab before the real payload lands.
    expect(result.current.isAdmin).toBe(true);
    expect(result.current.canCreate('leads')).toBe(false);
    expect(result.current.canDelete('settings')).toBe(false);
    expect(result.current.canDelete('roles')).toBe(false);
    expect(result.current.isUsingFallbackPermissions).toBe(true);
  });

  it('uses server effective permissions over the role fallback', async () => {
    vi.mocked(rolesApi.getMyPermissions).mockResolvedValue({
      role: 'custom_read_only',
      permissions: { leads: ['read'], reports: ['read'] },
    });
    __setUser({ ...BASE_USER, role: 'sales_rep' });

    const { result } = renderHook(() => usePermissions(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.role).toBe('custom_read_only'));

    expect(result.current.canRead('leads')).toBe(true);
    expect(result.current.canCreate('leads')).toBe(false);
    expect(result.current.canRead('reports')).toBe(true);
    expect(result.current.isUsingFallbackPermissions).toBe(false);
  });

  it('grants all permissions to superuser regardless of role', () => {
    vi.mocked(rolesApi.getMyPermissions).mockReturnValue(new Promise(() => {}));
    __setUser({ ...BASE_USER, role: 'viewer', is_superuser: true });

    const { result } = renderHook(() => usePermissions(), { wrapper: makeWrapper() });

    expect(result.current.hasPermission('roles', 'delete')).toBe(true);
    expect(result.current.isAdmin).toBe(true);
  });

  it('denies non-superuser permissions when the server query errors', async () => {
    vi.mocked(rolesApi.getMyPermissions).mockRejectedValue(new Error('offline'));
    __setUser({ ...BASE_USER, role: 'viewer' });

    const { result } = renderHook(() => usePermissions(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));

    // Even READ is denied when the server gate is unresolved — a 500 on
    // /api/roles/me/permissions during deploy lag would otherwise let an
    // auth-store role of "viewer" expose READ-only screens while the
    // actual permission set is unknown. Better to show empty/error than
    // to lie.
    expect(result.current.canRead('leads')).toBe(false);
    expect(result.current.canCreate('leads')).toBe(false);
    expect(result.current.isUsingFallbackPermissions).toBe(true);
    expect(result.current.isError).toBe(true);
  });

  it('does not expose retired opportunities permissions in fallback UI gates', () => {
    vi.mocked(rolesApi.getMyPermissions).mockReturnValue(new Promise(() => {}));
    __setUser({ ...BASE_USER, role: 'admin' });

    const { result } = renderHook(() => usePermissions(), { wrapper: makeWrapper() });

    expect(result.current.permissions).not.toHaveProperty('opportunities');
    expect(result.current.hasPermission('opportunities', 'read')).toBe(false);
  });
});

describe('useMyPermissions', () => {
  it('returns server-side permissions on success', async () => {
    __setUser({ ...BASE_USER, role: 'admin' });
    vi.mocked(rolesApi.getMyPermissions).mockResolvedValue({
      role: 'admin',
      permissions: {
        leads: ['create', 'read', 'update', 'delete'],
        opportunities: ['read'],
      },
    });

    const { result } = renderHook(() => useMyPermissions(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.role).toBe('admin');
    expect(result.current.data?.permissions.leads).toContain('delete');
    expect(result.current.data?.permissions).not.toHaveProperty('opportunities');
  });

  it('exposes loading state on initial fetch', () => {
    __setUser({ ...BASE_USER, role: 'sales_rep' });
    // Never resolves — stays pending
    vi.mocked(rolesApi.getMyPermissions).mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useMyPermissions(), { wrapper: makeWrapper() });

    expect(result.current.isPending).toBe(true);
  });

  it('exposes error state when the API fails', async () => {
    __setUser({ ...BASE_USER, role: 'sales_rep' });
    vi.mocked(rolesApi.getMyPermissions).mockRejectedValue(new Error('Unauthorized'));

    const { result } = renderHook(() => useMyPermissions(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error?.message).toBe('Unauthorized');
  });
});
