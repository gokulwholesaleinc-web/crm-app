import { useCallback, useState, useEffect, useRef } from 'react';
import { Modal, Button, ConfirmDialog } from '../ui';
import { PaperClipIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { useSendEmail } from '../../hooks/useEmail';
import { useSubmitShortcut } from '../../hooks/useSubmitShortcut';
import { useUnsavedChangesWarning } from '../../hooks/useUnsavedChangesWarning';
import { showError } from '../../utils/toast';
import type { ThreadEmailItem } from '../../types/email';
import type { InlineAttachmentPayload } from '../../api/email';

interface EmailComposeModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultTo?: string;
  entityType?: string;
  entityId?: number;
  replyTo?: ThreadEmailItem | null;
  fromEmail?: string;
}

interface StagedAttachment {
  filename: string;
  content_type: string;
  size: number;
  content_b64: string;
}

// Mirrors backend MAX_ATTACHMENTS_TOTAL_BYTES — Gmail's 25 MB user-facing
// cap also bounds Resend's accepted size, so the same number applies on
// both providers. Exposed as a constant so the helper text stays in sync
// if we ever raise the limit.
const MAX_TOTAL_BYTES = 25 * 1024 * 1024;
const MAX_ATTACHMENT_COUNT = 10;

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== 'string') {
        reject(new Error('FileReader returned a non-string result'));
        return;
      }
      // result is a data URL: "data:<mime>;base64,<payload>" — strip the prefix.
      const comma = result.indexOf(',');
      resolve(comma === -1 ? result : result.slice(comma + 1));
    };
    reader.onerror = () => reject(reader.error ?? new Error('FileReader failed'));
    reader.readAsDataURL(file);
  });
}

type SendEmailErrorShape = {
  detail?: string | Array<{ msg?: string; loc?: string[] }>;
} | null | undefined;

/**
 * Pull a user-actionable error string out of either:
 *   - the local "queued but not sent" state we set after the 201 path, or
 *   - the mutation's HTTP error (FastAPI 4xx/5xx with `detail` string or list).
 *
 * Returns `null` when neither source has anything to show.
 */
function deriveSendErrorMessage(
  statusError: string | null,
  mutationError: SendEmailErrorShape,
): string | null {
  if (statusError) return statusError;
  if (!mutationError) return null;
  const { detail } = mutationError;
  if (typeof detail === 'string' && detail.trim()) return detail;
  // FastAPI 422 returns detail as a list of field errors. Show the first
  // user-actionable message rather than the generic "validation error".
  const first = Array.isArray(detail) ? detail[0] : undefined;
  if (first) {
    const where = first.loc?.[first.loc.length - 1];
    const msg = first.msg || 'invalid value';
    return where ? `${where}: ${msg}` : msg;
  }
  return 'Failed to send email. Check your inputs and try again.';
}

/**
 * Build the Gmail-style quote block we prefill on Reply.
 *
 * Plain-text only: HTML quoting requires sanitization on every render
 * (DOMPurify allowlist drift is a known footgun) and our compose textarea
 * is plaintext anyway. The header line follows the standard
 * "On {date}, {sender} wrote:" form so it round-trips cleanly into the
 * recipient's mail client even if they're reading in plain text.
 */
function buildQuotedReply(replyTo: ThreadEmailItem): string {
  // The header attributes the QUOTED message to its author, not the
  // current reply target. For outbound rows the original sender is
  // the CRM user (`from_email`); for inbound rows it's the customer.
  // Earlier this branch flipped to `to_email` on outbound and
  // attributed the user's own copy to the customer.
  const sender = replyTo.from_email ?? 'sender';
  const when = new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(replyTo.timestamp));
  // Prefer plain body. body_html falls back through a strip — we're
  // displaying inside a <textarea>, so anything not stripped becomes
  // visible markup noise. In practice CRM-sent emails have body set.
  const rawBody = replyTo.body ?? stripHtml(replyTo.body_html ?? '') ?? '';
  const quotedLines = rawBody
    .replace(/\r\n/g, '\n')
    .split('\n')
    .map((line) => `> ${line}`)
    .join('\n');
  return `On ${when}, ${sender} wrote:\n${quotedLines}`;
}

function stripHtml(html: string): string {
  // Lightweight tag stripper. Inline within compose flow only — never
  // used for HTML rendering, so XSS is moot here. Replace block tags
  // with newlines so paragraphs stay readable in the quote.
  return html
    .replace(/<\/(p|div|br|li|tr|h[1-6])>/gi, '\n')
    .replace(/<br\s*\/?>(\r?\n)?/gi, '\n')
    .replace(/<[^>]+>/g, '')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .trim();
}

export function EmailComposeModal({
  isOpen,
  onClose,
  defaultTo = '',
  entityType,
  entityId,
  replyTo = null,
  fromEmail,
}: EmailComposeModalProps) {
  const [to, setTo] = useState(defaultTo);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const [cc, setCc] = useState('');
  const [bcc, setBcc] = useState('');
  const [showCcBcc, setShowCcBcc] = useState(false);
  const [showDiscardConfirm, setShowDiscardConfirm] = useState(false);
  // Quoted-reply block sits in its own state so the user's reply text and
  // the prefilled quote can be independently edited without one stomping
  // the other when toggled.
  const [quotedText, setQuotedText] = useState('');
  const [showQuoted, setShowQuoted] = useState(false);
  const [attachments, setAttachments] = useState<StagedAttachment[]>([]);
  // `sendStatusError` covers the post-201 non-sent status path: the API
  // returned 201 but the queue row is in retry/failed state, which the
  // mutation's `error` channel doesn't see (it only surfaces HTTP errors).
  const [sendStatusError, setSendStatusError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const formRef = useRef<HTMLFormElement>(null);
  const sendEmailMutation = useSendEmail();

  const submitForm = useCallback(() => {
    formRef.current?.requestSubmit();
  }, []);
  useSubmitShortcut(formRef, submitForm);

  const totalAttachmentBytes = attachments.reduce((sum, a) => sum + a.size, 0);
  const overLimit = totalAttachmentBytes > MAX_TOTAL_BYTES;

  const isDirty =
    subject !== '' ||
    body !== '' ||
    cc !== '' ||
    bcc !== '' ||
    attachments.length > 0;
  useUnsavedChangesWarning(isDirty);

  const handleClose = () => {
    if (isDirty) {
      setShowDiscardConfirm(true);
    } else {
      onClose();
    }
  };

  // Clear the inline send-error banner whenever the modal is closed.
  // Parents (Contact/Lead detail) keep this component permanently mounted
  // and only flip `isOpen`, so without this the banner from a previous
  // failed attempt would still show on the next reopen with the same
  // `replyTo`. The reply-target effect below covers the open path.
  useEffect(() => {
    if (!isOpen) {
      setSendStatusError(null);
      sendEmailMutation.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  // Pre-fill on mount and whenever the reply target changes.
  // Intentionally excludes `defaultTo` from deps so a parent re-render with
  // a new default recipient doesn't wipe in-progress edits mid-compose.
  useEffect(() => {
    setSendStatusError(null);
    sendEmailMutation.reset();
    if (replyTo) {
      const replyRecipient =
        replyTo.direction === 'outbound' ? replyTo.to_email : replyTo.from_email;
      setTo(replyRecipient || '');
      setSubject(
        replyTo.subject.startsWith('Re: ')
          ? replyTo.subject
          : `Re: ${replyTo.subject}`
      );
      setBody('');
      setCc(replyTo.cc || '');
      setShowCcBcc(!!replyTo.cc);
      setQuotedText(buildQuotedReply(replyTo));
      setShowQuoted(false); // collapsed by default — keep the compose surface focused on the user's reply
      setAttachments([]);
    } else {
      setTo(defaultTo);
      setSubject('');
      setBody('');
      setCc('');
      setBcc('');
      setShowCcBcc(false);
      setQuotedText('');
      setShowQuoted(false);
      setAttachments([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replyTo]);

  const handleFilesPicked = async (filesList: FileList | null) => {
    if (!filesList || filesList.length === 0) return;
    const files = Array.from(filesList);
    if (attachments.length + files.length > MAX_ATTACHMENT_COUNT) {
      showError(`Max ${MAX_ATTACHMENT_COUNT} attachments per email.`);
      return;
    }

    try {
      const next: StagedAttachment[] = [];
      for (const file of files) {
        if (file.size === 0) {
          showError(`"${file.name}" is empty and was skipped.`);
          continue;
        }
        if (file.size > MAX_TOTAL_BYTES) {
          showError(`"${file.name}" is over the 25 MB limit.`);
          continue;
        }
        const content_b64 = await readFileAsBase64(file);
        next.push({
          filename: file.name,
          content_type: file.type || 'application/octet-stream',
          size: file.size,
          content_b64,
        });
      }
      setAttachments((curr) => [...curr, ...next]);
    } catch (err) {
      showError(err instanceof Error ? err.message : 'Failed to read attachment.');
    } finally {
      // Always reset the input so the same file can be re-picked.
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const removeAttachment = (index: number) => {
    setAttachments((curr) => curr.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSendStatusError(null);
    if (overLimit) {
      showError(
        `Attachments total ${formatBytes(totalAttachmentBytes)} — over the 25 MB limit.`
      );
      return;
    }
    const replyToEmailId = replyTo?.direction === 'outbound' ? replyTo.id : undefined;
    const replyToInboundId = replyTo?.direction === 'inbound' ? replyTo.id : undefined;

    // Combined body = user reply + (always-included) quoted block. The
    // showQuoted toggle only controls *display* of the quote in the
    // compose surface — it always ships on send so the recipient has
    // context.
    const finalBody = quotedText
      ? body.trimEnd() + '\n\n' + quotedText
      : body;

    const apiAttachments: InlineAttachmentPayload[] = attachments.map((a) => ({
      filename: a.filename,
      content_type: a.content_type,
      content_b64: a.content_b64,
    }));

    try {
      const queued = await sendEmailMutation.mutateAsync({
        to_email: to,
        subject,
        body: finalBody,
        from_email: fromEmail || undefined,
        cc: cc || undefined,
        bcc: bcc || undefined,
        entity_type: entityType,
        entity_id: entityId,
        reply_to_email_id: replyToEmailId,
        reply_to_inbound_id: replyToInboundId,
        attachments: apiAttachments.length > 0 ? apiAttachments : undefined,
      });
      // The endpoint returns 201 even when Gmail rejected the send and the
      // row is in retry/failed state. Show the row's error so the user
      // can see "Gmail not connected" or "401 invalid_grant" instead of
      // assuming the message went out.
      if (queued.status && queued.status !== 'sent') {
        setSendStatusError(
          queued.error
            ? `Email queued but not delivered: ${queued.error}`
            : `Email is in '${queued.status}' state — check the email log to retry.`,
        );
        return;
      }
      setSendStatusError(null);
      setTo(defaultTo);
      setSubject('');
      setBody('');
      setCc('');
      setBcc('');
      setShowCcBcc(false);
      setQuotedText('');
      setShowQuoted(false);
      setAttachments([]);
      onClose();
    } catch {
      // Error stays on mutation.error and renders inline below the form;
      // see the conditional banner. Modal remains open so the user can fix
      // and retry without losing their draft.
    }
  };

  const sendErrorMessage = deriveSendErrorMessage(
    sendStatusError,
    sendEmailMutation.error as SendEmailErrorShape,
  );

  const inputClass =
    'mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 shadow-sm text-sm focus-visible:outline-none focus-visible:border-primary-500 focus-visible:ring-1 focus-visible:ring-primary-500';

  return (
    <>
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title={replyTo ? 'Reply to Email' : 'Compose Email'}
      size="lg"
    >
      <form ref={formRef} onSubmit={handleSubmit} className="space-y-4">
        {/* From (read-only) */}
        {fromEmail && (
          <div>
            <label htmlFor="email-from" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              From
            </label>
            <input
              id="email-from"
              type="email"
              name="from"
              value={fromEmail}
              readOnly
              className={`${inputClass} bg-gray-50 dark:bg-gray-600 cursor-not-allowed`}
              tabIndex={-1}
            />
          </div>
        )}

        {/* To */}
        <div>
          <label htmlFor="email-to" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            To
          </label>
          <input
            id="email-to"
            type="email"
            name="to"
            required
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className={inputClass}
            placeholder="recipient@example.com..."
            autoComplete="email"
            spellCheck={false}
            autoFocus={!to}
          />
        </div>

        {/* CC/BCC toggle */}
        {!showCcBcc && (
          <button
            type="button"
            onClick={() => setShowCcBcc(true)}
            className="text-xs text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 font-medium focus-visible:outline-none focus-visible:underline"
            aria-label="Show CC and BCC fields"
          >
            Add CC / BCC
          </button>
        )}

        {/* CC */}
        {showCcBcc && (
          <>
            <div>
              <label htmlFor="email-cc" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                CC
              </label>
              <input
                id="email-cc"
                type="text"
                name="cc"
                value={cc}
                onChange={(e) => setCc(e.target.value)}
                className={inputClass}
                placeholder="cc@example.com..."
                autoComplete="email"
                spellCheck={false}
              />
            </div>
            <div>
              <label htmlFor="email-bcc" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                BCC
              </label>
              <input
                id="email-bcc"
                type="text"
                name="bcc"
                value={bcc}
                onChange={(e) => setBcc(e.target.value)}
                className={inputClass}
                placeholder="bcc@example.com..."
                autoComplete="email"
                spellCheck={false}
              />
            </div>
          </>
        )}

        {/* Subject */}
        <div>
          <label htmlFor="email-subject" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Subject
          </label>
          <input
            id="email-subject"
            type="text"
            name="subject"
            required
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className={inputClass}
            placeholder="Email subject..."
            autoComplete="off"
            autoFocus={!!to && !subject}
          />
        </div>

        {/* Body */}
        <div>
          <label htmlFor="email-body" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Body
          </label>
          <textarea
            id="email-body"
            name="body"
            required
            rows={8}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className={inputClass}
            placeholder={replyTo ? 'Type your reply...' : 'Write your email...'}
          />
        </div>

        {/* Quoted-reply block — collapsed by default to keep the compose
            surface focused on the user's reply, but always sent on
            submit so the recipient has thread context. */}
        {quotedText && (
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => setShowQuoted((v) => !v)}
              className="text-xs text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 font-medium focus-visible:outline-none focus-visible:underline"
              aria-expanded={showQuoted}
              aria-controls="email-quoted-text"
            >
              {showQuoted ? 'Hide quoted text' : 'Show quoted text'}
            </button>
            {showQuoted && (
              <textarea
                id="email-quoted-text"
                name="quoted"
                rows={6}
                value={quotedText}
                onChange={(e) => setQuotedText(e.target.value)}
                className={`${inputClass} font-mono text-xs`}
                aria-label="Quoted message"
              />
            )}
          </div>
        )}

        {/* Attachments */}
        <div>
          <div className="flex items-center justify-between">
            <span className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Attachments
            </span>
            <span
              className={`text-xs tabular-nums ${
                overLimit
                  ? 'text-red-600 dark:text-red-400'
                  : 'text-gray-500 dark:text-gray-400'
              }`}
            >
              {formatBytes(totalAttachmentBytes)} / 25 MB
            </span>
          </div>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            className="sr-only"
            onChange={(e) => handleFilesPicked(e.target.files)}
            aria-label="Attach files"
          />
          <Button
            type="button"
            variant="secondary"
            size="sm"
            leftIcon={<PaperClipIcon className="h-4 w-4" />}
            onClick={() => fileInputRef.current?.click()}
            disabled={attachments.length >= MAX_ATTACHMENT_COUNT}
            className="mt-1"
          >
            Add files
          </Button>
          {attachments.length > 0 && (
            <ul className="mt-2 space-y-1.5">
              {attachments.map((att, i) => (
                <li
                  key={`${att.filename}:${i}`}
                  className="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/60 text-xs"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <PaperClipIcon
                      className="h-3.5 w-3.5 text-gray-400 flex-shrink-0"
                      aria-hidden="true"
                    />
                    <span className="truncate text-gray-900 dark:text-gray-100">
                      {att.filename}
                    </span>
                    <span className="tabular-nums text-gray-500 dark:text-gray-400 flex-shrink-0">
                      {formatBytes(att.size)}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => removeAttachment(i)}
                    className="p-0.5 rounded text-gray-400 hover:text-red-500 dark:hover:text-red-400 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-red-500"
                    aria-label={`Remove attachment ${att.filename}`}
                  >
                    <XMarkIcon className="h-3.5 w-3.5" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {sendErrorMessage && (
          <div
            role="alert"
            aria-live="polite"
            className="rounded-md border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-900/30 px-3 py-2 text-sm text-red-700 dark:text-red-200"
          >
            {sendErrorMessage}
          </div>
        )}
        <div className="flex justify-end gap-3 pt-2">
          <Button type="button" variant="secondary" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            isLoading={sendEmailMutation.isPending}
            disabled={overLimit}
          >
            {replyTo ? 'Send Reply' : 'Send Email'}
          </Button>
        </div>
      </form>
    </Modal>
    {/* Sibling, not child — nesting ConfirmDialog inside <Modal> stacks two
        focus traps on the same DOM subtree and Tab/Escape ordering goes
        undefined. Pattern matches UserManagement / UserApprovalsPage. */}
    <ConfirmDialog
      isOpen={showDiscardConfirm}
      onClose={() => setShowDiscardConfirm(false)}
      onConfirm={() => {
        setShowDiscardConfirm(false);
        onClose();
      }}
      title="Discard email draft?"
      message="Your unsent changes will be lost."
      confirmLabel="Discard"
      cancelLabel="Keep editing"
      variant="danger"
    />
    </>
  );
}
