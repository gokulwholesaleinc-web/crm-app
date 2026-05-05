import { Link } from 'react-router-dom';
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline';
import { useGmailStatus } from '../../hooks/useGmailStatus';

/**
 * Renders a "Reconnect Gmail" warning when the current user's Gmail
 * connection has been revoked / their refresh token expired. Hidden
 * when Gmail is healthy, never connected, or status is loading.
 *
 * Drop into anywhere email-thread state is shown (contact / lead /
 * company Emails tab). The Settings page has its own dedicated UI.
 */
export function GmailReconnectBanner() {
  const { data: status } = useGmailStatus();

  if (status?.state !== 'needs_reconnect') return null;

  const lastSynced = status.last_synced_at
    ? new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(
        new Date(status.last_synced_at),
      )
    : null;

  return (
    <div
      role="alert"
      aria-live="polite"
      className="mb-4 rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 p-3 sm:p-4"
    >
      <div className="flex items-start gap-3">
        <ExclamationTriangleIcon className="h-5 w-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
        <div className="flex-1 min-w-0 text-sm">
          <p className="font-medium text-amber-900 dark:text-amber-100">
            Gmail sync paused — reconnect required
          </p>
          <p className="mt-1 text-amber-800 dark:text-amber-200">
            Google revoked our access (this happens automatically every ~7 days for unverified
            apps). New emails won't appear here, and you can't send through Gmail until you
            reconnect.{lastSynced && <> Last successful sync: <strong>{lastSynced}</strong>.</>}
          </p>
          <Link
            to="/settings?section=integrations"
            className="mt-2 inline-flex items-center gap-1 font-medium text-amber-900 dark:text-amber-100 underline hover:no-underline"
          >
            Go to Settings → Integrations to reconnect
          </Link>
        </div>
      </div>
    </div>
  );
}

export default GmailReconnectBanner;
