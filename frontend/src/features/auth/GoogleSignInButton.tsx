/**
 * "Continue with Google" button shared by the login and register pages.
 *
 * Kicks off the OAuth2 flow: POSTs to /api/auth/google/authorize, stores the
 * CSRF state in sessionStorage, and redirects the browser to Google. The
 * public /auth/google/callback page finishes the flow.
 */

import { useState } from 'react';
import { authApi } from '../../api/auth';

const STATE_KEY = 'google-oauth-state:v1';
const CALLBACK_PATH = '/auth/google/callback';

interface GoogleSignInButtonProps {
  label?: string;
  disabled?: boolean;
  onError?: (message: string) => void;
}

function GoogleSignInButton({
  label = 'Continue with Google',
  disabled,
  onError,
}: GoogleSignInButtonProps) {
  const [isLoading, setIsLoading] = useState(false);

  const handleClick = async () => {
    setIsLoading(true);
    try {
      const redirectUri = window.location.origin + CALLBACK_PATH;
      const { auth_url, state } = await authApi.googleAuthorize(redirectUri);
      try {
        sessionStorage.setItem(STATE_KEY, state);
      } catch {
        /* storage blocked — proceed without state verification */
      }
      window.location.href = auth_url;
    } catch (err: unknown) {
      const detail =
        (typeof err === 'object' && err !== null && 'detail' in err
          ? String((err as { detail: unknown }).detail)
          : null) ||
        (err instanceof Error ? err.message : null) ||
        'Google sign-in is unavailable right now.';
      onError?.(detail);
      setIsLoading(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={disabled || isLoading}
      aria-label={label}
      className="w-full inline-flex items-center justify-center gap-2 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-4 py-2.5 sm:py-2 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
    >
      <svg aria-hidden="true" className="h-5 w-5" viewBox="0 0 24 24">
        <path
          fill="#4285F4"
          d="M23.49 12.27c0-.79-.07-1.54-.19-2.27H12v4.51h6.47c-.28 1.4-1.11 2.6-2.35 3.4v2.8h3.78c2.22-2.05 3.49-5.07 3.49-8.44z"
        />
        <path
          fill="#34A853"
          d="M12 24c3.24 0 5.95-1.08 7.93-2.9l-3.78-2.8c-1.06.71-2.42 1.14-4.15 1.14-3.19 0-5.9-2.16-6.86-5.05H1.22v3.17C3.2 21.3 7.27 24 12 24z"
        />
        <path
          fill="#FBBC05"
          d="M5.14 14.38c-.25-.71-.39-1.47-.39-2.38s.14-1.67.39-2.38V6.45H1.22C.44 8.05 0 9.97 0 12s.44 3.95 1.22 5.55l3.92-3.17z"
        />
        <path
          fill="#EA4335"
          d="M12 4.77c1.76 0 3.34.61 4.58 1.8l3.35-3.35C17.95 1.2 15.24 0 12 0 7.27 0 3.2 2.7 1.22 6.45l3.92 3.17C6.1 6.93 8.81 4.77 12 4.77z"
        />
      </svg>
      <span>{isLoading ? 'Redirecting...' : label}</span>
    </button>
  );
}

/**
 * Horizontal "Or" divider used above the Google button on login/register
 * pages. Kept next to the button so both auth pages share one implementation.
 */
function AuthDivider({ label = 'Or' }: { label?: string }) {
  return (
    <div className="relative" aria-hidden="true">
      <div className="absolute inset-0 flex items-center">
        <div className="w-full border-t border-gray-300 dark:border-gray-600" />
      </div>
      <div className="relative flex justify-center text-xs">
        <span className="bg-gray-50 dark:bg-gray-900 px-2 text-gray-500 dark:text-gray-400 uppercase tracking-wider">
          {label}
        </span>
      </div>
    </div>
  );
}

export default GoogleSignInButton;
export {
  STATE_KEY as GOOGLE_OAUTH_STATE_KEY,
  CALLBACK_PATH as GOOGLE_OAUTH_CALLBACK_PATH,
  AuthDivider,
};
