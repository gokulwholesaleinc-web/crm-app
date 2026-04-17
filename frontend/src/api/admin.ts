/**
 * Admin Dashboard API
 */

import { apiClient } from './client';
import type { RoleName } from '../store/authStore';
import type {
  AdminUser,
  AdminUserUpdate,
  AssignRoleRequest,
  SystemStats,
  TeamMemberOverview,
  ActivityFeedEntry,
  PendingUser,
  RejectedEmail,
  User,
} from '../types';

export type ApprovalRole = Exclude<RoleName, 'viewer'>;

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

export const deleteUserPermanently = async (userId: number): Promise<{ detail: string }> => {
  const response = await apiClient.delete<{ detail: string }>(
    `${ADMIN_BASE}/users/${userId}/permanent`
  );
  return response.data;
};

export const getPendingUsers = async (): Promise<PendingUser[]> => {
  const response = await apiClient.get<PendingUser[]>(`${ADMIN_BASE}/users/pending`);
  return response.data;
};

export const approveUser = async (
  id: number,
  role: ApprovalRole
): Promise<User> => {
  const response = await apiClient.patch<User>(`${ADMIN_BASE}/users/${id}/approve`, { role });
  return response.data;
};

export const rejectUser = async (
  id: number,
  reason?: string
): Promise<{ rejected_email_id: number }> => {
  const response = await apiClient.post<{ rejected_email_id: number }>(
    `${ADMIN_BASE}/users/${id}/reject`,
    { reason }
  );
  return response.data;
};

export const getRejectedEmails = async (): Promise<RejectedEmail[]> => {
  const response = await apiClient.get<RejectedEmail[]>(`${ADMIN_BASE}/rejected-emails`);
  return response.data;
};

export const unblockRejectedEmail = async (id: number): Promise<void> => {
  await apiClient.delete(`${ADMIN_BASE}/rejected-emails/${id}`);
};

export const adminApi = {
  getAdminUsers,
  updateAdminUser,
  deactivateUser,
  deleteUserPermanently,
  getSystemStats,
  getTeamOverview,
  getActivityFeed,
  assignUserRole,
  getPendingUsers,
  approveUser,
  rejectUser,
  getRejectedEmails,
  unblockRejectedEmail,
};

