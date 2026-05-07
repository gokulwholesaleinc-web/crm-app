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
    // withCredentials is required so the HttpOnly Google OAuth state
    // cookie set by /api/auth/google/authorize flows back to /callback.
    // Backend CORS must be configured with allow_credentials=True and a
    // concrete origin (no "*") for this to work in prod.
    withCredentials: true,
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
    async (error: AxiosError<ApiError>) => {
      if (error.response?.status === 401) {
        window.dispatchEvent(new CustomEvent('auth:unauthorized'));
      }

      // When the request used ``responseType: 'blob'``, axios deserializes
      // EVERY response (including error responses) as a Blob — so
      // ``error.response.data.detail`` is undefined and the user sees a
      // generic "Request failed with status code 403" instead of the
      // backend's actual JSON detail. Re-parse the blob body as JSON
      // before flattening so blob downloads (proposal/quote PDFs,
      // attachments, report exports) surface the real reason on
      // failure. Falls back to .text() if the body isn't JSON.
      let detailFromBlob: string | undefined;
      const data = error.response?.data;
      if (data instanceof Blob) {
        try {
          const text = await data.text();
          try {
            const parsed = JSON.parse(text) as { detail?: unknown };
            if (typeof parsed.detail === 'string' && parsed.detail.trim()) {
              detailFromBlob = parsed.detail.trim();
            } else if (Array.isArray(parsed.detail)) {
              // FastAPI 422 payload: detail is an array of {loc, msg, type}.
              // Joining the msgs is far more readable than a JSON.stringify
              // of the whole array (which is what users used to see in the
              // toast for blob-download validation failures).
              const msgs = parsed.detail
                .map((d) =>
                  typeof d === 'object' && d !== null && 'msg' in d
                    ? String((d as { msg: unknown }).msg)
                    : '',
                )
                .filter(Boolean);
              detailFromBlob = msgs.length ? msgs.join('; ') : JSON.stringify(parsed.detail);
            } else if (parsed.detail) {
              detailFromBlob = JSON.stringify(parsed.detail);
            }
          } catch {
            if (text.trim()) detailFromBlob = text.trim();
          }
        } catch (blobErr) {
          // Reading the blob body itself failed (already consumed,
          // network truncation). Falling through to axios's default
          // error.message would lose the cause; warn for the dev,
          // user still sees error.message in the toast.
          // eslint-disable-next-line no-console
          console.warn('[apiClient] failed to read error blob body:', blobErr);
        }
      }

      const responseDetail = !(data instanceof Blob)
        ? (data as ApiError | undefined)?.detail
        : undefined;

      const apiError: ApiError = {
        detail:
          detailFromBlob ||
          responseDetail ||
          error.message ||
          'An error occurred',
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

