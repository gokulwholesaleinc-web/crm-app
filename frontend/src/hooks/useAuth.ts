/**
 * Authentication hooks using TanStack Query
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { authApi } from '../api/auth';
import { useAuthStore } from '../store';
import type { User, UserCreate, UserUpdate, LoginRequest } from '../types';

// Query keys
export const authKeys = {
  all: ['auth'] as const,
  user: () => [...authKeys.all, 'user'] as const,
  users: (skip?: number, limit?: number) => [...authKeys.all, 'users', { skip, limit }] as const,
};

/**
 * Hook to fetch current user profile
 */
export function useUser() {
  const { setUser, setLoading, token } = useAuthStore();

  return useQuery({
    queryKey: authKeys.user(),
    queryFn: () => authApi.getMe(),
    enabled: !!token,
    onSuccess: (data: User) => {
      setUser(data);
      setLoading(false);
    },
    onError: () => {
      setUser(null);
      setLoading(false);
    },
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: false,
  });
}

/**
 * Hook for user login
 */
export function useLogin() {
  const { login: storeLogin } = useAuthStore();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (credentials: LoginRequest) => authApi.login(credentials),
    onSuccess: async (data) => {
      // Token is already stored by authApi.login
      useAuthStore.getState().setToken(data.access_token);

      // Fetch user profile
      const user = await authApi.getMe();
      storeLogin(user, data.access_token);

      // Invalidate queries to refresh data with new auth
      queryClient.invalidateQueries();
    },
  });
}

/**
 * Hook for user registration
 */
export function useRegister() {
  const { login: storeLogin } = useAuthStore();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: UserCreate) => {
      // Register user
      await authApi.register(data);

      // Login after registration
      const token = await authApi.login({
        email: data.email,
        password: data.password,
      });

      return token;
    },
    onSuccess: async (data) => {
      useAuthStore.getState().setToken(data.access_token);

      // Fetch user profile
      const user = await authApi.getMe();
      storeLogin(user, data.access_token);

      queryClient.invalidateQueries();
    },
  });
}

/**
 * Hook for user logout
 */
export function useLogout() {
  const { logout: storeLogout } = useAuthStore();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      authApi.logout();
      storeLogout();
    },
    onSuccess: () => {
      // Clear all cached queries
      queryClient.clear();
    },
  });
}

/**
 * Hook to update current user profile
 */
export function useUpdateProfile() {
  const { updateUser } = useAuthStore();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: UserUpdate) => authApi.updateProfile(data),
    onSuccess: (data) => {
      updateUser(data);
      queryClient.setQueryData(authKeys.user(), data);
    },
  });
}

/**
 * Hook to fetch all users (for dropdowns, assignments, etc.)
 */
export function useUsers(skip = 0, limit = 100) {
  return useQuery({
    queryKey: authKeys.users(skip, limit),
    queryFn: () => authApi.listUsers(skip, limit),
    staleTime: 10 * 60 * 1000, // 10 minutes
  });
}
