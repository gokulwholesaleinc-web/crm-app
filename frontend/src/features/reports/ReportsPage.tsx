/**
 * Reports page with CRM analytics and reporting.
 */

import { useState } from 'react';
import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import { formatCurrency, formatDate } from '../../utils';
import {
  useDashboard,
  usePipelineFunnelChart,
  useLeadsBySourceChart,
  useConversionRatesChart,
} from '../../hooks';
import {
  ChartBarIcon,
  ArrowDownTrayIcon,
  FunnelIcon,
  UserGroupIcon,
  CurrencyDollarIcon,
  ArrowTrendingUpIcon,
} from '@heroicons/react/24/outline';

type ReportType = 'pipeline' | 'leads' | 'conversion' | 'revenue';

interface ReportCardProps {
  title: string;
  description: string;
  icon: React.ReactNode;
  isActive: boolean;
  onClick: () => void;
}

function ReportCard({ title, description, icon, isActive, onClick }: ReportCardProps) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-4 rounded-lg border-2 transition-colors ${
        isActive
          ? 'border-primary-500 bg-primary-50'
          : 'border-gray-200 hover:border-gray-300 bg-white'
      }`}
    >
      <div className="flex items-start gap-3">
        <div className={`p-2 rounded-lg ${isActive ? 'bg-primary-100 text-primary-600' : 'bg-gray-100 text-gray-600'}`}>
          {icon}
        </div>
        <div>
          <h3 className={`font-medium ${isActive ? 'text-primary-700' : 'text-gray-900'}`}>
            {title}
          </h3>
          <p className="text-sm text-gray-500 mt-1">{description}</p>
        </div>
      </div>
    </button>
  );
}

function ReportsPage() {
  const [activeReport, setActiveReport] = useState<ReportType>('pipeline');

  const { data: dashboardData, isLoading: dashboardLoading } = useDashboard();
  const { data: pipelineData, isLoading: pipelineLoading } = usePipelineFunnelChart();
  const { data: leadsData, isLoading: leadsLoading } = useLeadsBySourceChart();
  const { data: conversionData, isLoading: conversionLoading } = useConversionRatesChart();

  const isLoading = dashboardLoading || pipelineLoading || leadsLoading || conversionLoading;

  const reports = [
    {
      type: 'pipeline' as ReportType,
      title: 'Pipeline Report',
      description: 'Opportunities by stage with values',
      icon: <FunnelIcon className="h-5 w-5" />,
    },
    {
      type: 'leads' as ReportType,
      title: 'Lead Sources',
      description: 'Where your leads come from',
      icon: <UserGroupIcon className="h-5 w-5" />,
    },
    {
      type: 'conversion' as ReportType,
      title: 'Conversion Rates',
      description: 'Lead to opportunity conversion',
      icon: <ArrowTrendingUpIcon className="h-5 w-5" />,
    },
    {
      type: 'revenue' as ReportType,
      title: 'Revenue Summary',
      description: 'Total and projected revenue',
      icon: <CurrencyDollarIcon className="h-5 w-5" />,
    },
  ];

  const renderReportContent = () => {
    if (isLoading) {
      return (
        <div className="flex items-center justify-center h-64">
          <Spinner size="lg" />
        </div>
      );
    }

    switch (activeReport) {
      case 'pipeline':
        return (
          <div className="space-y-4">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-lg font-medium text-gray-900">Pipeline by Stage</h3>
              <Button variant="secondary" size="sm">
                <ArrowDownTrayIcon className="h-4 w-4 mr-2" />
                Export CSV
              </Button>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Stage
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Count
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Value
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      % of Total
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {(pipelineData?.data || []).map((item: any, idx: number) => {
                    const totalCount = (pipelineData?.data || []).reduce(
                      (sum: number, i: any) => sum + (i.count || i.value || 0),
                      0
                    );
                    const count = item.count || item.value || 0;
                    const percentage = totalCount > 0 ? ((count / totalCount) * 100).toFixed(1) : '0';
                    return (
                      <tr key={idx} className="hover:bg-gray-50">
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                          {item.stage || item.label || `Stage ${idx + 1}`}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 text-right">
                          {count}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 text-right">
                          {formatCurrency(item.value || 0)}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 text-right">
                          {percentage}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
                <tfoot className="bg-gray-50">
                  <tr>
                    <td className="px-6 py-3 text-sm font-medium text-gray-900">Total</td>
                    <td className="px-6 py-3 text-sm font-medium text-gray-900 text-right">
                      {(pipelineData?.data || []).reduce(
                        (sum: number, i: any) => sum + (i.count || i.value || 0),
                        0
                      )}
                    </td>
                    <td className="px-6 py-3 text-sm font-medium text-gray-900 text-right">
                      {formatCurrency(
                        (pipelineData?.data || []).reduce(
                          (sum: number, i: any) => sum + (i.value || 0),
                          0
                        )
                      )}
                    </td>
                    <td className="px-6 py-3 text-sm font-medium text-gray-900 text-right">
                      100%
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        );

      case 'leads':
        return (
          <div className="space-y-4">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-lg font-medium text-gray-900">Leads by Source</h3>
              <Button variant="secondary" size="sm">
                <ArrowDownTrayIcon className="h-4 w-4 mr-2" />
                Export CSV
              </Button>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Source
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Leads
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      % of Total
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {(leadsData?.data || []).map((item: any, idx: number) => {
                    const totalCount = (leadsData?.data || []).reduce(
                      (sum: number, i: any) => sum + (i.count || i.value || 0),
                      0
                    );
                    const count = item.count || item.value || 0;
                    const percentage = totalCount > 0 ? ((count / totalCount) * 100).toFixed(1) : '0';
                    return (
                      <tr key={idx} className="hover:bg-gray-50">
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                          {item.source || item.label || `Source ${idx + 1}`}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 text-right">
                          {count}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 text-right">
                          {percentage}%
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        );

      case 'conversion':
        return (
          <div className="space-y-4">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-lg font-medium text-gray-900">Conversion Rates</h3>
              <Button variant="secondary" size="sm">
                <ArrowDownTrayIcon className="h-4 w-4 mr-2" />
                Export CSV
              </Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {(conversionData?.data || []).map((item: any, idx: number) => (
                <Card key={idx}>
                  <CardBody>
                    <div className="text-center">
                      <p className="text-sm text-gray-500">{item.label || `Metric ${idx + 1}`}</p>
                      <p className="text-3xl font-bold text-primary-600 mt-2">
                        {typeof item.value === 'number' ? `${item.value.toFixed(1)}%` : item.value}
                      </p>
                    </div>
                  </CardBody>
                </Card>
              ))}
              {(!conversionData?.data || conversionData.data.length === 0) && (
                <Card className="col-span-3">
                  <CardBody>
                    <p className="text-center text-gray-500">No conversion data available yet</p>
                  </CardBody>
                </Card>
              )}
            </div>
          </div>
        );

      case 'revenue':
        const numberCards = dashboardData?.number_cards || [];
        const totalRevenueRaw = numberCards.find((c: any) => c.id === 'total_revenue')?.value;
        const totalRevenue = typeof totalRevenueRaw === 'number' ? totalRevenueRaw : 0;
        const openOpportunitiesRaw = numberCards.find((c: any) => c.id === 'open_opportunities')?.value;
        const openOpportunities = typeof openOpportunitiesRaw === 'number' ? openOpportunitiesRaw : 0;

        return (
          <div className="space-y-4">
            <div className="flex justify-between items-center mb-6">
              <h3 className="text-lg font-medium text-gray-900">Revenue Summary</h3>
              <Button variant="secondary" size="sm">
                <ArrowDownTrayIcon className="h-4 w-4 mr-2" />
                Export CSV
              </Button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <Card>
                <CardBody>
                  <div className="text-center py-4">
                    <CurrencyDollarIcon className="h-12 w-12 text-green-500 mx-auto mb-3" />
                    <p className="text-sm text-gray-500">Total Revenue (Won)</p>
                    <p className="text-3xl font-bold text-gray-900 mt-2">
                      {formatCurrency(totalRevenue)}
                    </p>
                  </div>
                </CardBody>
              </Card>
              <Card>
                <CardBody>
                  <div className="text-center py-4">
                    <FunnelIcon className="h-12 w-12 text-primary-500 mx-auto mb-3" />
                    <p className="text-sm text-gray-500">Open Opportunities</p>
                    <p className="text-3xl font-bold text-gray-900 mt-2">
                      {openOpportunities}
                    </p>
                  </div>
                </CardBody>
              </Card>
            </div>
            <Card>
              <CardHeader title="Pipeline Value by Stage" />
              <CardBody>
                <div className="space-y-3">
                  {(pipelineData?.data || []).map((item: any, idx: number) => {
                    const maxValue = Math.max(
                      ...(pipelineData?.data || []).map((i: any) => i.value || 0)
                    );
                    const value = item.value || 0;
                    const width = maxValue > 0 ? (value / maxValue) * 100 : 0;
                    return (
                      <div key={idx} className="flex items-center gap-4">
                        <div className="w-32 text-sm text-gray-600">
                          {item.stage || item.label || `Stage ${idx + 1}`}
                        </div>
                        <div className="flex-1">
                          <div className="h-4 bg-gray-100 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-primary-500 rounded-full"
                              style={{ width: `${width}%` }}
                            />
                          </div>
                        </div>
                        <div className="w-24 text-sm text-gray-900 text-right font-medium">
                          {formatCurrency(value)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </CardBody>
            </Card>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Reports</h1>
          <p className="mt-1 text-sm text-gray-500">
            Analyze your CRM data with detailed reports
          </p>
        </div>
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <ChartBarIcon className="h-5 w-5" />
          <span>Last updated: {formatDate(new Date().toISOString())}</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Report Selection */}
        <div className="lg:col-span-1 space-y-3">
          {reports.map((report) => (
            <ReportCard
              key={report.type}
              title={report.title}
              description={report.description}
              icon={report.icon}
              isActive={activeReport === report.type}
              onClick={() => setActiveReport(report.type)}
            />
          ))}
        </div>

        {/* Report Content */}
        <div className="lg:col-span-3">
          <Card>
            <CardBody>{renderReportContent()}</CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default ReportsPage;
