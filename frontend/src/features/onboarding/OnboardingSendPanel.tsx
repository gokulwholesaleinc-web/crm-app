import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import clsx from 'clsx';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  PaperAirplaneIcon,
  NoSymbolIcon,
  ArrowPathIcon,
  EnvelopeIcon,
  LinkIcon,
} from '@heroicons/react/24/outline';
import { CheckIcon } from '@heroicons/react/20/solid';
import {
  Button,
  Input,
  Badge,
  ConfirmDialog,
  SearchableSelect,
  CopyButton,
  type SearchableSelectOption,
} from '../../components/ui';
import { listContacts } from '../../api/contacts';
import {
  createOnboardingPacket,
  listOnboardingPackets,
  revokeOnboardingPacket,
  retryOnboardingPacket,
  resendOnboardingCompletionNotice,
  resendOnboardingPacketInvite,
  regenerateOnboardingPacketLink,
} from '../../api/onboarding';
import { formatDate } from '../../utils/formatters';
import { showSuccess, showError } from '../../utils/toast';
import { extractApiErrorDetail } from '../../utils/errors';
import { isGmailReconnectSendError } from '../../utils/gmailSendError';
import { GMAIL_SETTINGS_PATH } from '../../utils/integrationLinks';
import type {
  OnboardingTemplate,
  OnboardingPacket,
  OnboardingPacketStatus,
  OnboardingPacketDelivery,
} from '../../types';

interface OnboardingSendPanelProps {
  /** Active templates available to send (retired ones are excluded upstream). */
  templates: OnboardingTemplate[];
}

const PACKETS_KEY = ['onboarding-packets'] as const;

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
const RETRYABLE = new Set<OnboardingPacketStatus>([
  'completion_failed',
  'completing',
]);

/** A completed packet can have its download notice re-sent (fresh link). */
const RESENDABLE = new Set<OnboardingPacketStatus>(['completed']);

/**
 * A still-live (or expired) packet can have its *invite* re-minted — a fresh
 * access token + a re-queued invite email (distinct from the completion
 * notice). Terminal states (completed/revoked/completing/abandoned) are 409.
 */
const INVITE_RESENDABLE = new Set<OnboardingPacketStatus>([
  'active',
  'opened',
  'in_progress',
  'expired',
]);

export function OnboardingSendPanel({ templates }: OnboardingSendPanelProps) {
  const queryClient = useQueryClient();
  // Persist the picked contact in ?contact= so a full refresh keeps the packet
  // list + selection (F5/F7 — the link itself is unrecoverable, but the list
  // is rebuilt from the contact).
  const [searchParams, setSearchParams] = useSearchParams();
  const contactParam = searchParams.get('contact');
  const [contactId, setContactId] = useState<number | null>(
    contactParam ? Number(contactParam) || null : null,
  );
  const [contactSearch, setContactSearch] = useState('');
  const [recipientEmail, setRecipientEmail] = useState('');
  const [recipientName, setRecipientName] = useState('');
  const [selectedTemplateIds, setSelectedTemplateIds] = useState<Set<number>>(() => new Set());
  // The one-time access_url from a create OR regenerate — shown once, copied,
  // then dropped on the next action (it is never re-served by the API §8).
  const [copyLink, setCopyLink] = useState<string | null>(null);
  // Set when a send fails because the operator's Gmail isn't connected — drives
  // the inline Connect-Gmail prompt instead of a generic error toast (F4).
  const [gmailPrompt, setGmailPrompt] = useState<string | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<OnboardingPacket | null>(null);
  // Regenerate rotates the token immediately (the old link dies), so it is
  // confirmed first — a misclick must not strand a client on a dead link.
  const [regenerateTarget, setRegenerateTarget] = useState<OnboardingPacket | null>(null);

  const activeTemplates = useMemo(() => templates.filter((t) => t.is_active), [templates]);

  // Contact picker options — debounced via the searchable select's own query.
  const { data: contactList } = useQuery({
    queryKey: ['onboarding-contact-picker', contactSearch],
    queryFn: () => listContacts({ search: contactSearch || undefined, page_size: 50 }),
    staleTime: 30_000,
  });
  const contactOptions: SearchableSelectOption[] = useMemo(
    () =>
      (contactList?.items ?? []).map((c) => ({
        value: c.id,
        label: c.email ? `${c.full_name} · ${c.email}` : c.full_name,
      })),
    [contactList],
  );

  const { data: packets = [], isLoading: packetsLoading } = useQuery({
    queryKey: [...PACKETS_KEY, contactId],
    queryFn: () => (contactId ? listOnboardingPackets(contactId) : Promise.resolve([])),
    enabled: contactId != null,
  });

  const createMutation = useMutation({
    mutationFn: createOnboardingPacket,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [...PACKETS_KEY, contactId] });
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (packetId: number) => revokeOnboardingPacket(packetId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [...PACKETS_KEY, contactId] }),
  });

  const retryMutation = useMutation({
    mutationFn: (packetId: number) => retryOnboardingPacket(packetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [...PACKETS_KEY, contactId] });
      showSuccess('Retrying finalization — refresh in a moment to see the result.');
    },
    onError: (err) => showError(extractApiErrorDetail(err) ?? 'Failed to retry finalization'),
  });

  const resendMutation = useMutation({
    mutationFn: (packetId: number) => resendOnboardingCompletionNotice(packetId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: [...PACKETS_KEY, contactId] });
      showSuccess(
        `Download link re-queued to ${result.resent.length} recipient(s) — check delivery status below.`,
      );
    },
    onError: (err) => showError(extractApiErrorDetail(err) ?? 'Failed to resend the notice'),
  });

  const resendInviteMutation = useMutation({
    mutationFn: (packetId: number) => resendOnboardingPacketInvite(packetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [...PACKETS_KEY, contactId] });
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

  // Link recovery (F5): rotate the token + surface the NEW link to copy. The
  // previously shared link dies; no email unless the operator also resends.
  const regenerateMutation = useMutation({
    mutationFn: (packetId: number) => regenerateOnboardingPacketLink(packetId),
    onSuccess: (packet) => {
      queryClient.invalidateQueries({ queryKey: [...PACKETS_KEY, contactId] });
      setCopyLink(packet.access_url ?? null);
      showSuccess('Fresh link generated — copy it below. The previous link no longer works.');
    },
    onError: (err) => showError(extractApiErrorDetail(err) ?? 'Failed to regenerate the link'),
  });

  const toggleTemplate = (id: number) => {
    setSelectedTemplateIds((curr) => {
      const next = new Set(curr);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleContactChange = (id: number | null) => {
    setContactId(id);
    setCopyLink(null);
    setGmailPrompt(null);
    setSearchParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (id == null) next.delete('contact');
        else next.set('contact', String(id));
        return next;
      },
      { replace: true },
    );
    // Prefill the recipient email from the picked contact when available.
    const picked = (contactList?.items ?? []).find((c) => c.id === id);
    setRecipientEmail(picked?.email ?? '');
    setRecipientName(picked?.full_name ?? '');
  };

  const canSend =
    contactId != null &&
    recipientEmail.trim().length > 0 &&
    selectedTemplateIds.size > 0 &&
    !createMutation.isPending;

  const handleSend = async (sendEmail: boolean) => {
    if (!canSend || contactId == null) return;
    setGmailPrompt(null);
    try {
      const packet = await createMutation.mutateAsync({
        contact_id: contactId,
        recipient_email: recipientEmail.trim(),
        recipient_name: recipientName.trim() || null,
        template_ids: [...selectedTemplateIds],
        send_email: sendEmail,
      });
      setSelectedTemplateIds(new Set());
      setCopyLink(packet.access_url ?? null);
      showSuccess(
        sendEmail
          ? // The send queues from the owner's Gmail and is fail-soft, so don't
            // assert delivery — steer staff to the per-packet status badge.
            `Onboarding invite queued to ${recipientEmail.trim()} — check delivery status below. The copy link is shown as a backup.`
          : 'Onboarding link created. Copy it below to share with the client.',
      );
    } catch (err) {
      const detail = extractApiErrorDetail(err);
      // A Gmail-down send mints nothing (the backend pre-flights before create),
      // so steer the operator to reconnect rather than show a dead-end error.
      if (sendEmail && isGmailReconnectSendError(detail)) {
        setGmailPrompt(detail ?? 'Connect your Gmail to email onboarding invites.');
      } else {
        showError(detail ?? 'Failed to create onboarding link');
      }
    }
  };

  const handleRevokeConfirm = async () => {
    if (!revokeTarget) return;
    try {
      await revokeMutation.mutateAsync(revokeTarget.id);
      showSuccess('Onboarding link revoked.');
      setRevokeTarget(null);
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to revoke link');
    }
  };

  const handleRegenerateConfirm = async () => {
    if (!regenerateTarget) return;
    try {
      // Success/error toasts + copyLink are handled by the mutation callbacks.
      await regenerateMutation.mutateAsync(regenerateTarget.id);
    } catch {
      // Already surfaced by the mutation's onError; swallow so the rejected
      // promise (ConfirmDialog calls onConfirm un-awaited) isn't unhandled.
    } finally {
      setRegenerateTarget(null);
    }
  };

  return (
    <section className="bg-white dark:bg-gray-800 shadow rounded-lg border border-transparent dark:border-gray-700 p-5 space-y-5">
      <div>
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Send onboarding to a client</h2>
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Pick a contact, choose the documents, and create a one-time link to share manually.
        </p>
      </div>

      {/* Contact picker */}
      <div>
        <SearchableSelect
          label="Contact"
          value={contactId}
          onChange={handleContactChange}
          options={contactOptions}
          placeholder="Search contacts..."
          name="onboarding-packet-contact"
        />
        {/* Drive the contact-search query as the user types. The SearchableSelect
            filters its own option labels; this keeps the server result set fresh. */}
        <input
          type="text"
          value={contactSearch}
          onChange={(e) => setContactSearch(e.target.value)}
          aria-label="Search contacts by name or email"
          placeholder="Type to search more contacts..."
          autoComplete="off"
          spellCheck={false}
          className="mt-2 block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-1.5 text-xs text-gray-700 dark:text-gray-200 placeholder:text-gray-400 focus-visible:border-primary-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary-500"
        />
      </div>

      {contactId != null && (
        <>
          {/* Recipient details */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input
              label="Recipient email"
              type="email"
              value={recipientEmail}
              onChange={(e) => setRecipientEmail(e.target.value)}
              name="onboarding-recipient-email"
              autoComplete="email"
              inputMode="email"
              spellCheck={false}
              placeholder="client@example.com"
              required
            />
            <Input
              label="Recipient name (optional)"
              value={recipientName}
              onChange={(e) => setRecipientName(e.target.value)}
              name="onboarding-recipient-name"
              autoComplete="name"
              placeholder="Client name..."
            />
          </div>

          {/* Template multi-select */}
          <fieldset>
            <legend className="text-sm font-medium text-gray-700 dark:text-gray-300">Documents to include</legend>
            {activeTemplates.length === 0 ? (
              <p className="mt-2 text-sm text-gray-400 dark:text-gray-500">
                No active templates. Create and upload a template first.
              </p>
            ) : (
              <div className="mt-2 space-y-1.5">
                {activeTemplates.map((t) => {
                  // Only esign_pdf templates need an uploaded PDF before they
                  // can be sent. questionnaire / upload_request templates carry
                  // no PDF by design and are sendable as-is (the backend mints
                  // them with pdf_path=None), so gating on has_pdf alone would
                  // wrongly lock them out with a misleading "No PDF" reason.
                  const isEsignPdf = (t.kind ?? 'esign_pdf') === 'esign_pdf';
                  const disabled = isEsignPdf && !t.has_pdf;
                  const selected = selectedTemplateIds.has(t.id);
                  return (
                    <button
                      key={t.id}
                      type="button"
                      role="checkbox"
                      aria-checked={selected}
                      disabled={disabled}
                      onClick={() => toggleTemplate(t.id)}
                      className={clsx(
                        'flex w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left text-sm transition-colors motion-reduce:transition-none',
                        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500',
                        disabled
                          ? 'cursor-not-allowed border-gray-200 opacity-60 dark:border-gray-700'
                          : selected
                            ? 'border-primary-500 bg-primary-50 dark:border-primary-500/60 dark:bg-primary-500/10'
                            : 'border-gray-200 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-700/40',
                      )}
                    >
                      <span
                        aria-hidden="true"
                        className={clsx(
                          'flex h-4 w-4 flex-shrink-0 items-center justify-center rounded border transition-colors motion-reduce:transition-none',
                          selected
                            ? 'border-primary-600 bg-primary-600 text-white'
                            : 'border-gray-300 bg-white dark:border-gray-500 dark:bg-gray-800',
                        )}
                      >
                        {selected && <CheckIcon className="h-3.5 w-3.5" />}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-gray-900 dark:text-gray-100">{t.name}</span>
                      {t.requires_esign && <Badge variant="yellow" size="sm">E-sign</Badge>}
                      {disabled && <span className="text-xs text-gray-400">No PDF</span>}
                    </button>
                  );
                })}
              </div>
            )}
          </fieldset>

          {/* Connect-Gmail prompt — only after a send failed on a missing Gmail. */}
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
              <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
                Or use “Create link only” to share the link yourself without email.
              </p>
            </div>
          )}

          {/* Primary: email the invite (D4). Secondary: mint a copy-only link. */}
          <div className="flex flex-wrap items-center gap-2">
            <Button
              leftIcon={<PaperAirplaneIcon className="h-4 w-4" aria-hidden="true" />}
              onClick={() => handleSend(true)}
              disabled={!canSend}
              isLoading={createMutation.isPending}
            >
              Send onboarding email
            </Button>
            <Button
              type="button"
              variant="secondary"
              leftIcon={<LinkIcon className="h-4 w-4" aria-hidden="true" />}
              onClick={() => handleSend(false)}
              disabled={!canSend}
            >
              Create link only
            </Button>
          </div>

          {/* One-time access URL (from a create or a regenerate) */}
          {copyLink && (
            <div className="rounded-md border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 p-3" role="status" aria-live="polite">
              <p className="text-sm font-medium text-green-900 dark:text-green-200">
                Link ready — copy it now. It is shown only once.
              </p>
              <div className="mt-2 flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded bg-white dark:bg-gray-800 border border-green-200 dark:border-green-800 px-2 py-1 text-xs text-gray-700 dark:text-gray-200">
                  {copyLink}
                </code>
                <CopyButton value={copyLink} label="onboarding link" />
              </div>
            </div>
          )}

          {/* Packet list for the contact */}
          <div>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Existing packets</h3>
            {packetsLoading ? (
              <p className="mt-2 text-sm text-gray-400">Loading…</p>
            ) : packets.length === 0 ? (
              <p className="mt-2 text-sm text-gray-400 dark:text-gray-500">No onboarding packets yet for this contact.</p>
            ) : (
              <ul className="mt-2 divide-y divide-gray-200 dark:divide-gray-700 rounded-md border border-gray-200 dark:border-gray-700">
                {packets.map((p) => (
                  <PacketRow
                    key={p.id}
                    packet={p}
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
          </div>
        </>
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
    </section>
  );
}

interface PacketRowProps {
  packet: OnboardingPacket;
  onRetry?: () => void;
  onResend?: () => void;
  onResendInvite?: () => void;
  onRegenerate?: () => void;
  onRevoke?: () => void;
}

function PacketRow({ packet, onRetry, onResend, onResendInvite, onRegenerate, onRevoke }: PacketRowProps) {
  const emails = packet.emails ?? [];
  return (
    <li className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between">
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
        {/* Live delivery status for any linked notice emails (staff-only). */}
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
      {(onRetry || onResend || onResendInvite || onRegenerate || onRevoke) && (
        <div className="flex flex-shrink-0 flex-wrap items-center gap-1">
          {/* Retry comes first for a stuck/failed packet so the destructive
              Revoke is never the only (or primary) action offered — revoke
              would scrub the salvageable signature the retry needs. */}
          {onRetry && (
            <Button
              type="button"
              variant="secondary"
              size="sm"
              leftIcon={<ArrowPathIcon className="h-4 w-4" aria-hidden="true" />}
              onClick={onRetry}
            >
              Retry
            </Button>
          )}
          {onResendInvite && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              leftIcon={<EnvelopeIcon className="h-4 w-4" aria-hidden="true" />}
              onClick={onResendInvite}
            >
              Resend invite
            </Button>
          )}
          {/* Recover a lost link: rotate + surface a fresh copyable URL (the old
              one dies). Distinct from "Resend invite", which emails it. */}
          {onRegenerate && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              leftIcon={<LinkIcon className="h-4 w-4" aria-hidden="true" />}
              onClick={onRegenerate}
            >
              Copy new link
            </Button>
          )}
          {onResend && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              leftIcon={<EnvelopeIcon className="h-4 w-4" aria-hidden="true" />}
              onClick={onResend}
            >
              Resend link
            </Button>
          )}
          {onRevoke && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              leftIcon={<NoSymbolIcon className="h-4 w-4" aria-hidden="true" />}
              onClick={onRevoke}
            >
              Revoke
            </Button>
          )}
        </div>
      )}
    </li>
  );
}

export default OnboardingSendPanel;
