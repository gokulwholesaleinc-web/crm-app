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

const BASE_URL = import.meta.env.VITE_API_URL || '';

const TOKEN_KEY = 'crm_access_token';
const TENANT_SLUG_KEY = 'crm_tenant_slug:v1';

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
    // withCredentials is required so the HttpOnly Google OAuth state
    // cookie set by /api/auth/google/authorize flows back to /callback.
    // Backend CORS must be configured with allow_credentials=True and a
    // concrete origin (no "*") for this to work in prod.
    withCredentials: true,
  });

  client.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      const token = getToken();
      if (token && config.headers) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      const slug = localStorage.getItem(TENANT_SLUG_KEY);
      if (slug && config.headers) {
        config.headers['X-Tenant-Slug'] = slug;
      }
      // Let Axios set multipart/form-data with boundary for file uploads
      if (config.data instanceof FormData && config.headers) {
        delete config.headers['Content-Type'];
      }
      return config;
    },
    (error: AxiosError) => {
      return Promise.reject(error);
    }
  );

  client.interceptors.response.use(
    (response: AxiosResponse) => {
      return response;
    },
    (error: AxiosError<ApiError>) => {
      if (error.response?.status === 401) {
        clearToken();
        window.dispatchEvent(new CustomEvent('auth:unauthorized'));
      }

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

export const apiClient = createApiClient();

export default apiClient;
