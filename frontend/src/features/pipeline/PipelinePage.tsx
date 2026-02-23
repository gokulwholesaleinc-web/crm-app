import { useNavigate } from 'react-router-dom';
import { Spinner } from '../../components/ui';
import { useLeadKanban, useMoveLeadStage } from '../../hooks/useLeads';
import { useKanban, useMoveOpportunity } from '../../hooks/useOpportunities';
import { usePageTitle } from '../../hooks/usePageTitle';
import { formatCurrency } from '../../utils/formatters';
import type { KanbanStage, KanbanOpportunity, KanbanLeadStage, KanbanLead } from '../../types';

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
    const types = e.dataTransfer.types;
    if (types.includes('application/json')) {
      e.preventDefault();
    }
  };

  return (
    <div
      className="flex-shrink-0 w-64 sm:w-72"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
    >
      <div className="bg-blue-50/50 dark:bg-blue-950/30 rounded-lg p-3 h-full">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <div
              className="w-3 h-3 rounded-full shrink-0"
              style={{ backgroundColor: stage.color }}
              aria-hidden="true"
            />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
              {stage.stage_name}
            </h3>
          </div>
          <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0 ml-2">
            {stage.count}
          </span>
        </div>
        <div className="space-y-2 max-h-[calc(100vh-18rem)] overflow-y-auto">
          {stage.leads.map((lead) => (
            <div
              key={lead.id}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData(
                  'application/json',
                  JSON.stringify({ id: lead.id, entityType: 'lead', sourceStageId: stage.stage_id })
                );
              }}
            >
              <LeadCard
                lead={lead}
                onClick={() => navigate(`/leads/${lead.id}`)}
              />
            </div>
          ))}
          {stage.leads.length === 0 && (
            <p className="text-xs text-gray-400 dark:text-gray-500 text-center py-4">
              No leads
            </p>
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
    const types = e.dataTransfer.types;
    if (types.includes('application/json')) {
      e.preventDefault();
    }
  };

  return (
    <div
      className="flex-shrink-0 w-64 sm:w-72"
      onDrop={handleDrop}
      onDragOver={handleDragOver}
    >
      <div className="bg-emerald-50/50 dark:bg-emerald-950/30 rounded-lg p-3 h-full">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2 min-w-0">
            <div
              className="w-3 h-3 rounded-full shrink-0"
              style={{ backgroundColor: stage.color }}
              aria-hidden="true"
            />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
              {stage.stage_name}
            </h3>
          </div>
          <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0 ml-2">
            {stage.count}
          </span>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3" style={{ fontVariantNumeric: 'tabular-nums' }}>
          {formatCurrency(stage.total_amount ?? 0, 'USD')}
        </p>
        <div className="space-y-2 max-h-[calc(100vh-18rem)] overflow-y-auto">
          {stage.opportunities.map((opp) => (
            <div
              key={opp.id}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData(
                  'application/json',
                  JSON.stringify({ id: opp.id, entityType: 'opportunity', sourceStageId: stage.stage_id })
                );
              }}
            >
              <OpportunityCard
                opportunity={opp}
                onClick={() => navigate(`/opportunities/${opp.id}`)}
              />
            </div>
          ))}
          {stage.opportunities.length === 0 && (
            <p className="text-xs text-gray-400 dark:text-gray-500 text-center py-4">
              No deals
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function PipelinePage() {
  usePageTitle('Pipeline');

  const { data: leadKanban, isLoading: leadsLoading, error: leadsError } = useLeadKanban();
  const { data: oppKanban, isLoading: oppsLoading, error: oppsError } = useKanban();

  const isLoading = leadsLoading || oppsLoading;
  const error = leadsError || oppsError;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
        <p className="text-sm font-medium text-red-800 dark:text-red-300">
          {error instanceof Error ? error.message : 'Failed to load pipeline data'}
        </p>
      </div>
    );
  }

  const leadStages = leadKanban?.stages ?? [];
  const oppStages = oppKanban?.stages ?? [];
  const hasData = leadStages.length > 0 || oppStages.length > 0;

  return (
    <div className="space-y-4 sm:space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">
          Unified Pipeline
        </h1>
        <p className="mt-0.5 sm:mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
          Track leads and deals across all pipeline stages
        </p>
      </div>

      {!hasData ? (
        <div className="text-center py-12">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No pipeline stages configured. Create pipeline stages in settings.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto pb-4">
          <div className="flex gap-3 min-w-max items-start">
            {/* Lead pipeline stages */}
            {leadStages.length > 0 && (
              <>
                <div className="flex gap-3">
                  {leadStages.map((stage) => (
                    <LeadStageColumn key={`lead-${stage.stage_id}`} stage={stage} />
                  ))}
                </div>

                {/* Separator */}
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
              <div className="flex gap-3">
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
      )}
    </div>
  );
}

export default PipelinePage;
