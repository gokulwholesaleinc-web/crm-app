/**
 * Authentication API
 */

import { apiClient, setToken, clearToken } from './client';
import type {
  User,
  UserCreate,
  UserUpdate,
  LoginRequest,
  Token,
} from '../types';

const AUTH_BASE = '/api/auth';

/**
 * Register a new user
 */
export const register = async (userData: UserCreate): Promise<User> => {
  const response = await apiClient.post<User>(`${AUTH_BASE}/register`, userData);
  return response.data;
};

/**
 * Login with email and password (JSON body)
 */
export const login = async (credentials: LoginRequest): Promise<Token> => {
  const response = await apiClient.post<Token>(`${AUTH_BASE}/login/json`, credentials);
  // Store token after successful login
  setToken(response.data.access_token);
  return response.data;
};

/**
 * Login with form data (OAuth2 compatible)
 */
export const loginWithForm = async (email: string, password: string): Promise<Token> => {
  const params = new URLSearchParams();
  params.append('username', email);
  params.append('password', password);

  const response = await apiClient.post<Token>(`${AUTH_BASE}/login`, params, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
  });
  // Store token after successful login
  setToken(response.data.access_token);
  return response.data;
};

/**
 * Get current user profile
 */
export const getMe = async (): Promise<User> => {
  const response = await apiClient.get<User>(`${AUTH_BASE}/me`);
  return response.data;
};

/**
 * Update current user profile
 */
export const updateProfile = async (userData: UserUpdate): Promise<User> => {
  const response = await apiClient.patch<User>(`${AUTH_BASE}/me`, userData);
  return response.data;
};

/**
 * List all users (for dropdowns, assignments, etc.)
 */
export const listUsers = async (skip = 0, limit = 100): Promise<User[]> => {
  const response = await apiClient.get<User[]>(`${AUTH_BASE}/users`, {
    params: { skip, limit },
  });
  return response.data;
};

/**
 * Logout - clear stored token
 */
export const logout = (): void => {
  clearToken();
  window.dispatchEvent(new CustomEvent('auth:logout'));
};

// Export all auth functions
export const authApi = {
  register,
  login,
  loginWithForm,
  getMe,
  updateProfile,
  listUsers,
  logout,
};

export default authApi;
