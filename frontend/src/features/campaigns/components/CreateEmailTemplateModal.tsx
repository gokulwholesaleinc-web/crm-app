/**
 * Inline modal for creating an EmailTemplate from inside CampaignStepBuilder
 * so users don't get stuck at "Select template..." with an empty dropdown.
 *
 * The body field accepts plain text or HTML — the campaign send path runs
 * the value through render_template() which is HTML-safe for both.
 */

import { useState } from 'react';
import { Button, Input, Modal, ModalFooter } from '../../../components/ui';
import { showError } from '../../../utils/toast';
import { useCreateEmailTemplate } from '../../../hooks/useCampaigns';
import type { ApiError, EmailTemplate } from '../../../types';

interface CreateEmailTemplateModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreated: (template: EmailTemplate) => void;
}

export function CreateEmailTemplateModal({
  isOpen,
  onClose,
  onCreated,
}: CreateEmailTemplateModalProps) {
  const [name, setName] = useState('');
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');
  const createTemplate = useCreateEmailTemplate();

  const reset = () => {
    setName('');
    setSubject('');
    setBody('');
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedName = name.trim();
    const trimmedSubject = subject.trim();
    const trimmedBody = body.trim();
    if (!trimmedName || !trimmedSubject || !trimmedBody) {
      showError('Name, subject and body are all required.');
      return;
    }
    try {
      const created = await createTemplate.mutateAsync({
        name: trimmedName,
        subject_template: trimmedSubject,
        body_template: trimmedBody,
      });
      onCreated(created);
      reset();
    } catch (err) {
      // ApiError.detail is populated by the axios interceptor — surface
      // it so 422 validation messages or name conflicts reach the user.
      const detail = (err as Partial<ApiError>).detail;
      showError(detail || 'Failed to create template.');
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="New Email Template" size="lg">
      <form onSubmit={handleSubmit} className="space-y-4">
        <Input
          label="Template name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Welcome email"
          autoFocus
          required
        />
        <Input
          label="Subject"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="Welcome to {{company_name}}"
          helperText="Variables like {{first_name}} are filled in at send time."
          required
        />
        <div className="w-full">
          <label
            htmlFor="email-template-body"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            Body
          </label>
          <textarea
            id="email-template-body"
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={10}
            required
            className="block w-full rounded-md border-gray-300 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm font-mono"
            placeholder={'Hi {{first_name}},\n\nThanks for connecting…'}
          />
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Plain text or HTML. Variables use double-curly braces.
          </p>
        </div>
        <ModalFooter>
          <Button type="button" variant="secondary" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="submit" isLoading={createTemplate.isPending}>
            Create Template
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}
