import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  NoSymbolIcon,
  ArrowPathIcon,
  EnvelopeIcon,
  LinkIcon,
  PaperClipIcon,
  ChevronDownIcon,
  ArrowDownTrayIcon,
} from '@heroicons/react/24/outline';
import { Button, Badge, ConfirmDialog, CopyButton } from '../../components/ui';
import {
  listOnboardingPackets,
  getOnboardingPacket,
  revokeOnboardingPacket,
  retryOnboardingPacket,
  resendOnboardingCompletionNotice,
  resendOnboardingPacketInvite,
  regenerateOnboardingPacketLink,
} from '../../api/onboarding';
import { downloadAttachmentFile } from '../../api/attachments';
import { formatDate, formatFileSize } from '../../utils/formatters';
import { showSuccess, showError } from '../../utils/toast';
import { extractApiErrorDetail } from '../../utils/errors';
import { isGmailReconnectSendError } from '../../utils/gmailSendError';
import { GMAIL_SETTINGS_PATH } from '../../utils/integrationLinks';
import type {
  OnboardingPacket,
  OnboardingPacketStatus,
  OnboardingPacketDelivery,
  OnboardingPacketUpload,
} from '../../types';

export const PACKETS_KEY = ['onboarding-packets'] as const;

/** Status pill colour by packet lifecycle state (build-order note §2). */
const STATUS_VARIANT: Record<OnboardingPacketStatus, 'gray' | 'blue' | 'green' | 'yellow' | 'red'> = {
  active: 'blue',
  opened: 'blue',
  in_progress: 'yellow',
  completing: 'yellow',
  completed: 'green',
  expired: 'gray',
  revoked: 'red',
  completion_failed: 'red',
  abandoned: 'gray',
};

const STATUS_LABEL: Record<OnboardingPacketStatus, string> = {
  active: 'Sent',
  opened: 'Opened',
  in_progress: 'In progress',
  completing: 'Finishing',
  completed: 'Completed',
  expired: 'Expired',
  revoked: 'Revoked',
  completion_failed: 'Needs attention',
  abandoned: 'Abandoned',
};

const DELIVERY_VARIANT: Record<OnboardingPacketDelivery, 'gray' | 'green' | 'red' | 'yellow'> = {
  pending: 'gray',
  sent: 'green',
  failed: 'red',
  retry: 'yellow',
  throttled: 'yellow',
};

/** Non-terminal statuses can be revoked. */
const REVOKABLE = new Set<OnboardingPacketStatus>([
  'active',
  'opened',
  'in_progress',
  'completion_failed',
]);

/** A stuck/failed packet can be re-finalized (salvages the client's data). */
const RETRYABLE = new Set<OnboardingPacketStatus>(['completion_failed', 'completing']);

/** A completed packet can have its download notice re-sent (fresh link). */
const RESENDABLE = new Set<OnboardingPacketStatus>(['completed']);

/**
 * A still-live (or expired) packet can have its *invite* re-minted (a fresh
 * access token + re-queued invite). Terminal states are a 409.
 */
const INVITE_RESENDABLE = new Set<OnboardingPacketStatus>([
  'active',
  'opened',
  'in_progress',
  'expired',
]);

interface OnboardingPacketListProps {
  contactId: number;
  /** Optional section heading (omit for a bare list). */
  heading?: string;
  emptyText?: string;
}

/**
 * The per-contact onboarding packet list with its full lifecycle toolkit —
 * resend invite / resend completion notice / retry / revoke / regenerate
 * (copy a fresh link) — plus the client-uploaded files (D5). Shared by the
 * staff send panel and the contact-page Onboarding tab so the actions can't
 * drift between the two surfaces.
 */
export function OnboardingPacketList({
  contactId,
  heading,
  emptyText = 'No onboarding packets yet for this contact.',
}: OnboardingPacketListProps) {
  const queryClient = useQueryClient();
  const [copyLink, setCopyLink] = useState<string | null>(null);
  const [gmailPrompt, setGmailPrompt] = useState<string | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<OnboardingPacket | null>(null);
  const [regenerateTarget, setRegenerateTarget] = useState<OnboardingPacket | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: [...PACKETS_KEY, contactId] });

  const { data: packets = [], isLoading } = useQuery({
    queryKey: [...PACKETS_KEY, contactId],
    queryFn: () => listOnboardingPackets(contactId),
  });

  const revokeMutation = useMutation({
    mutationFn: (packetId: number) => revokeOnboardingPacket(packetId),
    onSuccess: () => invalidate(),
  });

  const retryMutation = useMutation({
    mutationFn: (packetId: number) => retryOnboardingPacket(packetId),
    onSuccess: () => {
      invalidate();
      showSuccess('Retrying finalization — refresh in a moment to see the result.');
    },
    onError: (err) => showError(extractApiErrorDetail(err) ?? 'Failed to retry finalization'),
  });

  const resendMutation = useMutation({
    mutationFn: (packetId: number) => resendOnboardingCompletionNotice(packetId),
    onSuccess: (result) => {
      invalidate();
      showSuccess(
        `Download link re-queued to ${result.resent.length} recipient(s) — check delivery status below.`,
      );
    },
    onError: (err) => showError(extractApiErrorDetail(err) ?? 'Failed to resend the notice'),
  });

  const resendInviteMutation = useMutation({
    mutationFn: (packetId: number) => resendOnboardingPacketInvite(packetId),
    onSuccess: () => {
      invalidate();
      showSuccess('Fresh invite link re-sent — check delivery status below.');
    },
    onError: (err) => {
      const detail = extractApiErrorDetail(err);
      if (isGmailReconnectSendError(detail)) {
        setGmailPrompt(detail ?? 'Connect your Gmail to email onboarding invites.');
        return;
      }
      showError(detail ?? 'Failed to resend the invite');
    },
  });

  // Link recovery (F5): rotate the token + surface the NEW link to copy.
  const regenerateMutation = useMutation({
    mutationFn: (packetId: number) => regenerateOnboardingPacketLink(packetId),
    onSuccess: (packet) => {
      invalidate();
      setCopyLink(packet.access_url ?? null);
      showSuccess('Fresh link generated — copy it below. The previous link no longer works.');
    },
    onError: (err) => showError(extractApiErrorDetail(err) ?? 'Failed to regenerate the link'),
  });

  const handleRevokeConfirm = async () => {
    if (!revokeTarget) return;
    try {
      await revokeMutation.mutateAsync(revokeTarget.id);
      showSuccess('Onboarding link revoked.');
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to revoke link');
    } finally {
      setRevokeTarget(null);
    }
  };

  const handleRegenerateConfirm = async () => {
    if (!regenerateTarget) return;
    try {
      await regenerateMutation.mutateAsync(regenerateTarget.id);
    } catch {
      // Surfaced by the mutation's onError; swallow so the un-awaited
      // ConfirmDialog onConfirm promise isn't left unhandled.
    } finally {
      setRegenerateTarget(null);
    }
  };

  return (
    <div className="space-y-3">
      {heading && (
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">{heading}</h3>
      )}

      {/* Connect-Gmail prompt — only after a resend failed on a missing Gmail. */}
      {gmailPrompt && (
        <div
          role="alert"
          aria-live="polite"
          className="rounded-md border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 p-3"
        >
          <p className="text-sm font-medium text-amber-900 dark:text-amber-200">{gmailPrompt}</p>
          <Link
            to={GMAIL_SETTINGS_PATH}
            className="mt-2 inline-flex items-center gap-1 rounded text-sm font-semibold text-amber-900 underline underline-offset-2 hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 dark:text-amber-200"
          >
            Connect Gmail in Settings
          </Link>
        </div>
      )}

      {/* The fresh link from a regenerate — shown once, copied, then dropped. */}
      {copyLink && (
        <div className="rounded-md border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 p-3" role="status" aria-live="polite">
          <p className="text-sm font-medium text-green-900 dark:text-green-200">
            New link ready — copy it now. It is shown only once.
          </p>
          <div className="mt-2 flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded bg-white dark:bg-gray-800 border border-green-200 dark:border-green-800 px-2 py-1 text-xs text-gray-700 dark:text-gray-200">
              {copyLink}
            </code>
            <CopyButton value={copyLink} label="onboarding link" />
          </div>
        </div>
      )}

      {isLoading ? (
        <p className="text-sm text-gray-400">Loading…</p>
      ) : packets.length === 0 ? (
        <p className="text-sm text-gray-400 dark:text-gray-500">{emptyText}</p>
      ) : (
        <ul className="divide-y divide-gray-200 dark:divide-gray-700 rounded-md border border-gray-200 dark:border-gray-700">
          {packets.map((p) => (
            <PacketRow
              key={p.id}
              packet={p}
              expanded={expandedId === p.id}
              onToggleFiles={() => setExpandedId((curr) => (curr === p.id ? null : p.id))}
              onRetry={
                RETRYABLE.has(p.status) && !retryMutation.isPending
                  ? () => retryMutation.mutate(p.id)
                  : undefined
              }
              onResend={
                RESENDABLE.has(p.status) && !resendMutation.isPending
                  ? () => resendMutation.mutate(p.id)
                  : undefined
              }
              onResendInvite={
                INVITE_RESENDABLE.has(p.status) && !resendInviteMutation.isPending
                  ? () => resendInviteMutation.mutate(p.id)
                  : undefined
              }
              onRegenerate={
                INVITE_RESENDABLE.has(p.status) && !regenerateMutation.isPending
                  ? () => setRegenerateTarget(p)
                  : undefined
              }
              onRevoke={REVOKABLE.has(p.status) ? () => setRevokeTarget(p) : undefined}
            />
          ))}
        </ul>
      )}

      <ConfirmDialog
        isOpen={revokeTarget !== null}
        onClose={() => setRevokeTarget(null)}
        onConfirm={handleRevokeConfirm}
        title="Revoke onboarding link"
        message="Revoking immediately disables the link and erases any data the client entered. This cannot be undone."
        confirmLabel="Revoke"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={revokeMutation.isPending}
      />

      <ConfirmDialog
        isOpen={regenerateTarget !== null}
        onClose={() => setRegenerateTarget(null)}
        onConfirm={handleRegenerateConfirm}
        title="Generate a new link"
        message="This immediately stops the current link from working — anyone who already has the old link will get an error. The new link is shown for you to copy; no email is sent unless you resend the invite."
        confirmLabel="Generate new link"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={regenerateMutation.isPending}
      />
    </div>
  );
}

interface PacketRowProps {
  packet: OnboardingPacket;
  expanded: boolean;
  onToggleFiles: () => void;
  onRetry?: () => void;
  onResend?: () => void;
  onResendInvite?: () => void;
  onRegenerate?: () => void;
  onRevoke?: () => void;
}

function PacketRow({
  packet,
  expanded,
  onToggleFiles,
  onRetry,
  onResend,
  onResendInvite,
  onRegenerate,
  onRevoke,
}: PacketRowProps) {
  const emails = packet.emails ?? [];
  return (
    <li className="p-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={STATUS_VARIANT[packet.status]} size="sm">
              {STATUS_LABEL[packet.status]}
            </Badge>
            <span className="text-sm text-gray-700 dark:text-gray-300" style={{ fontVariantNumeric: 'tabular-nums' }}>
              {packet.document_count} document{packet.document_count === 1 ? '' : 's'}
            </span>
            {packet.recipient_email_masked && (
              <span className="text-xs text-gray-400 dark:text-gray-500 truncate">{packet.recipient_email_masked}</span>
            )}
          </div>
          <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500" style={{ fontVariantNumeric: 'tabular-nums' }}>
            Created {formatDate(packet.created_at)} · expires {formatDate(packet.token_expires_at)}
          </p>
          {emails.length > 0 && (
            <div className="mt-1 flex flex-wrap items-center gap-1.5">
              {emails.map((m) => (
                <Badge key={m.id} variant={DELIVERY_VARIANT[m.status]} size="sm">
                  {m.subject || 'Email'}: {m.status}
                </Badge>
              ))}
            </div>
          )}
        </div>
        <div className="flex flex-shrink-0 flex-wrap items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            leftIcon={
              <ChevronDownIcon
                className={`h-4 w-4 transition-transform motion-reduce:transition-none ${expanded ? 'rotate-180' : ''}`}
                aria-hidden="true"
              />
            }
            onClick={onToggleFiles}
            aria-expanded={expanded}
          >
            Files
          </Button>
          {/* Retry first so the destructive Revoke is never the only action. */}
          {onRetry && (
            <Button type="button" variant="secondary" size="sm" leftIcon={<ArrowPathIcon className="h-4 w-4" aria-hidden="true" />} onClick={onRetry}>
              Retry
            </Button>
          )}
          {onResendInvite && (
            <Button type="button" variant="ghost" size="sm" leftIcon={<EnvelopeIcon className="h-4 w-4" aria-hidden="true" />} onClick={onResendInvite}>
              Resend invite
            </Button>
          )}
          {onRegenerate && (
            <Button type="button" variant="ghost" size="sm" leftIcon={<LinkIcon className="h-4 w-4" aria-hidden="true" />} onClick={onRegenerate}>
              Copy new link
            </Button>
          )}
          {onResend && (
            <Button type="button" variant="ghost" size="sm" leftIcon={<EnvelopeIcon className="h-4 w-4" aria-hidden="true" />} onClick={onResend}>
              Resend link
            </Button>
          )}
          {onRevoke && (
            <Button type="button" variant="ghost" size="sm" leftIcon={<NoSymbolIcon className="h-4 w-4" aria-hidden="true" />} onClick={onRevoke}>
              Revoke
            </Button>
          )}
        </div>
      </div>

      {expanded && <PacketFiles packetId={packet.id} />}
    </li>
  );
}

/** Lazily fetch the packet detail (only when expanded) and list its uploads. */
function PacketFiles({ packetId }: { packetId: number }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['onboarding-packet-detail', packetId],
    queryFn: () => getOnboardingPacket(packetId),
  });

  const handleDownload = async (upload: OnboardingPacketUpload) => {
    if (upload.attachment_id == null) {
      showError('This file is no longer available to download.');
      return;
    }
    try {
      await downloadAttachmentFile(upload.attachment_id, upload.original_filename);
    } catch {
      showError('Failed to download the file.');
    }
  };

  if (isLoading) return <p className="mt-3 text-xs text-gray-400">Loading files…</p>;
  if (error) return <p className="mt-3 text-xs text-red-500">Failed to load files.</p>;

  const uploads = data?.uploads ?? [];
  if (uploads.length === 0) {
    return (
      <p className="mt-3 text-xs text-gray-400 dark:text-gray-500">
        No files uploaded by the client yet.
      </p>
    );
  }

  return (
    <ul className="mt-3 space-y-1.5 rounded-md bg-gray-50 dark:bg-gray-800/40 p-2">
      {uploads.map((u) => (
        <li key={u.id} className="flex items-center gap-2">
          <PaperClipIcon className="h-4 w-4 flex-shrink-0 text-gray-400" aria-hidden="true" />
          <span className="min-w-0 flex-1 truncate text-sm text-gray-700 dark:text-gray-200" title={u.original_filename}>
            {u.original_filename}
          </span>
          {u.sensitive && (
            <Badge variant="yellow" size="sm">
              Sensitive
            </Badge>
          )}
          <span className="flex-shrink-0 text-xs text-gray-400" style={{ fontVariantNumeric: 'tabular-nums' }}>
            {formatFileSize(u.byte_size)}
          </span>
          <button
            type="button"
            onClick={() => handleDownload(u)}
            disabled={u.attachment_id == null}
            aria-label={`Download ${u.original_filename}`}
            className="rounded p-1 text-gray-400 hover:text-primary-600 disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
          >
            <ArrowDownTrayIcon className="h-4 w-4" aria-hidden="true" />
          </button>
        </li>
      ))}
    </ul>
  );
}

export default OnboardingPacketList;
