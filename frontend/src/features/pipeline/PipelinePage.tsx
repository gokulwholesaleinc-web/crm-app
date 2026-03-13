import { useState, lazy, Suspense } from 'react';
import { useNavigate } from 'react-router-dom';
import { PlusIcon } from '@heroicons/react/24/outline';
import { Button, Spinner, Modal } from '../../components/ui';
import { OpportunityForm, OpportunityFormData } from '../opportunities/components/OpportunityForm';
const AIInsightsCard = lazy(() => import('../../components/ai').then(m => ({ default: m.AIInsightsCard })));
const NextBestActionCard = lazy(() => import('../../components/ai').then(m => ({ default: m.NextBestActionCard })));
import { useLeadKanban, useMoveLeadStage } from '../../hooks/useLeads';
import {
  useOpportunities,
  useKanban,
  useMoveOpportunity,
  usePipelineStages,
  useCreateOpportunity,
  useUpdateOpportunity,
} from '../../hooks/useOpportunities';
import { useContacts } from '../../hooks/useContacts';
import { useCompanies } from '../../hooks/useCompanies';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  formatCurrency,
  formatDate,
  formatPercentage,
  getStatusBadgeClasses,
} from '../../utils';
import { showError } from '../../utils/toast';
import type {
  Opportunity,
  OpportunityCreate,
  OpportunityUpdate,
  KanbanStage,
  KanbanOpportunity,
  KanbanLeadStage,
  KanbanLead,
} from '../../types';

// ---------------------------------------------------------------------------
// Kanban card components
// ---------------------------------------------------------------------------

function LeadCard({ lead, onClick }: { lead: KanbanLead; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left bg-blue-50 dark:bg-blue-900/20 rounded-lg shadow-sm border border-blue-200 dark:border-blue-800 p-3 hover:shadow-md transition-shadow duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
    >
      <div className="space-y-1.5">
        <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2">
          {lead.full_name}
        </h4>
        {lead.company_name && (
          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
            {lead.company_name}
          </p>
        )}
        {lead.email && (
          <p className="text-xs text-gray-400 dark:text-gray-500 truncate">
            {lead.email}
          </p>
        )}
        <div className="flex items-center gap-1.5">
          <span className="inline-flex items-center rounded-full bg-blue-100 dark:bg-blue-800 px-2 py-0.5 text-xs font-medium text-blue-700 dark:text-blue-300">
            Score: {lead.score}
          </span>
        </div>
      </div>
    </button>
  );
}

function OpportunityCard({ opportunity, onClick }: { opportunity: KanbanOpportunity; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left bg-emerald-50 dark:bg-emerald-900/20 rounded-lg shadow-sm border border-emerald-200 dark:border-emerald-800 p-3 hover:shadow-md transition-shadow duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
    >
      <div className="space-y-1.5">
        <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 line-clamp-2">
          {opportunity.name}
        </h4>
        {opportunity.company_name && (
          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
            {opportunity.company_name}
          </p>
        )}
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
            {formatCurrency(opportunity.amount ?? 0, opportunity.currency)}
          </span>
        </div>
        {opportunity.contact_name && (
          <div className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
            <svg className="h-3.5 w-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
            </svg>
            <span className="truncate">{opportunity.contact_name}</span>
          </div>
        )}
      </div>
    </button>
  );
}

// ---------------------------------------------------------------------------
// Kanban column components
// ---------------------------------------------------------------------------

function LeadStageColumn({ stage }: { stage: KanbanLeadStage }) {
  const navigate = useNavigate();
  const moveLead = useMoveLeadStage();

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const data = e.dataTransfer.getData('application/json');
    if (!data) return;
    try {
      const parsed = JSON.parse(data);
      if (parsed.entityType === 'lead' && parsed.sourceStageId !== stage.stage_id) {
        moveLead.mutate({ leadId: parsed.id, newStageId: stage.stage_id });
      }
    } catch {
      // ignore invalid drag data
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    if (e.dataTransfer.types.includes('application/json')) e.preventDefault();
  };

  return (
    <div className="w-full md:flex-shrink-0 md:w-72" onDrop={handleDrop} onDragOver={handleDragOver}>
      <div className="bg-blue-50/50 dark:bg-blue-950/30 rounded-lg p-3 h-full">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: stage.color }} aria-hidden="true" />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">{stage.stage_name}</h3>
          </div>
          <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0 ml-2">{stage.count}</span>
        </div>
        <div className="space-y-2 max-h-[calc(100vh-22rem)] overflow-y-auto">
          {stage.leads.map((lead) => (
            <div
              key={lead.id}
              draggable
              style={{ touchAction: 'manipulation' }}
              onDragStart={(e) => {
                e.dataTransfer.setData('application/json', JSON.stringify({ id: lead.id, entityType: 'lead', sourceStageId: stage.stage_id }));
              }}
            >
              <LeadCard lead={lead} onClick={() => navigate(`/leads/${lead.id}`)} />
            </div>
          ))}
          {stage.leads.length === 0 && (
            <p className="text-xs text-gray-400 dark:text-gray-500 text-center py-4">No leads</p>
          )}
        </div>
      </div>
    </div>
  );
}

function OpportunityStageColumn({ stage }: { stage: KanbanStage }) {
  const navigate = useNavigate();
  const moveOpp = useMoveOpportunity();

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    const data = e.dataTransfer.getData('application/json');
    if (!data) return;
    try {
      const parsed = JSON.parse(data);
      if (parsed.entityType === 'opportunity' && parsed.sourceStageId !== stage.stage_id) {
        moveOpp.mutate({ opportunityId: parsed.id, newStageId: stage.stage_id });
      }
    } catch {
      // ignore invalid drag data
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    if (e.dataTransfer.types.includes('application/json')) e.preventDefault();
  };

  return (
    <div className="w-full md:flex-shrink-0 md:w-72" onDrop={handleDrop} onDragOver={handleDragOver}>
      <div className="bg-emerald-50/50 dark:bg-emerald-950/30 rounded-lg p-3 h-full">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <div className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: stage.color }} aria-hidden="true" />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">{stage.stage_name}</h3>
          </div>
          <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0 ml-2">{stage.count}</span>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3" style={{ fontVariantNumeric: 'tabular-nums' }}>
          {formatCurrency(stage.total_amount ?? 0, 'USD')}
        </p>
        <div className="space-y-2 max-h-[calc(100vh-22rem)] overflow-y-auto">
          {stage.opportunities.map((opp) => (
            <div
              key={opp.id}
              draggable
              style={{ touchAction: 'manipulation' }}
              onDragStart={(e) => {
                e.dataTransfer.setData('application/json', JSON.stringify({ id: opp.id, entityType: 'opportunity', sourceStageId: stage.stage_id }));
              }}
            >
              <OpportunityCard opportunity={opp} onClick={() => navigate(`/opportunities/${opp.id}`)} />
            </div>
          ))}
          {stage.opportunities.length === 0 && (
            <p className="text-xs text-gray-400 dark:text-gray-500 text-center py-4">No deals</p>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Pipeline Page
// ---------------------------------------------------------------------------

function PipelinePage() {
  usePageTitle('Pipeline');
  const navigate = useNavigate();

  const [viewMode, setViewMode] = useState<'kanban' | 'list'>(() =>
    window.matchMedia('(min-width: 768px)').matches ? 'kanban' : 'list'
  );
  const [showForm, setShowForm] = useState(false);
  const [editingOpportunity, setEditingOpportunity] = useState<Opportunity | null>(null);

  // Kanban data
  const { data: leadKanban, isLoading: leadsLoading, error: leadsError } = useLeadKanban();
  const { data: oppKanban, isLoading: oppsLoading, error: oppsError } = useKanban();

  // List data (only fetch in list mode)
  const { data: opportunitiesData, isLoading: listLoading } = useOpportunities();
  const { data: pipelineStages } = usePipelineStages(true, 'opportunity');

  // Form dropdowns (only fetch when modal is open)
  const isModalOpen = showForm || !!editingOpportunity;
  const { data: contactsData } = useContacts({ page_size: 25 }, { enabled: isModalOpen });
  const { data: companiesData } = useCompanies({ page_size: 25 }, { enabled: isModalOpen });

  const createOpportunityMutation = useCreateOpportunity();
  const updateOpportunityMutation = useUpdateOpportunity();

  const isLoading = viewMode === 'kanban' ? (leadsLoading || oppsLoading) : listLoading;
  const error = leadsError || oppsError;

  // Pipeline summary from kanban data
  const oppStages = oppKanban?.stages ?? [];
  const leadStages = leadKanban?.stages ?? [];

  const totalPipelineValue = oppStages.reduce((sum, s) => sum + (s.total_amount ?? 0), 0);
  const openDeals = oppStages.reduce((sum, s) => sum + (s.count ?? 0), 0);
  const totalLeadsInPipeline = leadStages.reduce((sum, s) => sum + (s.count ?? 0), 0);

  // Opportunity list items for list view
  const opportunityItems = opportunitiesData?.items ?? [];

  // Form handlers — use numeric stage IDs directly (no slug conversion)
  const handleFormSubmit = async (data: OpportunityFormData) => {
    try {
      if (editingOpportunity) {
        const updateData: OpportunityUpdate = {
          name: data.name,
          amount: data.value,
          probability: data.probability,
          expected_close_date: data.expectedCloseDate || undefined,
          pipeline_stage_id: data.stage,
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
          pipeline_stage_id: data.stage,
          contact_id: data.contactId ? parseInt(data.contactId, 10) : undefined,
          company_id: data.companyId ? parseInt(data.companyId, 10) : undefined,
          description: data.description,
        };
        await createOpportunityMutation.mutateAsync(createData);
      }
      setShowForm(false);
      setEditingOpportunity(null);
    } catch (err) {
      showError('Failed to save opportunity');
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
      stage: editingOpportunity.pipeline_stage_id,
      probability: editingOpportunity.probability ?? 0,
      expectedCloseDate: editingOpportunity.expected_close_date ?? '',
      contactId: editingOpportunity.contact_id ? String(editingOpportunity.contact_id) : '',
      companyId: editingOpportunity.company_id ? String(editingOpportunity.company_id) : '',
      description: editingOpportunity.description ?? '',
    };
  };

  const contactsList = (contactsData?.items ?? []).map((c) => ({
    id: String(c.id),
    name: `${c.first_name} ${c.last_name}`,
  }));

  const companiesList = (companiesData?.items ?? []).map((c) => ({
    id: String(c.id),
    name: c.name,
  }));

  const hasKanbanData = leadStages.length > 0 || oppStages.length > 0;

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Pipeline</h1>
          <p className="mt-0.5 sm:mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            Track leads and deals across all pipeline stages
          </p>
        </div>
        <div className="flex items-center justify-between sm:justify-end gap-3">
          {/* View Toggle */}
          <div className="flex items-center bg-gray-100 dark:bg-gray-700 rounded-lg p-1">
            <button
              type="button"
              onClick={() => setViewMode('kanban')}
              className={`px-2 sm:px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                viewMode === 'kanban'
                  ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
              }`}
              aria-label="Kanban view"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
              </svg>
            </button>
            <button
              type="button"
              onClick={() => setViewMode('list')}
              className={`px-2 sm:px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                viewMode === 'list'
                  ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
              }`}
              aria-label="List view"
            >
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 10h16M4 14h16M4 18h16" />
              </svg>
            </button>
          </div>

          <Button leftIcon={<PlusIcon className="h-5 w-5" />} onClick={() => setShowForm(true)}>
            <span className="hidden sm:inline">Add Opportunity</span>
            <span className="sm:hidden">Add</span>
          </Button>
        </div>
      </div>

      {/* Pipeline Summary */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4 sm:p-6 border border-transparent dark:border-gray-700">
        <div className="grid grid-cols-1 gap-4 sm:gap-6 sm:grid-cols-3">
          <div>
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Total Pipeline Value</p>
            <p className="mt-1 sm:mt-2 text-2xl sm:text-3xl font-semibold text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
              {formatCurrency(totalPipelineValue, 'USD')}
            </p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Open Deals</p>
            <p className="mt-1 sm:mt-2 text-2xl sm:text-3xl font-semibold text-gray-900 dark:text-gray-100">
              {openDeals}
            </p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Active Leads</p>
            <p className="mt-1 sm:mt-2 text-2xl sm:text-3xl font-semibold text-gray-900 dark:text-gray-100">
              {totalLeadsInPipeline}
            </p>
          </div>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
          <p className="text-sm font-medium text-red-800 dark:text-red-300">
            {error instanceof Error ? error.message : 'Failed to load pipeline data'}
          </p>
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <Spinner size="lg" />
        </div>
      ) : viewMode === 'kanban' ? (
        /* ---- KANBAN VIEW ---- */
        !hasKanbanData ? (
          <div className="text-center py-12">
            <p className="text-sm text-gray-500 dark:text-gray-400">
              No pipeline stages configured. Create pipeline stages in settings.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto pb-4">
            <div className="flex flex-col md:flex-row gap-3 md:min-w-max items-start">
              {/* Lead pipeline stages */}
              {leadStages.length > 0 && (
                <>
                  <div className="flex flex-col md:flex-row gap-3">
                    {leadStages.map((stage) => (
                      <LeadStageColumn key={`lead-${stage.stage_id}`} stage={stage} />
                    ))}
                  </div>

                  {/* Separator between leads and opportunities */}
                  {oppStages.length > 0 && (
                    <div className="flex flex-col items-center justify-start pt-8 px-1 shrink-0">
                      <div className="w-px h-16 bg-gray-300 dark:bg-gray-600" />
                      <div className="my-2 px-2 py-1 rounded-full bg-gray-200 dark:bg-gray-700 text-xs font-medium text-gray-600 dark:text-gray-300 whitespace-nowrap">
                        Conversion
                      </div>
                      <svg className="w-4 h-4 text-gray-400 dark:text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                      </svg>
                      <div className="w-px h-16 bg-gray-300 dark:bg-gray-600" />
                    </div>
                  )}
                </>
              )}

              {/* Opportunity pipeline stages */}
              {oppStages.length > 0 && (
                <div className="flex flex-col md:flex-row gap-3">
                  {oppStages.map((stage) => (
                    <OpportunityStageColumn key={`opp-${stage.stage_id}`} stage={stage} />
                  ))}
                </div>
              )}
            </div>

            {/* Legend */}
            <div className="flex items-center gap-6 mt-4 pt-3 border-t border-gray-200 dark:border-gray-700">
              {leadStages.length > 0 && (
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded bg-blue-100 dark:bg-blue-900/40 border border-blue-300 dark:border-blue-700" />
                  <span className="text-xs text-gray-500 dark:text-gray-400">Leads</span>
                </div>
              )}
              {oppStages.length > 0 && (
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded bg-emerald-100 dark:bg-emerald-900/40 border border-emerald-300 dark:border-emerald-700" />
                  <span className="text-xs text-gray-500 dark:text-gray-400">Opportunities</span>
                </div>
              )}
            </div>
          </div>
        )
      ) : (
        /* ---- LIST VIEW ---- */
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700">
          {opportunityItems.length === 0 ? (
            <div className="text-center py-12 px-4">
              <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">No opportunities</h3>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Get started by creating a new opportunity.</p>
              <div className="mt-6">
                <Button onClick={() => setShowForm(true)}>Add Opportunity</Button>
              </div>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-900">
                  <tr>
                    <th scope="col" className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Opportunity</th>
                    <th scope="col" className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Value</th>
                    <th scope="col" className="px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Stage</th>
                    <th scope="col" className="hidden sm:table-cell px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Probability</th>
                    <th scope="col" className="hidden md:table-cell px-4 sm:px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Close Date</th>
                    <th scope="col" className="relative px-4 sm:px-6 py-3"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {opportunityItems.map((opp) => {
                    const stageName = opp.pipeline_stage?.name?.toLowerCase().replace(/\s+/g, '_') ?? '';
                    return (
                      <tr
                        key={opp.id}
                        className="hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer"
                        onClick={() => navigate(`/opportunities/${opp.id}`)}
                      >
                        <td className="px-4 sm:px-6 py-4">
                          <div className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate max-w-[150px] sm:max-w-none">{opp.name}</div>
                          {opp.company?.name && (
                            <div className="text-sm text-gray-500 dark:text-gray-400 truncate max-w-[150px] sm:max-w-none">{opp.company.name}</div>
                          )}
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
                          {formatCurrency(opp.amount ?? 0, opp.currency ?? 'USD')}
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                          <span className={getStatusBadgeClasses(stageName, 'opportunity')}>
                            {opp.pipeline_stage?.name ?? stageName}
                          </span>
                        </td>
                        <td className="hidden sm:table-cell px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                          {formatPercentage(opp.probability ?? 0)}
                        </td>
                        <td className="hidden md:table-cell px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                          {formatDate(opp.expected_close_date)}
                        </td>
                        <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setEditingOpportunity(opp);
                              setShowForm(true);
                            }}
                            className="text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300"
                          >
                            Edit
                          </button>
                        </td>
                      </tr>
                    );
                  })}
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
          {editingOpportunity && (
            <Suspense fallback={<div className="animate-pulse h-32 bg-gray-100 dark:bg-gray-700 rounded-lg" />}>
              <div className="space-y-4">
                <NextBestActionCard entityType="opportunity" entityId={editingOpportunity.id} />
                <AIInsightsCard entityType="opportunity" entityId={editingOpportunity.id} entityName={editingOpportunity.name} variant="inline" />
              </div>
            </Suspense>
          )}

          <OpportunityForm
            initialData={getInitialFormData()}
            onSubmit={handleFormSubmit}
            onCancel={handleFormCancel}
            isLoading={createOpportunityMutation.isPending || updateOpportunityMutation.isPending}
            submitLabel={editingOpportunity ? 'Update Opportunity' : 'Create Opportunity'}
            contacts={contactsList}
            companies={companiesList}
          />
        </div>
      </Modal>
    </div>
  );
}

export default PipelinePage;
