/**
 * Authentication hooks using TanStack Query
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { authApi } from '../api/auth';
import { useAuthStore, User as StoreUser } from '../store/authStore';
import type { User, UserUpdate } from '../types';

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

export function useUser() {
  const { token } = useAuthStore();

  return useQuery({
    queryKey: authKeys.user(),
    queryFn: () => authApi.getMe(),
    enabled: !!token,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });
}

export function useLogout() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async () => {
      authApi.logout();
    },
    onSuccess: () => {
      queryClient.clear();
    },
  });
}

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

export function useUsers(skip = 0, limit = 100, options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: authKeys.users(skip, limit),
    queryFn: () => authApi.listUsers(skip, limit),
    staleTime: 10 * 60 * 1000,
    ...options,
  });
}
