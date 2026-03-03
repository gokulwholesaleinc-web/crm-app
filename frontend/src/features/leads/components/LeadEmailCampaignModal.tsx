import { useState } from 'react';
import { Modal, Button } from '../../../components/ui';
import { useSendCampaign } from '../../../hooks/useLeads';
import { showSuccess, showError } from '../../../utils/toast';

interface LeadEmailCampaignModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedLeadIds: number[];
}

export function LeadEmailCampaignModal({ isOpen, onClose, selectedLeadIds }: LeadEmailCampaignModalProps) {
  const [subject, setSubject] = useState('');
  const [bodyTemplate, setBodyTemplate] = useState('');
  const sendCampaign = useSendCampaign();

  const handleSend = async () => {
    if (!subject.trim() || !bodyTemplate.trim()) return;
    try {
      const result = await sendCampaign.mutateAsync({
        lead_ids: selectedLeadIds,
        subject: subject.trim(),
        body_template: bodyTemplate.trim(),
      });
      showSuccess(`Campaign sent to ${result.sent_count} leads`);
      if (result.errors.length > 0) {
        showError(`${result.errors.length} leads could not be reached`);
      }
      setSubject('');
      setBodyTemplate('');
      onClose();
    } catch {
      showError('Failed to send campaign');
    }
  };

  const preview = bodyTemplate
    .replace(/\{\{first_name\}\}/g, 'John')
    .replace(/\{\{last_name\}\}/g, 'Doe')
    .replace(/\{\{full_name\}\}/g, 'John Doe')
    .replace(/\{\{email\}\}/g, 'john@example.com')
    .replace(/\{\{company_name\}\}/g, 'Acme Corp');

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Send Email Campaign" size="lg">
      <div className="space-y-4">
        <div>
          <p className="text-sm text-gray-500 mb-4">
            Send personalized emails to {selectedLeadIds.length} selected lead{selectedLeadIds.length !== 1 ? 's' : ''}.
          </p>
        </div>

        <div>
          <label htmlFor="campaign-subject" className="block text-sm font-medium text-gray-700">
            Subject
          </label>
          <input
            id="campaign-subject"
            type="text"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
            placeholder="e.g., Special offer for {{first_name}}..."
          />
        </div>

        <div>
          <label htmlFor="campaign-body" className="block text-sm font-medium text-gray-700">
            Email Body
          </label>
          <textarea
            id="campaign-body"
            rows={6}
            value={bodyTemplate}
            onChange={(e) => setBodyTemplate(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
            placeholder="Hi {{first_name}},&#10;&#10;We have an exciting offer for you..."
          />
          <p className="mt-1 text-xs text-gray-400">
            Available placeholders: {'{{first_name}}'}, {'{{last_name}}'}, {'{{full_name}}'}, {'{{email}}'}, {'{{company_name}}'}
          </p>
        </div>

        {bodyTemplate.trim() && (
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Preview</label>
            <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700 whitespace-pre-wrap">
              {preview}
            </div>
          </div>
        )}

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={handleSend}
            disabled={!subject.trim() || !bodyTemplate.trim() || sendCampaign.isPending}
            isLoading={sendCampaign.isPending}
          >
            Send to {selectedLeadIds.length} Lead{selectedLeadIds.length !== 1 ? 's' : ''}
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export default LeadEmailCampaignModal;
