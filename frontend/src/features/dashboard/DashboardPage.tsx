import { useState, useEffect } from 'react';
import { NumberCard } from './components/NumberCard';
import { ChartCard } from './components/ChartCard';
import { Spinner } from '../../components/ui/Spinner';

interface DashboardData {
  totalContacts: number;
  totalLeads: number;
  totalOpportunities: number;
  totalRevenue: number;
  contactsTrend: number;
  leadsTrend: number;
  opportunitiesTrend: number;
  revenueTrend: number;
  recentActivities: Array<{
    id: string;
    type: string;
    description: string;
    timestamp: string;
  }>;
  pipelineData: Array<{
    stage: string;
    count: number;
    value: number;
  }>;
  leadsBySource: Array<{
    source: string;
    count: number;
  }>;
}

export function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        const response = await fetch('/api/dashboard', {
          headers: {
            Authorization: `Bearer ${localStorage.getItem('access_token')}`,
          },
        });

        if (!response.ok) {
          throw new Error('Failed to fetch dashboard data');
        }

        const result = await response.json();
        setData(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        setIsLoading(false);
      }
    };

    fetchDashboardData();
  }, []);

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
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="mt-1 text-sm text-gray-500">
          Overview of your CRM performance
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
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

      {/* Charts Section */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <ChartCard
          title="Pipeline Overview"
          subtitle="Opportunities by stage"
        >
          <div className="space-y-4">
            {data?.pipelineData?.map((item) => (
              <div key={item.stage} className="flex items-center">
                <div className="w-32 text-sm font-medium text-gray-600">
                  {item.stage}
                </div>
                <div className="flex-1 ml-4">
                  <div className="relative h-4 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="absolute h-full bg-primary-500 rounded-full"
                      style={{
                        width: `${Math.min((item.count / Math.max(...(data?.pipelineData?.map(p => p.count) || [1]))) * 100, 100)}%`,
                      }}
                    />
                  </div>
                </div>
                <div className="w-20 text-right text-sm font-medium text-gray-900 ml-4">
                  {item.count} ({formatCurrency(item.value)})
                </div>
              </div>
            ))}
          </div>
        </ChartCard>

        <ChartCard
          title="Leads by Source"
          subtitle="Where your leads come from"
        >
          <div className="space-y-4">
            {data?.leadsBySource?.map((item) => (
              <div key={item.source} className="flex items-center">
                <div className="w-32 text-sm font-medium text-gray-600">
                  {item.source}
                </div>
                <div className="flex-1 ml-4">
                  <div className="relative h-4 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className="absolute h-full bg-green-500 rounded-full"
                      style={{
                        width: `${Math.min((item.count / Math.max(...(data?.leadsBySource?.map(l => l.count) || [1]))) * 100, 100)}%`,
                      }}
                    />
                  </div>
                </div>
                <div className="w-12 text-right text-sm font-medium text-gray-900 ml-4">
                  {item.count}
                </div>
              </div>
            ))}
          </div>
        </ChartCard>
      </div>

      {/* Recent Activities */}
      <ChartCard
        title="Recent Activities"
        subtitle="Latest actions in your CRM"
      >
        <div className="flow-root">
          <ul className="-mb-8">
            {data?.recentActivities?.map((activity, idx) => (
              <li key={activity.id}>
                <div className="relative pb-8">
                  {idx !== (data?.recentActivities?.length || 0) - 1 && (
                    <span
                      className="absolute top-4 left-4 -ml-px h-full w-0.5 bg-gray-200"
                      aria-hidden="true"
                    />
                  )}
                  <div className="relative flex space-x-3">
                    <div>
                      <span className="h-8 w-8 rounded-full bg-primary-100 flex items-center justify-center ring-8 ring-white">
                        <svg
                          className="h-4 w-4 text-primary-600"
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
                    <div className="min-w-0 flex-1 pt-1.5 flex justify-between space-x-4">
                      <div>
                        <p className="text-sm text-gray-500">
                          {activity.description}
                        </p>
                      </div>
                      <div className="text-right text-sm whitespace-nowrap text-gray-500">
                        {new Date(activity.timestamp).toLocaleDateString()}
                      </div>
                    </div>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </ChartCard>
    </div>
  );
}
