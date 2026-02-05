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
  exportContacts,
  exportCompanies,
  exportLeads,
  downloadBlob,
  generateExportFilename,
} from '../../api';
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

type ExportType = 'contacts' | 'companies' | 'leads' | 'opportunities';

function ReportsPage() {
  const [activeReport, setActiveReport] = useState<ReportType>('pipeline');
  const [exportLoading, setExportLoading] = useState<ExportType | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const { data: dashboardData, isLoading: dashboardLoading } = useDashboard();
  const { data: pipelineData, isLoading: pipelineLoading } = usePipelineFunnelChart();
  const { data: leadsData, isLoading: leadsLoading } = useLeadsBySourceChart();
  const { data: conversionData, isLoading: conversionLoading } = useConversionRatesChart();

  const isLoading = dashboardLoading || pipelineLoading || leadsLoading || conversionLoading;

  /**
   * Handle export for different entity types
   */
  const handleExport = async (type: ExportType) => {
    setExportLoading(type);
    setExportError(null);

    try {
      let blob: Blob;

      switch (type) {
        case 'contacts':
          blob = await exportContacts();
          break;
        case 'companies':
          blob = await exportCompanies();
          break;
        case 'leads':
          blob = await exportLeads();
          break;
        case 'opportunities':
          // For opportunities, we export the pipeline data (which includes opportunities)
          // Currently there's no separate opportunities export, so we'll use leads
          blob = await exportLeads();
          break;
        default:
          throw new Error(`Unknown export type: ${type}`);
      }

      const filename = generateExportFilename(type);
      downloadBlob(blob, filename);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Export failed. Please try again.';
      setExportError(errorMessage);
      console.error(`Export ${type} failed:`, error);
    } finally {
      setExportLoading(null);
    }
  };

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
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2 mb-4 sm:mb-6">
              <h3 className="text-base sm:text-lg font-medium text-gray-900">Pipeline by Stage</h3>
              <Button
                variant="secondary"
                size="sm"
                className="self-start sm:self-auto"
                onClick={() => handleExport('opportunities')}
                disabled={exportLoading === 'opportunities'}
              >
                {exportLoading === 'opportunities' ? (
                  <Spinner size="sm" className="mr-2" />
                ) : (
                  <ArrowDownTrayIcon className="h-4 w-4 mr-2" />
                )}
                {exportLoading === 'opportunities' ? 'Exporting...' : 'Export CSV'}
              </Button>
            </div>
            {/* Table with horizontal scroll on mobile */}
            <div className="overflow-x-auto -mx-3 sm:mx-0">
              <table className="min-w-full divide-y divide-gray-200" style={{ minWidth: '500px' }}>
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
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2 mb-4 sm:mb-6">
              <h3 className="text-base sm:text-lg font-medium text-gray-900">Leads by Source</h3>
              <Button
                variant="secondary"
                size="sm"
                className="self-start sm:self-auto"
                onClick={() => handleExport('leads')}
                disabled={exportLoading === 'leads'}
              >
                {exportLoading === 'leads' ? (
                  <Spinner size="sm" className="mr-2" />
                ) : (
                  <ArrowDownTrayIcon className="h-4 w-4 mr-2" />
                )}
                {exportLoading === 'leads' ? 'Exporting...' : 'Export CSV'}
              </Button>
            </div>
            {/* Table with horizontal scroll on mobile */}
            <div className="overflow-x-auto -mx-3 sm:mx-0">
              <table className="min-w-full divide-y divide-gray-200" style={{ minWidth: '400px' }}>
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
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2 mb-4 sm:mb-6">
              <h3 className="text-base sm:text-lg font-medium text-gray-900">Conversion Rates</h3>
              <Button
                variant="secondary"
                size="sm"
                className="self-start sm:self-auto"
                onClick={() => handleExport('contacts')}
                disabled={exportLoading === 'contacts'}
              >
                {exportLoading === 'contacts' ? (
                  <Spinner size="sm" className="mr-2" />
                ) : (
                  <ArrowDownTrayIcon className="h-4 w-4 mr-2" />
                )}
                {exportLoading === 'contacts' ? 'Exporting...' : 'Export CSV'}
              </Button>
            </div>
            {/* Cards - full width on mobile, 3 columns on desktop */}
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-6">
              {(conversionData?.data || []).map((item: any, idx: number) => (
                <Card key={idx}>
                  <CardBody className="p-4 sm:p-6">
                    <div className="text-center">
                      <p className="text-xs sm:text-sm text-gray-500">{item.label || `Metric ${idx + 1}`}</p>
                      <p className="text-2xl sm:text-3xl font-bold text-primary-600 mt-2">
                        {typeof item.value === 'number' ? `${item.value.toFixed(1)}%` : item.value}
                      </p>
                    </div>
                  </CardBody>
                </Card>
              ))}
              {(!conversionData?.data || conversionData.data.length === 0) && (
                <Card className="col-span-1 sm:col-span-2 md:col-span-3">
                  <CardBody>
                    <p className="text-center text-gray-500 text-sm">No conversion data available yet</p>
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
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2 mb-4 sm:mb-6">
              <h3 className="text-base sm:text-lg font-medium text-gray-900">Revenue Summary</h3>
              <Button
                variant="secondary"
                size="sm"
                className="self-start sm:self-auto"
                onClick={() => handleExport('companies')}
                disabled={exportLoading === 'companies'}
              >
                {exportLoading === 'companies' ? (
                  <Spinner size="sm" className="mr-2" />
                ) : (
                  <ArrowDownTrayIcon className="h-4 w-4 mr-2" />
                )}
                {exportLoading === 'companies' ? 'Exporting...' : 'Export CSV'}
              </Button>
            </div>
            {/* Revenue cards - full width on mobile */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-6">
              <Card>
                <CardBody className="p-4 sm:p-6">
                  <div className="text-center py-2 sm:py-4">
                    <CurrencyDollarIcon className="h-10 w-10 sm:h-12 sm:w-12 text-green-500 mx-auto mb-2 sm:mb-3" />
                    <p className="text-xs sm:text-sm text-gray-500">Total Revenue (Won)</p>
                    <p className="text-2xl sm:text-3xl font-bold text-gray-900 mt-2">
                      {formatCurrency(totalRevenue)}
                    </p>
                  </div>
                </CardBody>
              </Card>
              <Card>
                <CardBody className="p-4 sm:p-6">
                  <div className="text-center py-2 sm:py-4">
                    <FunnelIcon className="h-10 w-10 sm:h-12 sm:w-12 text-primary-500 mx-auto mb-2 sm:mb-3" />
                    <p className="text-xs sm:text-sm text-gray-500">Open Opportunities</p>
                    <p className="text-2xl sm:text-3xl font-bold text-gray-900 mt-2">
                      {openOpportunities}
                    </p>
                  </div>
                </CardBody>
              </Card>
            </div>
            {/* Pipeline chart - full width on mobile */}
            <Card>
              <CardHeader title="Pipeline Value by Stage" />
              <CardBody className="p-3 sm:p-6">
                <div className="space-y-2 sm:space-y-3">
                  {(pipelineData?.data || []).map((item: any, idx: number) => {
                    const maxValue = Math.max(
                      ...(pipelineData?.data || []).map((i: any) => i.value || 0)
                    );
                    const value = item.value || 0;
                    const width = maxValue > 0 ? (value / maxValue) * 100 : 0;
                    return (
                      <div key={idx} className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4">
                        <div className="w-full sm:w-32 text-xs sm:text-sm text-gray-600 truncate">
                          {item.stage || item.label || `Stage ${idx + 1}`}
                        </div>
                        <div className="flex items-center gap-2 sm:gap-4 flex-1">
                          <div className="flex-1">
                            <div className="h-3 sm:h-4 bg-gray-100 rounded-full overflow-hidden">
                              <div
                                className="h-full bg-primary-500 rounded-full"
                                style={{ width: `${width}%` }}
                              />
                            </div>
                          </div>
                          <div className="w-20 sm:w-24 text-xs sm:text-sm text-gray-900 text-right font-medium">
                            {formatCurrency(value)}
                          </div>
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
    <div className="space-y-4 sm:space-y-6">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900">Reports</h1>
          <p className="mt-1 text-xs sm:text-sm text-gray-500">
            Analyze your CRM data with detailed reports
          </p>
        </div>
        <div className="flex items-center gap-2 text-xs sm:text-sm text-gray-500">
          <ChartBarIcon className="h-4 w-4 sm:h-5 sm:w-5" />
          <span>Last updated: {formatDate(new Date().toISOString())}</span>
        </div>
      </div>

      {/* Export error message */}
      {exportError && (
        <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg flex items-center justify-between">
          <span className="text-sm">{exportError}</span>
          <button
            onClick={() => setExportError(null)}
            className="text-red-500 hover:text-red-700 font-medium text-sm"
          >
            Dismiss
          </button>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-4 sm:gap-6">
        {/* Report Selection - horizontal scroll on mobile, vertical on desktop */}
        <div className="lg:col-span-1">
          {/* Mobile: horizontal scrollable selector */}
          <div className="flex lg:hidden gap-2 overflow-x-auto pb-2 -mx-4 px-4 scrollbar-hide">
            {reports.map((report) => (
              <button
                key={report.type}
                onClick={() => setActiveReport(report.type)}
                className={`flex items-center gap-2 px-3 py-2 rounded-lg border-2 transition-colors whitespace-nowrap flex-shrink-0 ${
                  activeReport === report.type
                    ? 'border-primary-500 bg-primary-50'
                    : 'border-gray-200 hover:border-gray-300 bg-white'
                }`}
              >
                <div className={`p-1.5 rounded-lg ${activeReport === report.type ? 'bg-primary-100 text-primary-600' : 'bg-gray-100 text-gray-600'}`}>
                  {report.icon}
                </div>
                <span className={`text-sm font-medium ${activeReport === report.type ? 'text-primary-700' : 'text-gray-900'}`}>
                  {report.title}
                </span>
              </button>
            ))}
          </div>
          {/* Desktop: vertical cards */}
          <div className="hidden lg:block space-y-3">
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
        </div>

        {/* Report Content - full width on mobile */}
        <div className="lg:col-span-3">
          <Card>
            <CardBody className="p-3 sm:p-6">{renderReportContent()}</CardBody>
          </Card>
        </div>
      </div>
    </div>
  );
}

export default ReportsPage;
