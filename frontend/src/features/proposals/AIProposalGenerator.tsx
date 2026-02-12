import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { SparklesIcon } from '@heroicons/react/24/outline';
import { Button, SearchableSelect } from '../../components/ui';
import { useOpportunities } from '../../hooks/useOpportunities';
import { useGenerateProposal } from '../../hooks/useProposals';
import { showSuccess, showError } from '../../utils/toast';

interface AIProposalGeneratorProps {
  onClose: () => void;
}

export function AIProposalGenerator({ onClose }: AIProposalGeneratorProps) {
  const navigate = useNavigate();
  const [selectedOpportunityId, setSelectedOpportunityId] = useState<number | null>(null);
  const { data: opportunitiesData, isLoading: loadingOpps } = useOpportunities({ page_size: 100 });
  const generateMutation = useGenerateProposal();

  const opportunities = opportunitiesData?.items ?? [];

  const opportunityOptions = useMemo(
    () =>
      opportunities.map((opp) => {
        let label = opp.name;
        if (opp.company) label += ` - ${opp.company.name}`;
        if (opp.amount) label += ` ($${opp.amount.toLocaleString()})`;
        return { value: opp.id, label };
      }),
    [opportunities]
  );

  const handleGenerate = async () => {
    if (!selectedOpportunityId) return;

    try {
      const proposal = await generateMutation.mutateAsync({
        opportunity_id: selectedOpportunityId,
      });
      showSuccess('Proposal generated successfully');
      onClose();
      navigate(`/proposals/${proposal.id}`);
    } catch {
      showError('Failed to generate proposal');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 text-primary-600 dark:text-primary-400">
        <SparklesIcon className="h-6 w-6" aria-hidden="true" />
        <h3 className="text-lg font-medium">AI Proposal Generator</h3>
      </div>

      <p className="text-sm text-gray-600 dark:text-gray-400">
        Select an opportunity to generate a professional proposal using AI. The generator will use
        opportunity details, contact information, company data, and any linked quotes to create
        tailored proposal content.
      </p>

      <div>
        {loadingOpps ? (
          <div>
            <span className="block text-sm font-medium text-gray-700 dark:text-gray-300">Select Opportunity *</span>
            <div className="mt-1 animate-pulse h-10 bg-gray-200 dark:bg-gray-700 rounded-md" />
          </div>
        ) : (
          <SearchableSelect
            label="Select Opportunity *"
            id="ai-opportunity-select"
            name="opportunity_id"
            value={selectedOpportunityId}
            onChange={setSelectedOpportunityId}
            options={opportunityOptions}
            placeholder="Search opportunities..."
          />
        )}
      </div>

      {opportunities.length === 0 && !loadingOpps && (
        <div className="rounded-md bg-yellow-50 dark:bg-yellow-900/20 p-4">
          <p className="text-sm text-yellow-700 dark:text-yellow-300">
            No opportunities found. Create an opportunity first to generate a proposal.
          </p>
        </div>
      )}

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button type="button" variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button
          onClick={handleGenerate}
          disabled={!selectedOpportunityId || generateMutation.isPending}
          leftIcon={<SparklesIcon className="h-4 w-4" />}
        >
          {generateMutation.isPending ? 'Generating...' : 'Generate Proposal'}
        </Button>
      </div>
    </div>
  );
}
