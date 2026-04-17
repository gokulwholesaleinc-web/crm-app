import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createElement } from 'react';
import type { User } from '../store/authStore';

// Mock authStore so we can control user state without hitting localStorage
vi.mock('../store/authStore', () => {
  let _user: User | null = null;
  return {
    useAuthStore: (selector: (state: { user: User | null }) => unknown) =>
      selector({ user: _user }),
    __setUser: (u: User | null) => { _user = u; },
  };
});

// Mock rolesApi so useMyPermissions doesn't need a real server
vi.mock('../api/roles', () => ({
  rolesApi: {
    listRoles: vi.fn(),
    getMyPermissions: vi.fn(),
  },
}));

import { usePermissions, useMyPermissions } from './usePermissions';
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const { __setUser } = await import('../store/authStore') as any;
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
  __setUser(null);
});

describe('usePermissions', () => {
  it('defaults to sales_rep permissions when no user is set', () => {
    const { result } = renderHook(() => usePermissions());

    expect(result.current.role).toBe('sales_rep');
    expect(result.current.isAdmin).toBe(false);
    expect(result.current.isManager).toBe(false);
  });

  it('grants full permissions to admin role', () => {
    __setUser({ ...BASE_USER, role: 'admin' });

    const { result } = renderHook(() => usePermissions());

    expect(result.current.isAdmin).toBe(true);
    expect(result.current.canCreate('leads')).toBe(true);
    expect(result.current.canDelete('settings')).toBe(true);
    expect(result.current.canDelete('roles')).toBe(true);
  });

  it('denies delete on settings and roles for sales_rep', () => {
    __setUser({ ...BASE_USER, role: 'sales_rep' });

    const { result } = renderHook(() => usePermissions());

    expect(result.current.role).toBe('sales_rep');
    expect(result.current.canDelete('settings')).toBe(false);
    expect(result.current.canDelete('roles')).toBe(false);
    expect(result.current.canRead('leads')).toBe(true);
  });

  it('grants all permissions to superuser regardless of role', () => {
    __setUser({ ...BASE_USER, role: 'viewer', is_superuser: true });

    const { result } = renderHook(() => usePermissions());

    expect(result.current.hasPermission('roles', 'delete')).toBe(true);
    expect(result.current.isAdmin).toBe(true);
  });

  it('viewer can only read, not create', () => {
    __setUser({ ...BASE_USER, role: 'viewer' });

    const { result } = renderHook(() => usePermissions());

    expect(result.current.canRead('leads')).toBe(true);
    expect(result.current.canCreate('leads')).toBe(false);
  });
});

describe('useMyPermissions', () => {
  it('returns server-side permissions on success', async () => {
    vi.mocked(rolesApi.getMyPermissions).mockResolvedValue({
      role: 'admin',
      permissions: { leads: ['create', 'read', 'update', 'delete'] },
    });

    const { result } = renderHook(() => useMyPermissions(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.role).toBe('admin');
    expect(result.current.data?.permissions.leads).toContain('delete');
  });

  it('exposes loading state on initial fetch', () => {
    // Never resolves — stays pending
    vi.mocked(rolesApi.getMyPermissions).mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useMyPermissions(), { wrapper: makeWrapper() });

    expect(result.current.isPending).toBe(true);
  });

  it('exposes error state when the API fails', async () => {
    vi.mocked(rolesApi.getMyPermissions).mockRejectedValue(new Error('Unauthorized'));

    const { result } = renderHook(() => useMyPermissions(), { wrapper: makeWrapper() });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error?.message).toBe('Unauthorized');
  });
});
