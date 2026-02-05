/**
 * Axios HTTP Client with authentication interceptors
 */

import axios, {
  AxiosInstance,
  AxiosError,
  InternalAxiosRequestConfig,
  AxiosResponse,
} from 'axios';
import type { ApiError } from '../types';

// Get base URL from environment variable
// Individual API modules include /api prefix, so base URL should be empty for proxy setup
// or the backend root URL (e.g., http://localhost:8000) for direct access
const BASE_URL = import.meta.env.VITE_API_URL || '';

// Token storage key
const TOKEN_KEY = 'crm_access_token';

/**
 * Create configured Axios instance
 */
const createApiClient = (): AxiosInstance => {
  const client = axios.create({
    baseURL: BASE_URL,
    headers: {
      'Content-Type': 'application/json',
    },
    timeout: 30000,
  });

  // Request interceptor - add auth token
  client.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      const token = getToken();
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    },
    (error: AxiosError) => {
      return Promise.reject(error);
    }
  );

  // Response interceptor - handle errors
  client.interceptors.response.use(
    (response: AxiosResponse) => {
      return response;
    },
    (error: AxiosError<ApiError>) => {
      // Handle 401 Unauthorized - clear token and redirect to login
      if (error.response?.status === 401) {
        clearToken();
        // Optionally dispatch an event or redirect
        window.dispatchEvent(new CustomEvent('auth:unauthorized'));
      }

      // Transform error for consistent handling
      const apiError: ApiError = {
        detail: error.response?.data?.detail || error.message || 'An error occurred',
        status_code: error.response?.status,
      };

      return Promise.reject(apiError);
    }
  );

  return client;
};

/**
 * Get stored authentication token
 */
export const getToken = (): string | null => {
  return localStorage.getItem(TOKEN_KEY);
};

/**
 * Store authentication token
 */
export const setToken = (token: string): void => {
  localStorage.setItem(TOKEN_KEY, token);
};

/**
 * Clear authentication token
 */
export const clearToken = (): void => {
  localStorage.removeItem(TOKEN_KEY);
};

/**
 * Check if user is authenticated
 */
export const isAuthenticated = (): boolean => {
  return !!getToken();
};

// Create and export the API client instance
export const apiClient = createApiClient();

// Export default for convenience
export default apiClient;
