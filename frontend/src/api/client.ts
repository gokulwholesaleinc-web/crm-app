/**
 * Axios HTTP Client with authentication interceptors.
 *
 * The access token is owned by the zustand auth store (see store/authStore.ts).
 * This module exposes `registerAuthTokenGetter` so the store can inject a
 * getter without creating a circular import between the two modules.
 */

import axios, {
  AxiosInstance,
  AxiosError,
  InternalAxiosRequestConfig,
  AxiosResponse,
} from 'axios';
import type { ApiError } from '../types';

const BASE_URL = import.meta.env.VITE_API_URL || '';

const TENANT_SLUG_KEY = 'crm_tenant_slug:v1';

// Token getter injected by the auth store. Defaults to returning null so the
// client is safe to import before the store has initialized.
let tokenGetter: () => string | null = () => null;

/**
 * Register a function the axios request interceptor should call to read the
 * current access token. The auth store calls this at module init.
 */
export const registerAuthTokenGetter = (getter: () => string | null): void => {
  tokenGetter = getter;
};

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

  client.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
      const token = tokenGetter();
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
 * Read the current authentication token. Thin wrapper around the getter the
 * auth store registered — used by a handful of raw-fetch call sites that need
 * to attach a bearer header manually (file downloads, etc.).
 */
export const getToken = (): string | null => {
  return tokenGetter();
};

export const apiClient = createApiClient();

export default apiClient;
