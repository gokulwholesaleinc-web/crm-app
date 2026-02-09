/**
 * Roles API - RBAC role management endpoints
 */

import { apiClient } from './client';

export interface Role {
  id: number;
  name: string;
  description: string | null;
  permissions: Record<string, string[]>;
  created_at: string;
  updated_at: string;
}

export interface UserRoleAssign {
  user_id: number;
  role_id: number;
}

export interface UserRoleResponse {
  id: number;
  user_id: number;
  role_id: number;
  role: Role;
  created_at: string;
}

export interface MyPermissions {
  role: string;
  permissions: Record<string, string[]>;
}

export const rolesApi = {
  list: () => apiClient.get<Role[]>('/api/roles').then((r) => r.data),

  getById: (id: number) =>
    apiClient.get<Role>(`/api/roles/${id}`).then((r) => r.data),

  create: (data: { name: string; description?: string; permissions?: Record<string, string[]> }) =>
    apiClient.post<Role>('/api/roles', data).then((r) => r.data),

  update: (id: number, data: { name?: string; description?: string; permissions?: Record<string, string[]> }) =>
    apiClient.patch<Role>(`/api/roles/${id}`, data).then((r) => r.data),

  delete: (id: number) => apiClient.delete(`/api/roles/${id}`),

  assign: (data: UserRoleAssign) =>
    apiClient.post<UserRoleResponse>('/api/roles/assign', data).then((r) => r.data),

  getUserRole: (userId: number) =>
    apiClient.get<Role>(`/api/roles/user/${userId}`).then((r) => r.data),

  getMyPermissions: () =>
    apiClient.get<MyPermissions>('/api/roles/me/permissions').then((r) => r.data),
};
