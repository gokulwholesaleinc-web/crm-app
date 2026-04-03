/**
 * Modal for adding selected leads to an existing or new campaign.
 */

import { useState } from 'react';
import { Modal, Button, Spinner } from '../../../components/ui';
import { Input } from '../../../components/ui/Input';
import { Select } from '../../../components/ui/Select';
import {
  useCampaigns,
  useCreateCampaign,
  useAddCampaignMembers,
} from '../../../hooks/useCampaigns';
import { showSuccess, showError } from '../../../utils/toast';
import type { CampaignCreate } from '../../../types';

interface AddToCampaignModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedLeadIds: number[];
  onSuccess?: () => void;
}

type Mode = 'select' | 'create';

const campaignTypeOptions = [
  { value: 'email', label: 'Email Campaign' },
  { value: 'event', label: 'Event' },
  { value: 'webinar', label: 'Webinar' },
  { value: 'social', label: 'Social Media' },
  { value: 'other', label: 'Other' },
];

export function AddToCampaignModal({
  isOpen,
  onClose,
  selectedLeadIds,
  onSuccess,
}: AddToCampaignModalProps) {
  const [mode, setMode] = useState<Mode>('select');
  const [selectedCampaignId, setSelectedCampaignId] = useState<number | null>(null);
  const [newName, setNewName] = useState('');
  const [newType, setNewType] = useState('email');

  const { data: campaignsData, isLoading: loadingCampaigns } = useCampaigns({ page: 1, page_size: 100 });
  const createCampaign = useCreateCampaign();
  const addMembers = useAddCampaignMembers();

  const campaigns = campaignsData?.items ?? [];
  const isSubmitting = createCampaign.isPending || addMembers.isPending;

  const handleSubmit = async () => {
    try {
      let campaignId: number;

      if (mode === 'create') {
        if (!newName.trim()) return;
        const created = await createCampaign.mutateAsync({
          name: newName.trim(),
          campaign_type: newType,
          status: 'planned',
          budget_currency: 'USD',
        } as CampaignCreate);
        campaignId = created.id;
      } else {
        if (!selectedCampaignId) return;
        campaignId = selectedCampaignId;
      }

      const result = await addMembers.mutateAsync({
        campaignId,
        data: { member_type: 'lead', member_ids: selectedLeadIds },
      });

      showSuccess(`${result.added} lead${result.added !== 1 ? 's' : ''} added to campaign`);
      onSuccess?.();
      handleClose();
    } catch {
      showError('Failed to add leads to campaign');
    }
  };

  const handleClose = () => {
    setMode('select');
    setSelectedCampaignId(null);
    setNewName('');
    setNewType('email');
    onClose();
  };

  const canSubmit = mode === 'select'
    ? selectedCampaignId !== null
    : newName.trim().length > 0;

  return (
    <Modal isOpen={isOpen} onClose={handleClose} title="Add to Campaign" size="md">
      <div className="space-y-4 p-4 sm:p-6">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Add {selectedLeadIds.length} selected lead{selectedLeadIds.length !== 1 ? 's' : ''} to a campaign.
        </p>

        {/* Mode toggle */}
        <div className="flex rounded-md border border-gray-300 dark:border-gray-600 overflow-hidden">
          <button
            type="button"
            onClick={() => setMode('select')}
            className={`flex-1 px-3 py-2 text-sm font-medium transition-colors ${
              mode === 'select'
                ? 'bg-primary-600 text-white'
                : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600'
            }`}
            aria-label="Select existing campaign"
          >
            Existing Campaign
          </button>
          <button
            type="button"
            onClick={() => setMode('create')}
            className={`flex-1 px-3 py-2 text-sm font-medium transition-colors border-l border-gray-300 dark:border-gray-600 ${
              mode === 'create'
                ? 'bg-primary-600 text-white'
                : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600'
            }`}
            aria-label="Create new campaign"
          >
            New Campaign
          </button>
        </div>

        {mode === 'select' && (
          <div>
            {loadingCampaigns ? (
              <div className="flex items-center justify-center py-4">
                <Spinner size="sm" />
              </div>
            ) : campaigns.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
                No campaigns found. Create a new one instead.
              </p>
            ) : (
              <div>
                <label htmlFor="select-campaign" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Select Campaign
                </label>
                <select
                  id="select-campaign"
                  value={selectedCampaignId ?? ''}
                  onChange={(e) => setSelectedCampaignId(e.target.value ? Number(e.target.value) : null)}
                  className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
                >
                  <option value="">-- Select a campaign --</option>
                  {campaigns.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({c.status})
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        )}

        {mode === 'create' && (
          <div className="space-y-3">
            <Input
              label="Campaign Name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Enter campaign name..."
            />
            <Select
              label="Campaign Type"
              value={newType}
              onChange={(e) => setNewType(e.target.value)}
              options={campaignTypeOptions}
            />
          </div>
        )}

        <div className="flex justify-end gap-3 pt-2 border-t border-gray-200 dark:border-gray-700">
          <Button variant="secondary" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!canSubmit || isSubmitting}
            isLoading={isSubmitting}
          >
            Add to Campaign
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export default AddToCampaignModal;
