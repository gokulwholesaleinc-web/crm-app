/**
 * Admin Dashboard API
 */

import { apiClient } from './client';
import type {
  AdminUser,
  AdminUserUpdate,
  AssignRoleRequest,
  SystemStats,
  TeamMemberOverview,
  ActivityFeedEntry,
} from '../types';

const ADMIN_BASE = '/api/admin';

export const getAdminUsers = async (): Promise<AdminUser[]> => {
  const response = await apiClient.get<AdminUser[]>(`${ADMIN_BASE}/users`);
  return response.data;
};

export const updateAdminUser = async (
  userId: number,
  data: AdminUserUpdate
): Promise<AdminUser> => {
  const response = await apiClient.patch<AdminUser>(
    `${ADMIN_BASE}/users/${userId}`,
    data
  );
  return response.data;
};

export const deactivateUser = async (userId: number): Promise<{ detail: string }> => {
  const response = await apiClient.delete<{ detail: string }>(
    `${ADMIN_BASE}/users/${userId}`
  );
  return response.data;
};

export const getSystemStats = async (): Promise<SystemStats> => {
  const response = await apiClient.get<SystemStats>(`${ADMIN_BASE}/stats`);
  return response.data;
};

export const getTeamOverview = async (): Promise<TeamMemberOverview[]> => {
  const response = await apiClient.get<TeamMemberOverview[]>(
    `${ADMIN_BASE}/team-overview`
  );
  return response.data;
};

export const getActivityFeed = async (
  limit = 50
): Promise<ActivityFeedEntry[]> => {
  const response = await apiClient.get<ActivityFeedEntry[]>(
    `${ADMIN_BASE}/activity-feed`,
    { params: { limit } }
  );
  return response.data;
};

export const assignUserRole = async (
  userId: number,
  data: AssignRoleRequest
): Promise<AdminUser> => {
  const response = await apiClient.post<AdminUser>(
    `${ADMIN_BASE}/users/${userId}/assign-role`,
    data
  );
  return response.data;
};

export const adminApi = {
  getAdminUsers,
  updateAdminUser,
  deactivateUser,
  getSystemStats,
  getTeamOverview,
  getActivityFeed,
  assignUserRole,
};

export default adminApi;
