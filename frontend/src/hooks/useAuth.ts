/**
 * Authentication hooks using TanStack Query
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { authApi } from '../api/auth';
import { useAuthStore, User as StoreUser } from '../store/authStore';
import type { User, UserCreate, UserUpdate, LoginRequest } from '../types';

// Helper to convert types/index.ts User to store User type
// The difference is phone field: types has string | null | undefined, store has string | undefined
function toStoreUser(user: User): StoreUser {
  return {
    ...user,
    phone: user.phone ?? undefined,
    job_title: user.job_title ?? undefined,
    avatar_url: user.avatar_url ?? undefined,
    last_login: user.last_login ?? undefined,
  };
}

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
  const { token } = useAuthStore();

  return useQuery({
    queryKey: authKeys.user(),
    queryFn: () => authApi.getMe(),
    enabled: !!token,
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
      // Clear all cached data from previous session before loading new user data
      queryClient.clear();

      // Token is already stored by authApi.login
      useAuthStore.getState().setToken(data.access_token);

      // Fetch user profile
      const user = await authApi.getMe();
      storeLogin(toStoreUser(user), data.access_token);
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
      queryClient.clear();
      useAuthStore.getState().setToken(data.access_token);

      // Fetch user profile
      const user = await authApi.getMe();
      storeLogin(toStoreUser(user), data.access_token);
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
      updateUser(toStoreUser(data));
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
