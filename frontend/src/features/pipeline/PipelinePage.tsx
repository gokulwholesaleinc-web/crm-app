import { useNavigate } from 'react-router-dom';
import { Spinner } from '../../components/ui';
import { useKanban } from '../../hooks/useOpportunities';
import { usePageTitle } from '../../hooks/usePageTitle';
import { formatCurrency } from '../../utils/formatters';
import type { KanbanStage, KanbanOpportunity } from '../../types';
import clsx from 'clsx';

function PipelineCard({ opportunity, onClick }: { opportunity: KanbanOpportunity; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-3 hover:shadow-md transition-shadow duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
    >
      <div className="space-y-2">
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

function PipelineColumn({ stage }: { stage: KanbanStage }) {
  const navigate = useNavigate();

  return (
    <div className="flex-shrink-0 w-72 sm:w-80">
      <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div
              className="w-3 h-3 rounded-full shrink-0"
              style={{ backgroundColor: stage.color }}
              aria-hidden="true"
            />
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
              {stage.stage_name}
            </h3>
          </div>
          <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0">
            {stage.count}
          </span>
        </div>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3" style={{ fontVariantNumeric: 'tabular-nums' }}>
          {formatCurrency(stage.total_amount)}
        </p>
        <div className="space-y-2 max-h-[calc(100vh-16rem)] overflow-y-auto">
          {stage.opportunities.map((opp) => (
            <PipelineCard
              key={opp.id}
              opportunity={opp}
              onClick={() => navigate(`/opportunities/${opp.id}`)}
            />
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

  const { data: kanbanData, isLoading, error } = useKanban();

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

  const stages = kanbanData?.stages ?? [];

  return (
    <div className="space-y-4 sm:space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">
          Sales Pipeline
        </h1>
        <p className="mt-0.5 sm:mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
          Track deal progression across stages
        </p>
      </div>

      {stages.length === 0 ? (
        <div className="text-center py-12">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            No pipeline stages configured. Create pipeline stages in Opportunities settings.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto pb-4">
          <div className="flex gap-4 min-w-max">
            {stages.map((stage) => (
              <PipelineColumn key={stage.stage_id} stage={stage} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default PipelinePage;
