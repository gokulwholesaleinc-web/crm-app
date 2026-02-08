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
          <label htmlFor="email-to" className="block text-sm font-medium text-gray-700">
            To
          </label>
          <input
            id="email-to"
            type="email"
            required
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm text-sm focus:border-primary-500 focus:ring-primary-500"
            placeholder="recipient@example.com"
            autoComplete="email"
          />
        </div>

        <div>
          <label htmlFor="email-subject" className="block text-sm font-medium text-gray-700">
            Subject
          </label>
          <input
            id="email-subject"
            type="text"
            required
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm text-sm focus:border-primary-500 focus:ring-primary-500"
            placeholder="Email subject"
          />
        </div>

        <div>
          <label htmlFor="email-body" className="block text-sm font-medium text-gray-700">
            Body
          </label>
          <textarea
            id="email-body"
            required
            rows={8}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm text-sm focus:border-primary-500 focus:ring-primary-500"
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
