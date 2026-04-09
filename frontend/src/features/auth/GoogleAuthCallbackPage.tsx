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

function GoogleAuthCallbackPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const processed = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const { login: storeLogin } = useAuthStore();

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;

    const code = searchParams.get('code');
    const returnedState = searchParams.get('state');
    const errorParam = searchParams.get('error');

    if (errorParam) {
      setError(`Google returned an error: ${errorParam}`);
      return;
    }
    if (!code) {
      setError('Missing authorization code');
      return;
    }

    // State verification happens server-side now: /authorize sets an
    // HttpOnly cookie, /callback compares it against the `state` we
    // forward from Google's query string. Nothing for this page to
    // check client-side.
    if (!returnedState) {
      setError('Sign-in state mismatch. Please start again from the sign-in page.');
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
        const detail =
          (typeof err === 'object' && err !== null && 'detail' in err
            ? String((err as { detail: unknown }).detail)
            : null) ||
          (err instanceof Error ? err.message : null) ||
          'Failed to sign in with Google.';
        setError(detail);
      }
    })();
  }, [searchParams, navigate, storeLogin]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-gray-50 dark:bg-gray-900 px-4">
      <div className="text-center max-w-md">
        {error ? (
          <>
            <div
              role="alert"
              aria-live="polite"
              className="rounded-md bg-red-50 dark:bg-red-900/20 p-4 text-sm text-red-800 dark:text-red-300"
            >
              {error}
            </div>
            <button
              type="button"
              onClick={() => navigate('/login', { replace: true })}
              className="mt-4 text-sm font-medium text-primary-600 hover:text-primary-500"
            >
              Back to sign in
            </button>
          </>
        ) : (
          <>
            <Spinner size="lg" className="mx-auto mb-4 text-blue-600" />
            <p className="text-gray-600 dark:text-gray-300">Finishing Google sign-in...</p>
          </>
        )}
      </div>
    </div>
  );
}

export default GoogleAuthCallbackPage;
