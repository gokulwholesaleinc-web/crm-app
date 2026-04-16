import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import { Spinner } from '../../components/ui/Spinner';
import { Button } from '../../components/ui/Button';
import { showSuccess } from '../../utils/toast';
import { calendarCallback, metaCallback, gmailCallback } from '../../api/integrations';
import { useAuthStore } from '../../store/authStore';

type CallbackStatus = 'pending' | 'error';

interface IntegrationInfo {
  label: string;
  settingsPath: string;
}

function resolveIntegration(pathname: string): IntegrationInfo | null {
  if (pathname.includes('google-calendar')) {
    return { label: 'Google Calendar', settingsPath: '/settings' };
  }
  if (pathname.includes('meta')) {
    return { label: 'Meta', settingsPath: '/settings' };
  }
  if (pathname.includes('gmail')) {
    return { label: 'Gmail', settingsPath: '/settings' };
  }
  return null;
}

function OAuthCallbackPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const processed = useRef(false);
  const [status, setStatus] = useState<CallbackStatus>('pending');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const integration = resolveIntegration(location.pathname);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;

    // Unauthenticated landing on the callback URL should bounce to /login
    // rather than show a spinner forever. After login we'll redirect back
    // to the settings integrations page.
    if (!isAuthenticated) {
      navigate('/login', {
        replace: true,
        state: { from: { pathname: '/settings' } },
      });
      return;
    }

    const code = searchParams.get('code');

    // Strip the OAuth `code` and `state` from the URL so they don't sit in
    // browser history or get accidentally shared. The token exchange is
    // server-side; the code is single-use, but leaving it in the address
    // bar is still low-value information disclosure.
    if (code) {
      window.history.replaceState(
        {},
        '',
        window.location.pathname
      );
    }

    if (!code) {
      setStatus('error');
      setErrorMessage('The authorization code is missing from the callback URL.');
      return;
    }

    if (!integration) {
      setStatus('error');
      setErrorMessage('Unknown integration callback.');
      return;
    }

    (async () => {
      try {
        if (integration.label === 'Google Calendar') {
          const redirectUri =
            window.location.origin + '/settings/integrations/google-calendar/callback';
          await calendarCallback(code, redirectUri);
        } else if (integration.label === 'Meta') {
          const redirectUri =
            window.location.origin + '/settings/integrations/meta/callback';
          await metaCallback(code, redirectUri);
        } else if (integration.label === 'Gmail') {
          const state = searchParams.get('state') ?? '';
          await gmailCallback(code, state);
        }
        showSuccess(`${integration.label} connected successfully`);
        navigate(integration.settingsPath, { replace: true });
      } catch (err) {
        const detail =
          (typeof err === 'object' && err !== null && 'response' in err
            ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
            : null) ||
          (err instanceof Error ? err.message : null) ||
          `Failed to connect ${integration.label}. Please try again.`;
        setStatus('error');
        setErrorMessage(detail);
      }
    })();
  }, [searchParams, location.pathname, navigate, isAuthenticated, integration]);

  if (status === 'error') {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <div className="max-w-md text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
            <ExclamationTriangleIcon
              className="h-6 w-6 text-red-600 dark:text-red-400"
              aria-hidden="true"
            />
          </div>
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Connection Failed
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-6" role="alert">
            {errorMessage}
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link to={integration?.settingsPath ?? '/settings'}>
              <Button variant="primary">Return to Settings</Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center" role="status" aria-live="polite">
        <Spinner size="lg" className="mx-auto mb-4 text-blue-600" />
        <p className="text-gray-600 dark:text-gray-300">
          Connecting to {integration?.label ?? 'integration'}...
        </p>
      </div>
    </div>
  );
}

export default OAuthCallbackPage;
