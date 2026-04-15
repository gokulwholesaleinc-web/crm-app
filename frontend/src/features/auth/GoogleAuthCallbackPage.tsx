/**
 * Public Google OAuth callback page.
 *
 * Runs BEFORE the user is authenticated (not wrapped in PrivateRoute), so it
 * cannot rely on the auth store. Finishes the token exchange, persists the
 * JWT + tenant slug, then redirects to the dashboard.
 *
 * CSRF: the state nonce is stored server-side in an HttpOnly cookie set
 * by /api/auth/google/authorize. This page just forwards whatever state
 * Google echoed back; the server compares it to the cookie and rejects
 * mismatches. A victim lured directly to this URL has no cookie and
 * the callback will 400 out.
 */

import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Spinner } from '../../components/ui/Spinner';
import { authApi } from '../../api/auth';
import { setTenantSlugOnLogin } from '../../providers/TenantProvider';
import { useAuthStore } from '../../store/authStore';
import { GOOGLE_OAUTH_CALLBACK_PATH } from './GoogleSignInButton';

type CallbackState =
  | { kind: 'loading' }
  | { kind: 'pending' }
  | { kind: 'rejected' }
  | { kind: 'error'; message: string };

function GoogleAuthCallbackPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const processed = useRef(false);
  const [state, setState] = useState<CallbackState>({ kind: 'loading' });
  const { login: storeLogin } = useAuthStore();

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;

    const code = searchParams.get('code');
    const returnedState = searchParams.get('state');
    const errorParam = searchParams.get('error');

    if (errorParam) {
      setState({ kind: 'error', message: `Google returned an error: ${errorParam}` });
      return;
    }
    if (!code) {
      setState({ kind: 'error', message: 'Missing authorization code' });
      return;
    }

    // State verification happens server-side now: /authorize sets an
    // HttpOnly cookie, /callback compares it against the `state` we
    // forward from Google's query string. Nothing for this page to
    // check client-side.
    if (!returnedState) {
      setState({ kind: 'error', message: 'Sign-in state mismatch. Please start again from the sign-in page.' });
      return;
    }

    (async () => {
      try {
        const redirectUri = window.location.origin + GOOGLE_OAUTH_CALLBACK_PATH;
        const tokenResult = await authApi.googleCallback(code, redirectUri, returnedState);
        const user = await authApi.getMe();

        if (tokenResult.tenants && tokenResult.tenants.length > 0) {
          const primary =
            tokenResult.tenants.find((t) => t.is_primary) ?? tokenResult.tenants[0];
          if (primary) {
            setTenantSlugOnLogin(primary.tenant_slug);
          }
        }

        storeLogin(user, tokenResult.access_token);

        navigate('/', { replace: true });
      } catch (err: unknown) {
        // Check for structured 403 detail objects from the approval gate
        const detail =
          typeof err === 'object' && err !== null && 'detail' in err
            ? (err as { detail: unknown }).detail
            : null;

        if (typeof detail === 'object' && detail !== null) {
          const d = detail as Record<string, unknown>;
          if (d.pending_approval === true) {
            setState({ kind: 'pending' });
            return;
          }
          if (d.rejected === true) {
            setState({ kind: 'rejected' });
            return;
          }
        }

        const message =
          (typeof detail === 'string' ? detail : null) ||
          (err instanceof Error ? err.message : null) ||
          'Failed to sign in with Google.';
        setState({ kind: 'error', message });
      }
    })();
  }, [searchParams, navigate, storeLogin]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="text-center max-w-md">
        {state.kind === 'loading' && (
          <>
            <Spinner size="lg" className="mx-auto mb-4 text-blue-600" />
            <p className="text-gray-600 dark:text-gray-300">Finishing Google sign-in...</p>
          </>
        )}

        {state.kind === 'pending' && (
          <>
            <div
              role="alert"
              aria-live="polite"
              className="rounded-md bg-yellow-50 dark:bg-yellow-900/20 p-4 text-sm text-yellow-800 dark:text-yellow-300"
            >
              Your account is pending admin approval. You'll receive a notification when approved.
            </div>
            <button
              type="button"
              onClick={() => navigate('/login', { replace: true })}
              className="mt-4 text-sm font-medium text-primary-600 hover:text-primary-500"
            >
              Back to sign in
            </button>
          </>
        )}

        {state.kind === 'rejected' && (
          <>
            <div
              role="alert"
              aria-live="polite"
              className="rounded-md bg-red-50 dark:bg-red-900/20 p-4 text-sm text-red-800 dark:text-red-300"
            >
              Access denied. Contact an admin if this is a mistake.
            </div>
            <button
              type="button"
              onClick={() => navigate('/login', { replace: true })}
              className="mt-4 text-sm font-medium text-primary-600 hover:text-primary-500"
            >
              Back to sign in
            </button>
          </>
        )}

        {state.kind === 'error' && (
          <>
            <div
              role="alert"
              aria-live="polite"
              className="rounded-md bg-red-50 dark:bg-red-900/20 p-4 text-sm text-red-800 dark:text-red-300"
            >
              {state.message}
            </div>
            <button
              type="button"
              onClick={() => navigate('/login', { replace: true })}
              className="mt-4 text-sm font-medium text-primary-600 hover:text-primary-500"
            >
              Back to sign in
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default GoogleAuthCallbackPage;
