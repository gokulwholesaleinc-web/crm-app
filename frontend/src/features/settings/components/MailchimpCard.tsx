/**
 * Mailchimp connection card for the Settings -> Integrations panel.
 *
 * Mailchimp is the campaign-only send path. Transactional mail
 * (proposals, invoices, e-sign) is sent through the user's connected
 * Gmail account; Mailchimp is wired up here so marketing campaigns
 * with `send_via = "mailchimp"` can drive existing Mailchimp audiences.
 */

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowPathIcon,
  CheckCircleIcon,
  EnvelopeOpenIcon,
  LinkIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { showSuccess, showError } from '../../../utils/toast';

import { Button } from '../../../components/ui/Button';
import { Spinner } from '../../../components/ui/Spinner';
import {
  type MailchimpAudience,
  type MailchimpStatus,
  connectMailchimp,
  getMailchimpStatus,
  listMailchimpAudiences,
  setMailchimpAudience,
  setMailchimpBlockedAudiences,
} from '../../../api/integrations';
import { usePermissions } from '../../../hooks/usePermissions';
import { MailchimpAudienceViewer } from './MailchimpAudienceViewer';

function StatusPill({ connected }: { connected: boolean | null }) {
  if (connected === null) {
    // Non-admins can't query Mailchimp status — show an honest "unknown"
    // pill instead of lying with "Not connected" when we have no data.
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-gray-100 dark:bg-gray-700 px-2.5 py-0.5 text-xs font-medium text-gray-600 dark:text-gray-400">
        Admin only
      </span>
    );
  }
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

function ConnectForm({ onConnected }: { onConnected: () => void }) {
  const [apiKey, setApiKey] = useState('');

  const connectMutation = useMutation({
    mutationFn: connectMailchimp,
    onSuccess: () => {
      showSuccess('Mailchimp connected');
      setApiKey('');
      onConnected();
    },
    onError: (err: unknown) => {
      const detail =
        err && typeof err === 'object' && 'response' in err
          ? // axios-style error
            (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null;
      showError(detail ?? 'Mailchimp rejected the API key');
    },
  });

  return (
    <form
      className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-end"
      onSubmit={(e) => {
        e.preventDefault();
        if (apiKey.trim().length < 10) {
          showError('Paste your full Mailchimp API key (ends with -us19, -us21, etc.)');
          return;
        }
        connectMutation.mutate(apiKey.trim());
      }}
    >
      <div className="flex-1 min-w-0">
        <label
          htmlFor="mailchimp-api-key"
          className="block text-xs font-medium text-gray-700 dark:text-gray-300"
        >
          Mailchimp API key
        </label>
        <input
          id="mailchimp-api-key"
          type="password"
          autoComplete="off"
          spellCheck={false}
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="abcdef0123456789...-us19"
          className="mt-1 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2.5 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      </div>
      <Button
        type="submit"
        variant="primary"
        size="sm"
        leftIcon={<LinkIcon className="h-4 w-4" />}
        disabled={connectMutation.isPending || apiKey.trim().length < 10}
      >
        Connect
      </Button>
    </form>
  );
}

function AudiencePicker({ status }: { status: MailchimpStatus }) {
  const queryClient = useQueryClient();
  const [showBlockedManager, setShowBlockedManager] = useState(false);
  const { data: audiences, isLoading } = useQuery<MailchimpAudience[]>({
    queryKey: ['integrations', 'mailchimp', 'audiences'],
    queryFn: listMailchimpAudiences,
    enabled: status.connected,
  });

  const setMutation = useMutation({
    mutationFn: setMailchimpAudience,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'mailchimp', 'status'] });
      showSuccess('Default audience updated');
    },
    onError: () => showError('Could not update audience'),
  });

  const blockMutation = useMutation({
    mutationFn: setMailchimpBlockedAudiences,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['integrations', 'mailchimp', 'status'] });
      showSuccess('Blocklist updated');
    },
    onError: () => showError('Could not update blocklist'),
  });

  if (isLoading) {
    return (
      <div className="mt-2 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
        <Spinner size="sm" /> Loading audiences&hellip;
      </div>
    );
  }

  if (!audiences || audiences.length === 0) {
    return (
      <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
        No audiences found in this Mailchimp account.
      </p>
    );
  }

  const blockedSet = new Set(status.blocked_audience_ids ?? []);
  const defaultIsBlocked =
    status.default_audience_id != null &&
    blockedSet.has(status.default_audience_id);

  const toggleBlocked = (audienceId: string) => {
    const next = new Set(blockedSet);
    if (next.has(audienceId)) {
      next.delete(audienceId);
    } else {
      next.add(audienceId);
    }
    blockMutation.mutate([...next]);
  };

  return (
    <div className="mt-2 flex flex-col gap-2">
      <label
        htmlFor="mailchimp-audience"
        className="block text-xs font-medium text-gray-700 dark:text-gray-300"
      >
        Default audience
      </label>
      {defaultIsBlocked && (
        <p
          role="alert"
          className="rounded-md border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 px-2.5 py-1.5 text-xs text-amber-700 dark:text-amber-300"
        >
          Heads up: the current default audience is blocked. Campaigns will
          still send to it until you pick a different default. Either unblock
          it below or pick a new default first.
        </p>
      )}
      <select
        id="mailchimp-audience"
        value={status.default_audience_id ?? ''}
        onChange={(e) => {
          const next = e.target.value;
          if (next && !blockedSet.has(next)) setMutation.mutate(next);
        }}
        className="block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 px-2.5 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
      >
        <option value="" disabled>
          Select an audience&hellip;
        </option>
        {audiences.map((a) => (
          <option
            key={a.id}
            value={a.id}
            disabled={blockedSet.has(a.id)}
          >
            {blockedSet.has(a.id) ? '🚫 ' : ''}
            {a.name} ({a.member_count.toLocaleString()})
            {blockedSet.has(a.id) ? ' — blocked' : ''}
          </option>
        ))}
      </select>

      <button
        type="button"
        onClick={() => setShowBlockedManager((v) => !v)}
        className="self-start text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 rounded"
      >
        {showBlockedManager ? 'Hide blocklist' : 'Manage blocked audiences'}
        {blockedSet.size > 0 && (
          <span className="ml-1 text-gray-500 dark:text-gray-400">
            ({blockedSet.size} blocked)
          </span>
        )}
      </button>

      {showBlockedManager && (
        <div className="rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 p-3">
          <p className="mb-2 text-xs text-gray-600 dark:text-gray-400">
            Audiences marked blocked are disabled in the dropdown so the
            CRM can't accidentally point at them. The send path still
            relies on per-send segment scoping for the actual safety guarantee.
          </p>
          <ul className="space-y-1">
            {audiences.map((a) => {
              const isBlocked = blockedSet.has(a.id);
              return (
                <li key={a.id} className="flex items-center gap-2">
                  <input
                    id={`block-${a.id}`}
                    type="checkbox"
                    checked={isBlocked}
                    onChange={() => toggleBlocked(a.id)}
                    disabled={blockMutation.isPending}
                    className="h-4 w-4 rounded border-gray-300 dark:border-gray-600 text-indigo-600 focus:ring-indigo-500"
                  />
                  <label
                    htmlFor={`block-${a.id}`}
                    className="text-xs text-gray-700 dark:text-gray-300 select-none"
                  >
                    {a.name}{' '}
                    <span className="text-gray-500 dark:text-gray-400">
                      ({a.member_count.toLocaleString()})
                    </span>
                    {isBlocked && (
                      <span className="ml-1 font-medium text-red-600 dark:text-red-400">
                        blocked
                      </span>
                    )}
                  </label>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

function AudienceViewerToggle() {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="text-xs font-medium text-indigo-600 dark:text-indigo-400 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-500 rounded"
      >
        {open ? 'Hide audience members' : 'View audience members'}
      </button>
      <MailchimpAudienceViewer enabled={open} />
    </div>
  );
}

export function MailchimpCard({
  onRequestDisconnect,
}: {
  onRequestDisconnect: () => void;
}) {
  const { isAdmin } = usePermissions();
  const queryClient = useQueryClient();
  const { data: status, isLoading, refetch } = useQuery<MailchimpStatus>({
    queryKey: ['integrations', 'mailchimp', 'status'],
    queryFn: getMailchimpStatus,
    enabled: isAdmin,
  });

  if (isLoading) {
    return <Spinner size="sm" />;
  }

  // For non-admins the status query is disabled (enabled: isAdmin), so
  // `status` is always undefined and we'd otherwise render a red "Not
  // connected" pill regardless of reality. Use `null` to signal "unknown".
  const connected: boolean | null = isAdmin ? status?.connected ?? false : null;

  return (
    <div className="flex items-start gap-4 py-4 first:pt-0 last:pb-0">
      <div className="flex-shrink-0">
        <div className="h-10 w-10 rounded-lg bg-yellow-100 dark:bg-yellow-900/30 flex items-center justify-center">
          <EnvelopeOpenIcon
            className="h-5 w-5 text-yellow-600 dark:text-yellow-400"
            aria-hidden="true"
          />
        </div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">Mailchimp</p>
          <StatusPill connected={connected} />
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          {connected
            ? `${status?.account_email ?? 'connected'} · server ${status?.server_prefix ?? ''} · campaigns send through your audiences`
            : 'Connect a Mailchimp account to send marketing campaigns through an existing audience.'}
        </p>
        {connected && status && (
          <>
            {isAdmin && <AudiencePicker status={status} />}
            <p className="mt-2 text-xs text-gray-400 dark:text-gray-500">
              Default audience: {status.default_audience_name ?? 'not set'}
            </p>
            {isAdmin && status.default_audience_id && (
              <AudienceViewerToggle />
            )}
          </>
        )}
        {!connected && isAdmin && (
          <ConnectForm
            onConnected={() => {
              queryClient.invalidateQueries({ queryKey: ['integrations', 'mailchimp'] });
              void refetch();
            }}
          />
        )}
        {!connected && !isAdmin && (
          <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
            Ask an admin to connect Mailchimp from Settings → Integrations.
          </p>
        )}
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        {!isAdmin && (
          <span className="text-xs text-gray-400 dark:text-gray-500">Admin only</span>
        )}
        {connected && isAdmin && (
          <>
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<ArrowPathIcon className="h-4 w-4" />}
              onClick={() =>
                queryClient.invalidateQueries({ queryKey: ['integrations', 'mailchimp'] })
              }
              aria-label="Refresh Mailchimp"
            >
              Refresh
            </Button>
            <Button
              variant="danger"
              size="sm"
              leftIcon={<XMarkIcon className="h-4 w-4" />}
              onClick={onRequestDisconnect}
              aria-label="Disconnect Mailchimp"
            >
              Disconnect
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
