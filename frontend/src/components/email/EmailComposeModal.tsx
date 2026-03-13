import { useState } from 'react';
import { Modal, Button } from '../ui';
import { useSendEmail } from '../../hooks/useEmail';

interface EmailComposeModalProps {
  isOpen: boolean;
  onClose: () => void;
  defaultTo?: string;
  entityType?: string;
  entityId?: number;
}

export function EmailComposeModal({
  isOpen,
  onClose,
  defaultTo = '',
  entityType,
  entityId,
}: EmailComposeModalProps) {
  const [to, setTo] = useState(defaultTo);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const sendEmailMutation = useSendEmail();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await sendEmailMutation.mutateAsync({
        to_email: to,
        subject,
        body,
        entity_type: entityType,
        entity_id: entityId,
      });
      setTo(defaultTo);
      setSubject('');
      setBody('');
      onClose();
    } catch {
      // Error handled by mutation
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Compose Email" size="lg">
      <form onSubmit={handleSubmit} className="space-y-4">
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
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 shadow-sm text-sm focus-visible:outline-none focus-visible:border-primary-500 focus-visible:ring-1 focus-visible:ring-primary-500"
            placeholder="recipient@example.com..."
            autoComplete="email"
            spellCheck={false}
          />
        </div>

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
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 shadow-sm text-sm focus-visible:outline-none focus-visible:border-primary-500 focus-visible:ring-1 focus-visible:ring-primary-500"
            placeholder="Email subject..."
            autoComplete="off"
          />
        </div>

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
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 shadow-sm text-sm focus-visible:outline-none focus-visible:border-primary-500 focus-visible:ring-1 focus-visible:ring-primary-500"
            placeholder="Write your email..."
          />
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" isLoading={sendEmailMutation.isPending}>
            Send Email
          </Button>
        </div>
      </form>
    </Modal>
  );
}
