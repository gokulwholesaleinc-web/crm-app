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
  const [toEmail, setToEmail] = useState(defaultTo);
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const sendEmail = useSendEmail();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await sendEmail.mutateAsync({
      to_email: toEmail,
      subject,
      body,
      entity_type: entityType,
      entity_id: entityId,
    });
    setToEmail('');
    setSubject('');
    setBody('');
    onClose();
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Send Email" size="lg">
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label htmlFor="email-to" className="block text-sm font-medium text-gray-700">
            To
          </label>
          <input
            id="email-to"
            type="email"
            required
            value={toEmail}
            onChange={(e) => setToEmail(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            placeholder="recipient@example.com"
            autoComplete="email"
            name="to"
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
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            placeholder="Email subject"
            name="subject"
          />
        </div>
        <div>
          <label htmlFor="email-body" className="block text-sm font-medium text-gray-700">
            Body
          </label>
          <textarea
            id="email-body"
            required
            rows={6}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
            placeholder="Write your email..."
            name="body"
          />
        </div>
        <div className="flex justify-end gap-3 pt-2">
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" isLoading={sendEmail.isPending}>
            Send Email
          </Button>
        </div>
      </form>
    </Modal>
  );
}
