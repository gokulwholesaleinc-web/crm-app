/**
 * Roles & Permissions API
 */

import { apiClient } from './client';
import type { Role, UserPermissions, UserRoleAssign } from '../types';

const ROLES_BASE = '/api/roles';

/**
 * List all roles
 */
export const listRoles = async (): Promise<Role[]> => {
  const response = await apiClient.get<Role[]>(ROLES_BASE);
  return response.data;
};

/**
 * Get a role by ID
 */
export const getRole = async (roleId: number): Promise<Role> => {
  const response = await apiClient.get<Role>(`${ROLES_BASE}/${roleId}`);
  return response.data;
};

/**
 * Create a new role (admin-only)
 */
export const createRole = async (data: Partial<Role>): Promise<Role> => {
  const response = await apiClient.post<Role>(ROLES_BASE, data);
  return response.data;
};

/**
 * Update a role (admin-only)
 */
export const updateRole = async (roleId: number, data: Partial<Role>): Promise<Role> => {
  const response = await apiClient.patch<Role>(`${ROLES_BASE}/${roleId}`, data);
  return response.data;
};

/**
 * Delete a role (admin-only)
 */
export const deleteRole = async (roleId: number): Promise<void> => {
  await apiClient.delete(`${ROLES_BASE}/${roleId}`);
};

/**
 * Assign a role to a user (admin-only)
 */
export const assignRole = async (data: UserRoleAssign): Promise<void> => {
  await apiClient.post(`${ROLES_BASE}/assign`, data);
};

/**
 * Get a user's role
 */
export const getUserRole = async (userId: number): Promise<Role> => {
  const response = await apiClient.get<Role>(`${ROLES_BASE}/user/${userId}`);
  return response.data;
};

/**
 * Get current user's permissions
 */
export const getMyPermissions = async (): Promise<UserPermissions> => {
  const response = await apiClient.get<UserPermissions>(`${ROLES_BASE}/me/permissions`);
  return response.data;
};

export const rolesApi = {
  listRoles,
  getRole,
  createRole,
  updateRole,
  deleteRole,
  assignRole,
  getUserRole,
  getMyPermissions,
};

export default rolesApi;
