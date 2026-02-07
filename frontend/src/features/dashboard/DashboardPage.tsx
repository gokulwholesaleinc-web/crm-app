import { NumberCard } from './components/NumberCard';
import { ChartCard } from './components/ChartCard';
import { SalesFunnelChart } from './components/SalesFunnelChart';
import { Spinner } from '../../components/ui/Spinner';
import { DashboardRecommendations } from '../../components/ai/DashboardRecommendations';
import { formatCurrency, formatDate } from '../../utils';
import { useDashboard, usePipelineFunnelChart, useLeadsBySourceChart, useUserTimeline, useSalesFunnel } from '../../hooks';
import type { NumberCardData, ChartDataPoint } from '../../types';

// Helper to find number card by id
function findCardValue(cards: NumberCardData[], id: string): number {
  const card = cards.find(c => c.id === id);
  return typeof card?.value === 'number' ? card.value : 0;
}

function findCardChange(cards: NumberCardData[], id: string): number {
  const card = cards.find(c => c.id === id);
  return card?.change ?? 0;
}

function DashboardPage() {
  // Use hooks for data fetching
  const { data: dashboardData, isLoading: isLoadingDashboard, error: dashboardError } = useDashboard();
  const { data: pipelineData } = usePipelineFunnelChart();
  const { data: leadsBySourceData } = useLeadsBySourceChart();
  const { data: timelineData } = useUserTimeline();
  const { data: funnelData } = useSalesFunnel();

  const isLoading = isLoadingDashboard;
  const error = dashboardError instanceof Error ? dashboardError.message : dashboardError ? String(dashboardError) : null;

  // Extract number cards from dashboard response
  const numberCards = dashboardData?.number_cards ?? [];
  // Note: charts from dashboardData can be used for additional visualizations if needed

  // Map data to expected format using number cards
  const data = dashboardData ? {
    totalContacts: findCardValue(numberCards, 'total_contacts'),
    totalLeads: findCardValue(numberCards, 'total_leads'),
    totalOpportunities: findCardValue(numberCards, 'open_opportunities'),
    totalRevenue: findCardValue(numberCards, 'total_revenue'),
    contactsTrend: findCardChange(numberCards, 'total_contacts'),
    leadsTrend: findCardChange(numberCards, 'total_leads'),
    opportunitiesTrend: findCardChange(numberCards, 'open_opportunities'),
    revenueTrend: findCardChange(numberCards, 'total_revenue'),
    recentActivities: (timelineData?.items ?? []).slice(0, 10).map(item => ({
      id: item.id,
      description: item.subject || item.description || 'Activity',
      timestamp: item.scheduled_at || item.completed_at || item.due_date || new Date().toISOString(),
    })),
    pipelineData: (pipelineData?.data ?? []) as (ChartDataPoint & { stage?: string; count?: number; value?: number })[],
    leadsBySource: (leadsBySourceData?.data ?? []) as (ChartDataPoint & { source?: string; count?: number })[],
  } : null;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-md bg-red-50 p-4">
        <div className="flex">
          <div className="ml-3">
            <h3 className="text-sm font-medium text-red-800">Error loading dashboard</h3>
            <p className="mt-2 text-sm text-red-700">{error}</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="mt-0.5 sm:mt-1 text-xs sm:text-sm text-gray-500">
          Overview of your CRM performance
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-3 sm:gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <NumberCard
          title="Total Contacts"
          value={data?.totalContacts ?? 0}
          trend={{
            value: data?.contactsTrend ?? 0,
            isPositive: (data?.contactsTrend ?? 0) >= 0,
          }}
          icon={
            <svg
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
              />
            </svg>
          }
        />

        <NumberCard
          title="Total Leads"
          value={data?.totalLeads ?? 0}
          trend={{
            value: data?.leadsTrend ?? 0,
            isPositive: (data?.leadsTrend ?? 0) >= 0,
          }}
          icon={
            <svg
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6"
              />
            </svg>
          }
        />

        <NumberCard
          title="Open Opportunities"
          value={data?.totalOpportunities ?? 0}
          trend={{
            value: data?.opportunitiesTrend ?? 0,
            isPositive: (data?.opportunitiesTrend ?? 0) >= 0,
          }}
          icon={
            <svg
              className="h-6 w-6"
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
          }
        />

        <NumberCard
          title="Total Revenue"
          value={formatCurrency(data?.totalRevenue ?? 0)}
          trend={{
            value: data?.revenueTrend ?? 0,
            isPositive: (data?.revenueTrend ?? 0) >= 0,
          }}
          icon={
            <svg
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          }
        />
      </div>

      {/* AI Suggestions */}
      <DashboardRecommendations maxItems={3} />

      {/* Charts Section */}
      <div className="grid grid-cols-1 gap-3 sm:gap-6 lg:grid-cols-2">
        <ChartCard
          title="Pipeline Overview"
          subtitle="Opportunities by stage"
        >
          <div className="space-y-3 sm:space-y-4">
            {data?.pipelineData?.map((item, index) => {
              const label = item.stage || item.label || `Stage ${index + 1}`;
              const count = item.count ?? (typeof item.value === 'number' ? item.value : 0);
              const value = item.value ?? count;
              const maxCount = Math.max(...(data?.pipelineData?.map(p => p.count ?? (typeof p.value === 'number' ? p.value : 0)) || [1]));
              return (
                <div key={label} className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-0">
                  <div className="w-full sm:w-28 md:w-32 text-xs sm:text-sm font-medium text-gray-600 truncate">
                    {label}
                  </div>
                  <div className="flex items-center flex-1 gap-2 sm:gap-4">
                    <div className="flex-1 sm:ml-4">
                      <div className="relative h-3 sm:h-4 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="absolute h-full bg-primary-500 rounded-full"
                          style={{
                            width: `${Math.min((count / maxCount) * 100, 100)}%`,
                          }}
                        />
                      </div>
                    </div>
                    <div className="w-auto sm:w-20 text-right text-xs sm:text-sm font-medium text-gray-900 whitespace-nowrap">
                      {count} ({formatCurrency(typeof value === 'number' ? value : 0)})
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </ChartCard>

        <ChartCard
          title="Leads by Source"
          subtitle="Where your leads come from"
        >
          <div className="space-y-3 sm:space-y-4">
            {data?.leadsBySource?.map((item, index) => {
              const label = item.source || item.label || `Source ${index + 1}`;
              const count = item.count ?? (typeof item.value === 'number' ? item.value : 0);
              const maxCount = Math.max(...(data?.leadsBySource?.map(l => l.count ?? (typeof l.value === 'number' ? l.value : 0)) || [1]));
              return (
                <div key={label} className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-0">
                  <div className="w-full sm:w-28 md:w-32 text-xs sm:text-sm font-medium text-gray-600 truncate">
                    {label}
                  </div>
                  <div className="flex items-center flex-1 gap-2 sm:gap-4">
                    <div className="flex-1 sm:ml-4">
                      <div className="relative h-3 sm:h-4 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="absolute h-full bg-green-500 rounded-full"
                          style={{
                            width: `${Math.min((count / maxCount) * 100, 100)}%`,
                          }}
                        />
                      </div>
                    </div>
                    <div className="w-8 sm:w-12 text-right text-xs sm:text-sm font-medium text-gray-900">
                      {count}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </ChartCard>
      </div>

      {/* Sales Funnel */}
      {funnelData && (
        <ChartCard
          title="Sales Funnel"
          subtitle="Lead progression through stages"
        >
          <SalesFunnelChart data={funnelData} />
        </ChartCard>
      )}

      {/* Recent Activities */}
      <ChartCard
        title="Recent Activities"
        subtitle="Latest actions in your CRM"
      >
        <div className="flow-root">
          <ul className="-mb-8">
            {data?.recentActivities && data.recentActivities.length > 0 ? (
              data.recentActivities.map((activity: { id: number; description: string; timestamp: string }, idx: number) => (
                <li key={activity.id}>
                  <div className="relative pb-6 sm:pb-8">
                    {idx !== (data?.recentActivities?.length || 0) - 1 && (
                      <span
                        className="absolute top-3 sm:top-4 left-3 sm:left-4 -ml-px h-full w-0.5 bg-gray-200"
                        aria-hidden="true"
                      />
                    )}
                    <div className="relative flex space-x-2 sm:space-x-3">
                      <div>
                        <span className="h-6 w-6 sm:h-8 sm:w-8 rounded-full bg-primary-100 flex items-center justify-center ring-4 sm:ring-8 ring-white">
                          <svg
                            className="h-3 w-3 sm:h-4 sm:w-4 text-primary-600"
                            fill="none"
                            viewBox="0 0 24 24"
                            stroke="currentColor"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M12 6v6m0 0v6m0-6h6m-6 0H6"
                            />
                          </svg>
                        </span>
                      </div>
                      <div className="min-w-0 flex-1 pt-0.5 sm:pt-1.5">
                        <div className="flex flex-col sm:flex-row sm:justify-between sm:space-x-4">
                          <p className="text-xs sm:text-sm text-gray-500 break-words">
                            {activity.description}
                          </p>
                          <div className="text-xs sm:text-sm text-gray-400 sm:text-gray-500 whitespace-nowrap mt-0.5 sm:mt-0">
                            {formatDate(activity.timestamp)}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </li>
              ))
            ) : (
              <li className="text-center py-4 text-sm text-gray-500">
                No recent activities
              </li>
            )}
          </ul>
        </div>
      </ChartCard>
    </div>
  );
}

export default DashboardPage;
