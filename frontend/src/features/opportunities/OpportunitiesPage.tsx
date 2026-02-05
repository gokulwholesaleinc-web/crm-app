import { useState } from 'react';
import { PlusIcon } from '@heroicons/react/24/outline';
import { Button, Spinner, Modal } from '../../components/ui';
import {
  KanbanBoard,
  KanbanStage,
} from './components/KanbanBoard/KanbanBoard';
import { Opportunity as KanbanOpportunity } from './components/KanbanBoard/KanbanCard';
import { OpportunityForm, OpportunityFormData } from './components/OpportunityForm';
import { AIInsightsCard, NextBestActionCard } from '../../components/ai';
import {
  useOpportunities,
  useMoveOpportunity,
  usePipelineStages,
  useCreateOpportunity,
  useUpdateOpportunity,
  useContacts,
  useCompanies,
} from '../../hooks';
import {
  formatCurrency,
  formatDate,
  formatPercentage,
  getStatusBadgeClasses,
} from '../../utils';
import type { Opportunity, OpportunityCreate, OpportunityUpdate } from '../../types';

const defaultStages: KanbanStage[] = [
  { id: 'qualification', title: 'Qualification', color: 'blue' },
  { id: 'needs_analysis', title: 'Needs Analysis', color: 'yellow' },
  { id: 'proposal', title: 'Proposal', color: 'purple' },
  { id: 'negotiation', title: 'Negotiation', color: 'orange' },
  { id: 'closed_won', title: 'Closed Won', color: 'green' },
  { id: 'closed_lost', title: 'Closed Lost', color: 'red' },
];

function OpportunitiesPage() {
  const [viewMode, setViewMode] = useState<'kanban' | 'list'>('kanban');
  const [showForm, setShowForm] = useState(false);
  const [editingOpportunity, setEditingOpportunity] = useState<Opportunity | null>(null);

  // Use the hooks for data fetching
  const {
    data: opportunitiesData,
    isLoading,
    error,
  } = useOpportunities();

  const { data: pipelineStages } = usePipelineStages();
  const { data: contactsData } = useContacts({ page_size: 100 });
  const { data: companiesData } = useCompanies({ page_size: 100 });

  const moveOpportunityMutation = useMoveOpportunity();
  const createOpportunityMutation = useCreateOpportunity();
  const updateOpportunityMutation = useUpdateOpportunity();

  // Build stages from pipeline stages or use defaults
  const stages: KanbanStage[] = pipelineStages
    ? pipelineStages.map((stage) => ({
        id: stage.name.toLowerCase().replace(/\s+/g, '_'),
        title: stage.name,
        color: stage.color as 'blue' | 'yellow' | 'purple' | 'orange' | 'green' | 'red',
      }))
    : defaultStages;

  // Transform opportunities to Kanban format
  const opportunities: KanbanOpportunity[] = (opportunitiesData?.items ?? []).map((item: Opportunity) => ({
    id: String(item.id),
    name: item.name,
    value: item.amount ?? 0,
    stage: item.pipeline_stage?.name?.toLowerCase().replace(/\s+/g, '_') ?? 'qualification',
    probability: item.probability ?? 0,
    expectedCloseDate: item.expected_close_date ?? undefined,
    contactName: item.contact?.full_name ?? undefined,
    companyName: item.company?.name ?? undefined,
  }));

  const handleOpportunityMove = async (
    opportunityId: string,
    newStage: string,
    _newIndex: number
  ) => {
    try {
      // Find the stage ID from the stage name
      const stage = pipelineStages?.find(
        (s) => s.name.toLowerCase().replace(/\s+/g, '_') === newStage
      );
      if (!stage) {
        throw new Error('Pipeline stage not found');
      }

      await moveOpportunityMutation.mutateAsync({
        opportunityId: parseInt(opportunityId, 10),
        newStageId: stage.id,
      });
    } catch (err) {
      console.error('Failed to move opportunity:', err);
      throw err;
    }
  };

  const handleOpportunityClick = (opportunity: KanbanOpportunity) => {
    // Find the full opportunity data to show details or edit
    const fullOpportunity = opportunitiesData?.items?.find(
      (item) => String(item.id) === opportunity.id
    );
    if (fullOpportunity) {
      setEditingOpportunity(fullOpportunity);
      setShowForm(true);
    }
  };

  const handleEdit = (opportunity: Opportunity) => {
    setEditingOpportunity(opportunity);
    setShowForm(true);
  };

  const handleFormSubmit = async (data: OpportunityFormData) => {
    try {
      // Find the stage ID from the stage name
      const stage = pipelineStages?.find(
        (s) => s.name.toLowerCase().replace(/\s+/g, '_') === data.stage
      );

      if (editingOpportunity) {
        const updateData: OpportunityUpdate = {
          name: data.name,
          amount: data.value,
          probability: data.probability,
          expected_close_date: data.expectedCloseDate || undefined,
          pipeline_stage_id: stage?.id,
          contact_id: data.contactId ? parseInt(data.contactId, 10) : undefined,
          company_id: data.companyId ? parseInt(data.companyId, 10) : undefined,
          description: data.description,
        };
        await updateOpportunityMutation.mutateAsync({
          id: editingOpportunity.id,
          data: updateData,
        });
      } else {
        const createData: OpportunityCreate = {
          name: data.name,
          amount: data.value,
          currency: 'USD',
          probability: data.probability,
          expected_close_date: data.expectedCloseDate || undefined,
          pipeline_stage_id: stage?.id || 1,
          contact_id: data.contactId ? parseInt(data.contactId, 10) : undefined,
          company_id: data.companyId ? parseInt(data.companyId, 10) : undefined,
          description: data.description,
        };
        await createOpportunityMutation.mutateAsync(createData);
      }
      setShowForm(false);
      setEditingOpportunity(null);
    } catch (err) {
      console.error('Failed to save opportunity:', err);
    }
  };

  const handleFormCancel = () => {
    setShowForm(false);
    setEditingOpportunity(null);
  };

  const getInitialFormData = (): Partial<OpportunityFormData> | undefined => {
    if (!editingOpportunity) return undefined;
    return {
      name: editingOpportunity.name,
      value: editingOpportunity.amount ?? 0,
      stage: editingOpportunity.pipeline_stage?.name?.toLowerCase().replace(/\s+/g, '_') ?? 'qualification',
      probability: editingOpportunity.probability ?? 0,
      expectedCloseDate: editingOpportunity.expected_close_date ?? '',
      contactId: editingOpportunity.contact_id ? String(editingOpportunity.contact_id) : '',
      companyId: editingOpportunity.company_id ? String(editingOpportunity.company_id) : '',
      description: editingOpportunity.description ?? '',
    };
  };

  // Build contacts list for form dropdown
  const contactsList = (contactsData?.items ?? []).map((contact) => ({
    id: String(contact.id),
    name: `${contact.first_name} ${contact.last_name}`,
  }));

  // Build companies list for form dropdown
  const companiesList = (companiesData?.items ?? []).map((company) => ({
    id: String(company.id),
    name: company.name,
  }));

  const totalPipelineValue = opportunities
    .filter((o) => !['closed_won', 'closed_lost'].includes(o.stage))
    .reduce((sum, o) => sum + o.value, 0);

  const weightedPipelineValue = opportunities
    .filter((o) => !['closed_won', 'closed_lost'].includes(o.stage))
    .reduce((sum, o) => sum + o.value * (o.probability / 100), 0);

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900">Opportunities</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage your sales pipeline
          </p>
        </div>
        <div className="flex items-center justify-between sm:justify-end gap-3">
          {/* View Toggle */}
          <div className="flex items-center bg-gray-100 rounded-lg p-1">
            <button
              onClick={() => setViewMode('kanban')}
              className={`px-2 sm:px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                viewMode === 'kanban'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
              aria-label="Kanban view"
            >
              <svg
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2"
                />
              </svg>
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`px-2 sm:px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                viewMode === 'list'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
              aria-label="List view"
            >
              <svg
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M4 6h16M4 10h16M4 14h16M4 18h16"
                />
              </svg>
            </button>
          </div>

          <Button
            leftIcon={<PlusIcon className="h-5 w-5" />}
            onClick={() => setShowForm(true)}
          >
            <span className="hidden sm:inline">Add Opportunity</span>
            <span className="sm:hidden">Add</span>
          </Button>
        </div>
      </div>

      {/* Pipeline Summary */}
      <div className="bg-white shadow rounded-lg p-4 sm:p-6">
        <div className="grid grid-cols-1 gap-4 sm:gap-6 sm:grid-cols-3">
          <div>
            <p className="text-sm font-medium text-gray-500">
              Total Pipeline Value
            </p>
            <p className="mt-1 sm:mt-2 text-2xl sm:text-3xl font-semibold text-gray-900">
              {formatCurrency(totalPipelineValue)}
            </p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">
              Weighted Pipeline Value
            </p>
            <p className="mt-1 sm:mt-2 text-2xl sm:text-3xl font-semibold text-gray-900">
              {formatCurrency(weightedPipelineValue)}
            </p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">
              Open Opportunities
            </p>
            <p className="mt-1 sm:mt-2 text-2xl sm:text-3xl font-semibold text-gray-900">
              {
                opportunities.filter(
                  (o) => !['closed_won', 'closed_lost'].includes(o.stage)
                ).length
              }
            </p>
          </div>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="rounded-md bg-red-50 p-4">
          <div className="flex">
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">
                {error instanceof Error ? error.message : 'An error occurred'}
              </h3>
            </div>
          </div>
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <Spinner size="lg" />
        </div>
      ) : viewMode === 'kanban' ? (
        <div className="-mx-4 sm:mx-0 overflow-x-auto">
          <div className="px-4 sm:px-0">
            <KanbanBoard
              stages={stages}
              opportunities={opportunities}
              onOpportunityMove={handleOpportunityMove}
              onOpportunityClick={handleOpportunityClick}
            />
          </div>
        </div>
      ) : (
        /* List View */
        <div className="bg-white shadow rounded-lg overflow-hidden">
          {opportunities.length === 0 ? (
            <div className="text-center py-12 px-4">
              <svg
                className="mx-auto h-12 w-12 text-gray-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <h3 className="mt-2 text-sm font-medium text-gray-900">
                No opportunities
              </h3>
              <p className="mt-1 text-sm text-gray-500">
                Get started by creating a new opportunity.
              </p>
              <div className="mt-6">
                <Button onClick={() => setShowForm(true)}>
                  Add Opportunity
                </Button>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th
                      scope="col"
                      className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Opportunity
                    </th>
                    <th
                      scope="col"
                      className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Value
                    </th>
                    <th
                      scope="col"
                      className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Stage
                    </th>
                    <th
                      scope="col"
                      className="hidden sm:table-cell px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Probability
                    </th>
                    <th
                      scope="col"
                      className="hidden md:table-cell px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                    >
                      Close Date
                    </th>
                    <th scope="col" className="relative px-4 sm:px-6 py-3">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {opportunities.map((opportunity) => (
                    <tr
                      key={opportunity.id}
                      className="hover:bg-gray-50 cursor-pointer"
                      onClick={() => handleOpportunityClick(opportunity)}
                    >
                      <td className="px-4 sm:px-6 py-4">
                        <div className="text-sm font-medium text-gray-900 truncate max-w-[150px] sm:max-w-none">
                          {opportunity.name}
                        </div>
                        {opportunity.companyName && (
                          <div className="text-sm text-gray-500 truncate max-w-[150px] sm:max-w-none">
                            {opportunity.companyName}
                          </div>
                        )}
                      </td>
                      <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        {formatCurrency(opportunity.value)}
                      </td>
                      <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                        <span className={getStatusBadgeClasses(opportunity.stage, 'opportunity')}>
                          {stages.find((s) => s.id === opportunity.stage)
                            ?.title || opportunity.stage}
                        </span>
                      </td>
                      <td className="hidden sm:table-cell px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {formatPercentage(opportunity.probability)}
                      </td>
                      <td className="hidden md:table-cell px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {formatDate(opportunity.expectedCloseDate)}
                      </td>
                      <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            const fullOpportunity = opportunitiesData?.items?.find(
                              (item) => String(item.id) === opportunity.id
                            );
                            if (fullOpportunity) {
                              handleEdit(fullOpportunity);
                            }
                          }}
                          className="text-primary-600 hover:text-primary-900"
                        >
                          Edit
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Form Modal */}
      <Modal
        isOpen={showForm}
        onClose={handleFormCancel}
        title={editingOpportunity ? 'Edit Opportunity' : 'Add Opportunity'}
        size="full"
        fullScreenOnMobile
      >
        <div className="space-y-6">
          {/* AI Insights Section - Only show when editing an existing opportunity */}
          {editingOpportunity && (
            <div className="space-y-4">
              {/* Next Best Action */}
              <NextBestActionCard
                entityType="opportunity"
                entityId={editingOpportunity.id}
              />

              {/* AI Insights Card */}
              <AIInsightsCard
                entityType="opportunity"
                entityId={editingOpportunity.id}
                entityName={editingOpportunity.name}
                variant="inline"
              />
            </div>
          )}

          <OpportunityForm
            initialData={getInitialFormData()}
            onSubmit={handleFormSubmit}
            onCancel={handleFormCancel}
            isLoading={
              createOpportunityMutation.isPending || updateOpportunityMutation.isPending
            }
            submitLabel={editingOpportunity ? 'Update Opportunity' : 'Create Opportunity'}
            contacts={contactsList}
            companies={companiesList}
          />
        </div>
      </Modal>
    </div>
  );
}

export default OpportunitiesPage;
