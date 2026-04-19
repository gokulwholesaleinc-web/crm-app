import { useState, useEffect } from 'react';
import { Modal, Button } from '../ui';
import { useSendEmail } from '../../hooks/useEmail';
import type { ThreadEmailItem } from '../../types/email';

interface EmailComposeModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultTo?: string;
  entityType?: string;
  entityId?: number;
  replyTo?: ThreadEmailItem | null;
  fromEmail?: string;
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
  const sendEmailMutation = useSendEmail();

  // Pre-fill on mount and whenever the reply target changes.
  // Intentionally excludes `defaultTo` from deps so a parent re-render with
  // a new default recipient doesn't wipe in-progress edits mid-compose.
  useEffect(() => {
    if (replyTo) {
      // For outbound replyTo, from_email is the CRM user's own address —
      // continuing the thread means sending back to the original recipient.
      const replyRecipient =
        replyTo.direction === 'outbound'
          ? replyTo.to_email
          : replyTo.from_email || '';
      setTo(replyRecipient);
      setSubject(
        replyTo.subject.startsWith('Re: ')
          ? replyTo.subject
          : `Re: ${replyTo.subject}`
      );
      setBody('');
      setCc(replyTo.cc || '');
      setShowCcBcc(!!replyTo.cc);
    } else {
      setTo(defaultTo);
      setSubject('');
      setBody('');
      setCc('');
      setBcc('');
      setShowCcBcc(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replyTo]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await sendEmailMutation.mutateAsync({
        to_email: to,
        subject,
        body,
        from_email: fromEmail || undefined,
        cc: cc || undefined,
        bcc: bcc || undefined,
        entity_type: entityType,
        entity_id: entityId,
      });
      setTo(defaultTo);
      setSubject('');
      setBody('');
      setCc('');
      setBcc('');
      setShowCcBcc(false);
      onClose();
    } catch {
      // Error handled by mutation
    }
  };

  const inputClass =
    'mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 shadow-sm text-sm focus-visible:outline-none focus-visible:border-primary-500 focus-visible:ring-1 focus-visible:ring-primary-500';

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={replyTo ? 'Reply to Email' : 'Compose Email'}
      size="lg"
    >
      <form onSubmit={handleSubmit} className="space-y-4">
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
            placeholder="Write your email..."
          />
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" isLoading={sendEmailMutation.isPending}>
            {replyTo ? 'Send Reply' : 'Send Email'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
