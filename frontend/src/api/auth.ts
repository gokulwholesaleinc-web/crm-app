/**
 * Authentication API
 */

import { apiClient } from './client';
import { useAuthStore } from '../store/authStore';
import type {
  User,
  UserUpdate,
  Token,
} from '../types';

const AUTH_BASE = '/api/auth';

export const getMe = async (): Promise<User> => {
  const response = await apiClient.get<User>(`${AUTH_BASE}/me`);
  return response.data;
};

export const updateProfile = async (userData: UserUpdate): Promise<User> => {
  const response = await apiClient.patch<User>(`${AUTH_BASE}/me`, userData);
  return response.data;
};

export const listUsers = async (skip = 0, limit = 100): Promise<User[]> => {
  const response = await apiClient.get<User[]>(`${AUTH_BASE}/users`, {
    params: { skip, limit },
  });
  return response.data;
};

export const logout = (): void => {
  useAuthStore.getState().logout();
  window.dispatchEvent(new CustomEvent('auth:logout'));
};

/**
 * Start the Google OAuth2 sign-in flow. Returns the auth URL + state nonce
 * that the frontend should redirect the browser to. Sign-in is distinct from
 * the calendar integration and only requests openid/email/profile scopes.
 */
export const googleAuthorize = async (
  redirectUri: string
): Promise<{ auth_url: string; state: string }> => {
  const response = await apiClient.post<{ auth_url: string; state: string }>(
    `${AUTH_BASE}/google/authorize`,
    { redirect_uri: redirectUri }
  );
  return response.data;
};

/**
 * Exchange a Google authorization code for a CRM JWT + tenant list.
 * Stores the token on success.
 */
export const googleCallback = async (
  code: string,
  redirectUri: string,
  state?: string | null
): Promise<Token> => {
  const response = await apiClient.post<Token>(`${AUTH_BASE}/google/callback`, {
    code,
    redirect_uri: redirectUri,
    state: state ?? undefined,
  });
  useAuthStore.getState().setToken(response.data.access_token);
  return response.data;
};

// Export all auth functions
export const authApi = {
  getMe,
  updateProfile,
  listUsers,
  logout,
  googleAuthorize,
  googleCallback,
};

