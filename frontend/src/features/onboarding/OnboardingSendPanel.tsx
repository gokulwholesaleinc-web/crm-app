import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import clsx from 'clsx';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { PaperAirplaneIcon, LinkIcon } from '@heroicons/react/24/outline';
import { CheckIcon } from '@heroicons/react/20/solid';
import {
  Button,
  Input,
  Badge,
  SearchableSelect,
  CopyButton,
  type SearchableSelectOption,
} from '../../components/ui';
import { listContacts } from '../../api/contacts';
import { createOnboardingPacket } from '../../api/onboarding';
import { showSuccess, showError } from '../../utils/toast';
import { extractApiErrorDetail } from '../../utils/errors';
import { isGmailReconnectSendError } from '../../utils/gmailSendError';
import { GMAIL_SETTINGS_PATH } from '../../utils/integrationLinks';
import { OnboardingPacketList, PACKETS_KEY } from './OnboardingPacketList';
import type { OnboardingTemplate } from '../../types';

interface OnboardingSendPanelProps {
  /** Active templates available to send (retired ones are excluded upstream). */
  templates: OnboardingTemplate[];
}

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
  // The one-time access_url from a create — shown once, copied, then dropped on
  // the next action (it is never re-served by the API §8).
  const [copyLink, setCopyLink] = useState<string | null>(null);
  // Set when a send fails because the operator's Gmail isn't connected — drives
  // the inline Connect-Gmail prompt instead of a generic error toast (F4).
  const [gmailPrompt, setGmailPrompt] = useState<string | null>(null);

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

  const createMutation = useMutation({
    mutationFn: createOnboardingPacket,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [...PACKETS_KEY, contactId] });
    },
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

          {/* One-time access URL from a create. */}
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

          {/* Existing packets for the contact + their lifecycle actions + files. */}
          <OnboardingPacketList contactId={contactId} heading="Existing packets" />
        </>
      )}
    </section>
  );
}

export default OnboardingSendPanel;
