import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { PaperAirplaneIcon, NoSymbolIcon } from '@heroicons/react/24/outline';
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
} from '../../api/onboarding';
import { formatDate } from '../../utils/formatters';
import { showSuccess, showError } from '../../utils/toast';
import { extractApiErrorDetail } from '../../utils/errors';
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

export function OnboardingSendPanel({ templates }: OnboardingSendPanelProps) {
  const queryClient = useQueryClient();
  const [contactId, setContactId] = useState<number | null>(null);
  const [contactSearch, setContactSearch] = useState('');
  const [recipientEmail, setRecipientEmail] = useState('');
  const [recipientName, setRecipientName] = useState('');
  const [selectedTemplateIds, setSelectedTemplateIds] = useState<Set<number>>(() => new Set());
  // The one-time access_url returned by the create call — shown once, copied,
  // then dropped on the next create (it is never re-served by the API §8).
  const [accessUrl, setAccessUrl] = useState<string | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<OnboardingPacket | null>(null);

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
    onSuccess: (packet) => {
      queryClient.invalidateQueries({ queryKey: [...PACKETS_KEY, contactId] });
      setAccessUrl(packet.access_url ?? null);
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (packetId: number) => revokeOnboardingPacket(packetId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [...PACKETS_KEY, contactId] }),
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
    setAccessUrl(null);
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

  const handleSend = async () => {
    if (!canSend || contactId == null) return;
    try {
      await createMutation.mutateAsync({
        contact_id: contactId,
        recipient_email: recipientEmail.trim(),
        recipient_name: recipientName.trim() || null,
        template_ids: [...selectedTemplateIds],
      });
      setSelectedTemplateIds(new Set());
      showSuccess('Onboarding link created. Copy it below to share with the client.');
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to create onboarding link');
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
                  const disabled = !t.has_pdf;
                  return (
                    <label
                      key={t.id}
                      className={`flex items-center gap-2.5 rounded border px-3 py-2 text-sm ${
                        disabled
                          ? 'border-gray-200 dark:border-gray-700 opacity-60 cursor-not-allowed'
                          : 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/40 cursor-pointer'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={selectedTemplateIds.has(t.id)}
                        onChange={() => toggleTemplate(t.id)}
                        disabled={disabled}
                        className="h-4 w-4 rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
                      />
                      <span className="min-w-0 flex-1 truncate text-gray-900 dark:text-gray-100">{t.name}</span>
                      {t.requires_esign && <Badge variant="yellow" size="sm">E-sign</Badge>}
                      {disabled && <span className="text-xs text-gray-400">No PDF</span>}
                    </label>
                  );
                })}
              </div>
            )}
          </fieldset>

          <Button
            leftIcon={<PaperAirplaneIcon className="h-4 w-4" aria-hidden="true" />}
            onClick={handleSend}
            disabled={!canSend}
            isLoading={createMutation.isPending}
          >
            Create onboarding link
          </Button>

          {/* One-time access URL */}
          {accessUrl && (
            <div className="rounded-md border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 p-3" role="status" aria-live="polite">
              <p className="text-sm font-medium text-green-900 dark:text-green-200">
                Link ready — copy it now. It is shown only once.
              </p>
              <div className="mt-2 flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded bg-white dark:bg-gray-800 border border-green-200 dark:border-green-800 px-2 py-1 text-xs text-gray-700 dark:text-gray-200">
                  {accessUrl}
                </code>
                <CopyButton value={accessUrl} label="onboarding link" />
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
    </section>
  );
}

interface PacketRowProps {
  packet: OnboardingPacket;
  onRevoke?: () => void;
}

function PacketRow({ packet, onRevoke }: PacketRowProps) {
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
      {onRevoke && (
        <div className="flex-shrink-0">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            leftIcon={<NoSymbolIcon className="h-4 w-4" aria-hidden="true" />}
            onClick={onRevoke}
          >
            Revoke
          </Button>
        </div>
      )}
    </li>
  );
}

export default OnboardingSendPanel;
