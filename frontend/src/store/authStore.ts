/**
 * Zustand store for authentication state management.
 *
 * This store is the single source of truth for the access token and the
 * current user. `isAuthenticated` is derived from both — it is NOT persisted,
 * so a tampered localStorage slice cannot claim authenticated with no token.
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { registerAuthTokenGetter } from '../api/client';
import { clearTenantSlugOnLogout } from '../providers/TenantProvider';

export type RoleName = 'admin' | 'manager' | 'sales_rep' | 'viewer';

export interface User {
  id: number;
  email: string;
  full_name: string;
  phone?: string | null;
  job_title?: string | null;
  is_active: boolean;
  is_superuser: boolean;
  role?: string;
  avatar_url?: string | null;
  created_at: string;
  last_login?: string | null;
}

interface AuthState {
  user: User | null;
  token: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;

  // Actions
  setUser: (user: User | null) => void;
  setToken: (token: string | null) => void;
  login: (user: User, token: string) => void;
  logout: () => void;
  setLoading: (loading: boolean) => void;
  updateUser: (userData: Partial<User>) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: true,

      setUser: (user) =>
        set({
          user,
          isAuthenticated: !!user && !!get().token,
        }),

      setToken: (token) =>
        set({
          token,
          isAuthenticated: !!token && !!get().user,
        }),

      login: (user, token) =>
        set({
          user,
          token,
          isAuthenticated: true,
          isLoading: false,
        }),

      logout: () => {
        // Clear all session-scoped state in one place so every caller
        // (PrivateRoute, useLogout hook, authApi.logout) gets a clean slate.
        clearTenantSlugOnLogout();
        set({
          user: null,
          token: null,
          isAuthenticated: false,
          isLoading: false,
        });
      },

      setLoading: (isLoading) => set({ isLoading }),

      updateUser: (userData) =>
        set((state) => ({
          user: state.user ? { ...state.user, ...userData } : null,
        })),
    }),
    {
      name: 'crm-auth-storage',
      storage: createJSONStorage(() => localStorage),
      // isAuthenticated is intentionally NOT persisted — it's derived from
      // token + user on rehydration so a tampered storage slice cannot claim
      // authenticated without both halves present.
      partialize: (state) => ({
        user: state.user,
        token: state.token,
      }),
      onRehydrateStorage: () => (state) => {
        if (state) {
          state.isAuthenticated = !!state.token && !!state.user;
          state.setLoading(false);
        }
      },
    }
  )
);

// Register the axios client's token getter with zustand as the source of
// truth. The axios interceptor reads through this getter on every request.
registerAuthTokenGetter(() => useAuthStore.getState().token);

// Selectors for common access patterns
export const selectUser = (state: AuthState) => state.user;
export const selectToken = (state: AuthState) => state.token;
export const selectIsAuthenticated = (state: AuthState) => state.isAuthenticated;
export const selectIsLoading = (state: AuthState) => state.isLoading;
