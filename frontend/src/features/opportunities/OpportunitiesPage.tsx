import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import {
  KanbanBoard,
  KanbanStage,
} from './components/KanbanBoard/KanbanBoard';
import { Opportunity } from './components/KanbanBoard/KanbanCard';

const defaultStages: KanbanStage[] = [
  { id: 'qualification', title: 'Qualification', color: 'blue' },
  { id: 'needs_analysis', title: 'Needs Analysis', color: 'yellow' },
  { id: 'proposal', title: 'Proposal', color: 'purple' },
  { id: 'negotiation', title: 'Negotiation', color: 'orange' },
  { id: 'closed_won', title: 'Closed Won', color: 'green' },
  { id: 'closed_lost', title: 'Closed Lost', color: 'red' },
];

export function OpportunitiesPage() {
  const navigate = useNavigate();
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'kanban' | 'list'>('kanban');

  useEffect(() => {
    fetchOpportunities();
  }, []);

  const fetchOpportunities = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch('/api/opportunities', {
        headers: {
          Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to fetch opportunities');
      }

      const data = await response.json();
      setOpportunities(
        data.items.map((item: Record<string, unknown>) => ({
          id: item.id,
          name: item.name,
          value: item.value,
          stage: item.stage,
          probability: item.probability,
          expectedCloseDate: item.expected_close_date,
          contactName: item.contact_name,
          companyName: item.company_name,
        }))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  const handleOpportunityMove = async (
    opportunityId: string,
    newStage: string,
    _newIndex: number
  ) => {
    try {
      const response = await fetch(`/api/opportunities/${opportunityId}`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        },
        body: JSON.stringify({ stage: newStage }),
      });

      if (!response.ok) {
        throw new Error('Failed to update opportunity');
      }

      // Optimistically update local state
      setOpportunities((prev) =>
        prev.map((o) => (o.id === opportunityId ? { ...o, stage: newStage } : o))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to move opportunity');
      // Refresh to get correct state
      fetchOpportunities();
      throw err;
    }
  };

  const handleOpportunityClick = (opportunity: Opportunity) => {
    navigate(`/opportunities/${opportunity.id}`);
  };

  const totalPipelineValue = opportunities
    .filter((o) => !['closed_won', 'closed_lost'].includes(o.stage))
    .reduce((sum, o) => sum + o.value, 0);

  const weightedPipelineValue = opportunities
    .filter((o) => !['closed_won', 'closed_lost'].includes(o.stage))
    .reduce((sum, o) => sum + o.value * (o.probability / 100), 0);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Opportunities</h1>
          <p className="mt-1 text-sm text-gray-500">
            Manage your sales pipeline
          </p>
        </div>
        <div className="flex items-center space-x-3">
          {/* View Toggle */}
          <div className="flex items-center bg-gray-100 rounded-lg p-1">
            <button
              onClick={() => setViewMode('kanban')}
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                viewMode === 'kanban'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
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
              className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                viewMode === 'list'
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'
              }`}
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

          <Button onClick={() => navigate('/opportunities/new')}>
            <svg
              className="h-5 w-5 mr-2"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 4v16m8-8H4"
              />
            </svg>
            Add Opportunity
          </Button>
        </div>
      </div>

      {/* Pipeline Summary */}
      <div className="bg-white shadow rounded-lg p-6">
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
          <div>
            <p className="text-sm font-medium text-gray-500">
              Total Pipeline Value
            </p>
            <p className="mt-2 text-3xl font-semibold text-gray-900">
              {formatCurrency(totalPipelineValue)}
            </p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">
              Weighted Pipeline Value
            </p>
            <p className="mt-2 text-3xl font-semibold text-gray-900">
              {formatCurrency(weightedPipelineValue)}
            </p>
          </div>
          <div>
            <p className="text-sm font-medium text-gray-500">
              Open Opportunities
            </p>
            <p className="mt-2 text-3xl font-semibold text-gray-900">
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
              <h3 className="text-sm font-medium text-red-800">{error}</h3>
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
        <div className="overflow-x-auto">
          <KanbanBoard
            stages={defaultStages}
            opportunities={opportunities}
            onOpportunityMove={handleOpportunityMove}
            onOpportunityClick={handleOpportunityClick}
          />
        </div>
      ) : (
        /* List View */
        <div className="bg-white shadow rounded-lg overflow-hidden">
          {opportunities.length === 0 ? (
            <div className="text-center py-12">
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
                <Button onClick={() => navigate('/opportunities/new')}>
                  Add Opportunity
                </Button>
              </div>
            </div>
          ) : (
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                  >
                    Opportunity
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                  >
                    Value
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                  >
                    Stage
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                  >
                    Probability
                  </th>
                  <th
                    scope="col"
                    className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider"
                  >
                    Close Date
                  </th>
                  <th scope="col" className="relative px-6 py-3">
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
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm font-medium text-gray-900">
                        {opportunity.name}
                      </div>
                      {opportunity.companyName && (
                        <div className="text-sm text-gray-500">
                          {opportunity.companyName}
                        </div>
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                      {formatCurrency(opportunity.value)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className="px-2 inline-flex text-xs leading-5 font-semibold rounded-full bg-blue-100 text-blue-800">
                        {defaultStages.find((s) => s.id === opportunity.stage)
                          ?.title || opportunity.stage}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {opportunity.probability}%
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {opportunity.expectedCloseDate
                        ? new Date(
                            opportunity.expectedCloseDate
                          ).toLocaleDateString()
                        : '-'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          navigate(`/opportunities/${opportunity.id}/edit`);
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
          )}
        </div>
      )}
    </div>
  );
}
