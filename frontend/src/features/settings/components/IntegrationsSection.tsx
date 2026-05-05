/**
 * Integrations section for Settings page.
 * Shows Google Calendar and Meta (Facebook/Instagram) connection status
 * with connect/disconnect/sync actions.
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import { Spinner } from '../../../components/ui/Spinner';
import { ConfirmDialog } from '../../../components/ui/ConfirmDialog';
import {
  getCalendarAuthUrl,
  disconnectCalendar,
  getMetaStatus,
  getMetaAuthUrl,
  disconnectMeta,
  getGmailStatus,
  getGmailAuthUrl,
  disconnectGmail,
  syncGmail,
} from '../../../api/integrations';
import type { MetaConnectionStatus, GmailStatus } from '../../../api/integrations';
import {
  CalendarDaysIcon,
  ArrowPathIcon,
  LinkIcon,
  XMarkIcon,
  CheckCircleIcon,
  EnvelopeIcon,
} from '@heroicons/react/24/outline';
import toast from 'react-hot-toast';
import { useGoogleCalendarSync } from '../../../hooks/useGoogleCalendarSync';

function ConnectionBadge({ connected }: { connected: boolean }) {
  return connected ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-green-100 dark:bg-green-900/30 px-2.5 py-0.5 text-xs font-medium text-green-700 dark:text-green-400">
      <CheckCircleIcon className="h-3.5 w-3.5" aria-hidden="true" />
      Connected
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 dark:bg-gray-700 px-2.5 py-0.5 text-xs font-medium text-gray-600 dark:text-gray-400">
      Not connected
    </span>
  );
}

function GoogleCalendarCard({ onRequestDisconnect }: { onRequestDisconnect: () => void }) {
  const { status, connected, isLoadingStatus, sync, isSyncing } = useGoogleCalendarSync();

  const connectMutation = useMutation({
    mutationFn: () => {
      const redirectUri = `${window.location.origin}/settings/integrations/google-calendar/callback`;
      return getCalendarAuthUrl(redirectUri);
    },
    onSuccess: (data) => {
      window.location.href = data.auth_url;
    },
    onError: () => {
      toast.error('Google Calendar integration is not configured. Contact your administrator.');
    },
  });

  if (isLoadingStatus) {
    return <Spinner size="sm" />;
  }

  return (
    <div className="flex items-start gap-4 py-4 first:pt-0 last:pb-0">
      <div className="flex-shrink-0">
        <div className="h-10 w-10 rounded-lg bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
          <CalendarDaysIcon className="h-5 w-5 text-blue-600 dark:text-blue-400" aria-hidden="true" />
        </div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Google Calendar</p>
          <ConnectionBadge connected={connected} />
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          {connected
            ? `Calendar: ${status?.calendar_id ?? 'primary'} · ${status?.synced_events_count ?? 0} synced events`
            : 'Sync activities and meetings with Google Calendar'}
        </p>
        {connected && status?.last_synced_at && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            Last synced: {new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(status.last_synced_at))}
          </p>
        )}
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        {connected ? (
          <>
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<ArrowPathIcon className="h-4 w-4" />}
              onClick={sync}
              disabled={isSyncing}
              aria-label="Sync Google Calendar"
            >
              Sync
            </Button>
            <Button
              variant="danger"
              size="sm"
              leftIcon={<XMarkIcon className="h-4 w-4" />}
              onClick={onRequestDisconnect}
              aria-label="Disconnect Google Calendar"
            >
              Disconnect
            </Button>
          </>
        ) : (
          <Button
            variant="primary"
            size="sm"
            leftIcon={<LinkIcon className="h-4 w-4" />}
            onClick={() => connectMutation.mutate()}
            disabled={connectMutation.isPending}
            aria-label="Connect Google Calendar"
          >
            Connect
          </Button>
        )}
      </div>
    </div>
  );
}

function MetaCard({ onRequestDisconnect }: { onRequestDisconnect: () => void }) {
  const { data: status, isLoading } = useQuery<MetaConnectionStatus>({
    queryKey: ['integrations', 'meta', 'status'],
    queryFn: getMetaStatus,
  });

  const connectMutation = useMutation({
    mutationFn: () => {
      const redirectUri = `${window.location.origin}/settings/integrations/meta/callback`;
      return getMetaAuthUrl(redirectUri);
    },
    onSuccess: (data) => {
      window.location.href = data.auth_url;
    },
    onError: () => {
      toast.error('Meta integration is not configured. Contact your administrator.');
    },
  });

  if (isLoading) {
    return <Spinner size="sm" />;
  }

  const connected = status?.connected ?? false;
  const pages = status?.pages ?? [];

  return (
    <div className="flex items-start gap-4 py-4 first:pt-0 last:pb-0">
      <div className="flex-shrink-0">
        <div className="h-10 w-10 rounded-lg bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center">
          <svg className="h-5 w-5 text-indigo-600 dark:text-indigo-400" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path d="M12 2.04c-5.5 0-10 4.49-10 10.02 0 5 3.66 9.15 8.44 9.9v-7H7.9v-2.9h2.54V9.85c0-2.52 1.49-3.93 3.78-3.93 1.09 0 2.23.19 2.23.19v2.47h-1.26c-1.24 0-1.63.77-1.63 1.56v1.88h2.78l-.45 2.9h-2.33v7a10 10 0 008.44-9.9c0-5.53-4.5-10.02-10-10.02z" />
          </svg>
        </div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Meta (Facebook & Instagram)</p>
          <ConnectionBadge connected={connected} />
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          {connected
            ? `${pages.length} page${pages.length !== 1 ? 's' : ''} linked · Lead capture & social sync`
            : 'Connect Facebook pages, Instagram, and Lead Ads'}
        </p>
        {connected && status?.token_expiry && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            Token expires: {new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(new Date(status.token_expiry))}
          </p>
        )}
        {connected && pages.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {pages.map((page) => (
              <span key={page.id} className="inline-flex items-center rounded bg-gray-100 dark:bg-gray-700 px-2 py-0.5 text-xs text-gray-700 dark:text-gray-300">
                {page.name}
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        {connected ? (
          <Button
            variant="danger"
            size="sm"
            leftIcon={<XMarkIcon className="h-4 w-4" />}
            onClick={onRequestDisconnect}
            aria-label="Disconnect Meta"
          >
            Disconnect
          </Button>
        ) : (
          <Button
            variant="primary"
            size="sm"
            leftIcon={<LinkIcon className="h-4 w-4" />}
            onClick={() => connectMutation.mutate()}
            disabled={connectMutation.isPending}
            aria-label="Connect Meta"
          >
            Connect
          </Button>
        )}
      </div>
    </div>
  );
}

function GmailCard({ onRequestDisconnect }: { onRequestDisconnect: () => void }) {
  const queryClient = useQueryClient();

  const { data: status, isLoading } = useQuery<GmailStatus>({
    queryKey: ['integrations', 'gmail', 'status'],
    queryFn: getGmailStatus,
  });

  const connected = status?.connected ?? false;
  const needsReconnect = status?.state === 'needs_reconnect';

  const connectMutation = useMutation({
    mutationFn: getGmailAuthUrl,
    onSuccess: (data) => {
      window.location.href = data.auth_url;
    },
    onError: () => {
      toast.error('Gmail integration is not configured. Contact your administrator.');
    },
  });

  const syncMutation = useMutation({
    mutationFn: syncGmail,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'gmail'] });
      toast.success('Gmail sync complete');
    },
    onError: () => {
      toast.error('Gmail sync failed');
    },
  });

  if (isLoading) {
    return <Spinner size="sm" />;
  }

  return (
    <div className="flex items-start gap-4 py-4 first:pt-0 last:pb-0">
      <div className="flex-shrink-0">
        <div className="h-10 w-10 rounded-lg bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
          <EnvelopeIcon className="h-5 w-5 text-red-600 dark:text-red-400" aria-hidden="true" />
        </div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Gmail</p>
          {needsReconnect ? (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 dark:bg-amber-900/40 text-amber-800 dark:text-amber-200">
              Reconnect required
            </span>
          ) : (
            <ConnectionBadge connected={connected} />
          )}
        </div>
        {needsReconnect ? (
          <p className="text-xs text-amber-700 dark:text-amber-300 mt-1">
            Google revoked our access — this typically happens automatically every 7 days for
            unverified apps. Click <strong>Reconnect</strong> to restore email sync. Outgoing email
            and contact thread sync are paused until you do.
          </p>
        ) : (
          <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
            {connected
              ? `${status?.email ?? ''} · Emails sent via Gmail appear in your Sent folder`
              : 'Send and receive emails through your Gmail account'}
          </p>
        )}
        {status?.last_synced_at && (
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-0.5">
            Last synced: {new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(status.last_synced_at))}
          </p>
        )}
        {connected && status?.last_error && !needsReconnect && (
          <p className="text-xs text-red-500 mt-0.5">{status.last_error}</p>
        )}
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        {connected ? (
          <>
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<ArrowPathIcon className="h-4 w-4" />}
              onClick={() => syncMutation.mutate()}
              disabled={syncMutation.isPending}
              aria-label="Sync Gmail"
            >
              Sync
            </Button>
            <Button
              variant="danger"
              size="sm"
              leftIcon={<XMarkIcon className="h-4 w-4" />}
              onClick={onRequestDisconnect}
              aria-label="Disconnect Gmail"
            >
              Disconnect
            </Button>
          </>
        ) : (
          <Button
            variant="primary"
            size="sm"
            leftIcon={<LinkIcon className="h-4 w-4" />}
            onClick={() => connectMutation.mutate()}
            disabled={connectMutation.isPending}
            aria-label={needsReconnect ? 'Reconnect Gmail' : 'Connect Gmail'}
          >
            {needsReconnect ? 'Reconnect' : 'Connect'}
          </Button>
        )}
      </div>
    </div>
  );
}

type DisconnectingIntegration = 'gmail' | 'calendar' | 'meta' | null;

const DISCONNECT_MESSAGES: Record<Exclude<DisconnectingIntegration, null>, string> = {
  gmail: 'The CRM will stop sending emails on your behalf and inbound sync will pause.',
  calendar: 'Activities will no longer sync to/from Google Calendar.',
  meta: 'LinkedIn campaigns will stop syncing audiences.',
};

const DISCONNECT_TITLES: Record<Exclude<DisconnectingIntegration, null>, string> = {
  gmail: 'Disconnect Gmail?',
  calendar: 'Disconnect Google Calendar?',
  meta: 'Disconnect Meta?',
};

export function IntegrationsSection() {
  const queryClient = useQueryClient();
  const [disconnectingIntegration, setDisconnectingIntegration] = useState<DisconnectingIntegration>(null);

  const calendarDisconnectMutation = useMutation({
    mutationFn: disconnectCalendar,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'google-calendar'] });
      toast.success('Google Calendar disconnected');
      setDisconnectingIntegration(null);
    },
  });

  const metaDisconnectMutation = useMutation({
    mutationFn: disconnectMeta,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'meta'] });
      toast.success('Meta disconnected');
      setDisconnectingIntegration(null);
    },
  });

  const gmailDisconnectMutation = useMutation({
    mutationFn: disconnectGmail,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'gmail'] });
      toast.success('Gmail disconnected');
      setDisconnectingIntegration(null);
    },
  });

  const handleConfirmDisconnect = () => {
    if (disconnectingIntegration === 'gmail') gmailDisconnectMutation.mutate();
    else if (disconnectingIntegration === 'calendar') calendarDisconnectMutation.mutate();
    else if (disconnectingIntegration === 'meta') metaDisconnectMutation.mutate();
  };

  const isDisconnecting =
    gmailDisconnectMutation.isPending ||
    calendarDisconnectMutation.isPending ||
    metaDisconnectMutation.isPending;

  return (
    <div>
      <Card>
        <CardHeader
          title="Integrations"
          description="Connect third-party services to your CRM"
        />
        <CardBody className="p-4 sm:p-6">
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            <GmailCard onRequestDisconnect={() => setDisconnectingIntegration('gmail')} />
            <GoogleCalendarCard onRequestDisconnect={() => setDisconnectingIntegration('calendar')} />
            <MetaCard onRequestDisconnect={() => setDisconnectingIntegration('meta')} />
          </div>
        </CardBody>
      </Card>

      <ConfirmDialog
        isOpen={disconnectingIntegration !== null}
        onClose={() => setDisconnectingIntegration(null)}
        onConfirm={handleConfirmDisconnect}
        title={disconnectingIntegration ? DISCONNECT_TITLES[disconnectingIntegration] : ''}
        message={disconnectingIntegration ? DISCONNECT_MESSAGES[disconnectingIntegration] : ''}
        confirmLabel="Disconnect"
        variant="danger"
        isLoading={isDisconnecting}
      />
    </div>
  );
}
