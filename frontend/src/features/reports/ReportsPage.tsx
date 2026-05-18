/**
 * Reports page with custom reports, templates, and saved reports.
 */

import { useState } from 'react';
import { Card, CardBody } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import { Modal, ModalFooter } from '../../components/ui/Modal';
import { ReportChart } from './components/ReportChart';
import { ReportBuilder } from './components/ReportBuilder';
import {
  useReportTemplates,
  useSavedReports,
  useExecuteReport,
  useDeleteSavedReport,
} from '../../hooks/useReports';
import type { ReportDefinition, ReportResult, ReportTemplate, SavedReport } from '../../api/reports';
import {
  PlusIcon,
  TrashIcon,
  PlayIcon,
  ClockIcon,
  ChartBarIcon,
  DocumentTextIcon,
} from '@heroicons/react/24/outline';

// Contract stats widget removed 2026-05-14 — contracts router unmounted,
// useContractStats hook removed along with frontend/src/hooks/useContracts.ts.

type ViewMode = 'list' | 'builder' | 'viewing';

function ReportsPage() {
  const [viewMode, setViewMode] = useState<ViewMode>('list');
  const [activeResult, setActiveResult] = useState<{ definition: ReportDefinition; result: ReportResult } | null>(null);
  const [builderInitial, setBuilderInitial] = useState<Partial<ReportDefinition> | undefined>(undefined);
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  const { data: templates, isLoading: templatesLoading } = useReportTemplates();
  const { data: savedReports, isLoading: reportsLoading } = useSavedReports();
  const executeReport = useExecuteReport();
  const deleteReport = useDeleteSavedReport();

  const handleRunTemplate = async (template: ReportTemplate) => {
    const definition: ReportDefinition = {
      entity_type: template.entity_type,
      metric: template.metric,
      metric_field: template.metric_field ?? null,
      group_by: template.group_by ?? null,
      date_group: template.date_group ?? null,
      filters: template.filters ?? null,
      chart_type: template.chart_type,
    };
    try {
      const result = await executeReport.mutateAsync(definition);
      setActiveResult({ definition, result });
      setViewMode('viewing');
    } catch {
      // Error handled by mutation state
    }
  };

  const handleRunSaved = async (report: SavedReport) => {
    const definition: ReportDefinition = {
      entity_type: report.entity_type,
      metric: report.metric,
      metric_field: report.metric_field ?? null,
      group_by: report.group_by ?? null,
      date_group: report.date_group ?? null,
      filters: report.filters ?? null,
      chart_type: report.chart_type,
    };
    try {
      const result = await executeReport.mutateAsync(definition);
      setActiveResult({ definition, result });
      setViewMode('viewing');
    } catch {
      // Error handled by mutation state
    }
  };

  const handleOpenBuilder = (initial?: Partial<ReportDefinition>) => {
    setBuilderInitial(initial);
    setViewMode('builder');
  };

  const handleDeleteReport = async () => {
    if (confirmDeleteId == null) return;
    await deleteReport.mutateAsync(confirmDeleteId);
    setConfirmDeleteId(null);
  };

  if (viewMode === 'builder') {
    return (
      <div className="space-y-4 sm:space-y-6">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Create Custom Report</h1>
          <p className="mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            Build a report step by step
          </p>
        </div>
        <Card>
          <CardBody className="p-4 sm:p-6">
            <ReportBuilder
              onClose={() => setViewMode('list')}
              onSaved={() => setViewMode('list')}
              initialDefinition={builderInitial}
            />
          </CardBody>
        </Card>
      </div>
    );
  }

  if (viewMode === 'viewing' && activeResult) {
    return (
      <div className="space-y-4 sm:space-y-6">
        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2">
          <div>
            <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Report Results</h1>
            <p className="mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
              {activeResult.definition.entity_type} - {activeResult.definition.metric}
              {activeResult.definition.metric_field ? `(${activeResult.definition.metric_field})` : ''}
              {activeResult.definition.group_by ? ` by ${activeResult.definition.group_by}` : ''}
              {activeResult.definition.date_group ? ` by ${activeResult.definition.date_group}` : ''}
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => { setViewMode('list'); setActiveResult(null); }}>
            Back to Reports
          </Button>
        </div>
        <Card>
          <CardBody className="p-4 sm:p-6">
            <ReportChart
              chartType={activeResult.result.chart_type}
              data={activeResult.result.data}
              total={activeResult.result.total}
            />
            {activeResult.result.total != null && (
              <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700 text-sm font-medium text-gray-700 dark:text-gray-300">
                Total: {activeResult.result.total.toLocaleString()}
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-4 sm:space-y-6" data-guide="reports-page">
      {/* Header */}
      <div
        className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-2"
        data-guide="reports-header"
      >
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">Reports</h1>
          <p className="mt-1 text-xs sm:text-sm text-gray-500 dark:text-gray-400">
            Analyze your CRM data with custom reports and templates
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" onClick={() => handleOpenBuilder()}>
            <PlusIcon className="h-4 w-4 mr-1.5" />
            Create Custom Report
          </Button>
        </div>
      </div>

      {/* Contract stats widgets removed 2026-05-14 — contracts router unmounted. */}

      {/* My Reports Section */}
      <section data-guide="reports-saved">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
          <DocumentTextIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
          My Reports
        </h2>
        {reportsLoading ? (
          <div className="flex items-center justify-center h-24">
            <Spinner size="md" />
          </div>
        ) : !savedReports || savedReports.length === 0 ? (
          <Card>
            <CardBody className="p-6 text-center text-gray-500 dark:text-gray-400 text-sm">
              No saved reports yet. Create one using the builder above.
            </CardBody>
          </Card>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {savedReports.map((report) => (
              <Card key={report.id} hover>
                <CardBody className="p-4">
                  <div className="flex items-start justify-between mb-2">
                    <div className="min-w-0 flex-1">
                      <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{report.name}</h3>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        {report.entity_type} - {report.metric}
                        {report.metric_field ? `(${report.metric_field})` : ''}
                      </p>
                    </div>
                    {report.schedule && (
                      <span className="flex-shrink-0 ml-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                        <ClockIcon className="h-3 w-3" aria-hidden="true" />
                        {report.schedule}
                      </span>
                    )}
                  </div>
                  {report.description && (
                    <p className="text-xs text-gray-400 dark:text-gray-500 mb-3 line-clamp-2">{report.description}</p>
                  )}
                  <div className="flex items-center gap-2 mt-3">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handleRunSaved(report)}
                      disabled={executeReport.isPending}
                    >
                      <PlayIcon className="h-3.5 w-3.5 mr-1" />
                      Run
                    </Button>
                    <button
                      onClick={() => setConfirmDeleteId(report.id)}
                      className="p-1.5 text-gray-400 hover:text-red-500 rounded-md hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
                      aria-label={`Delete report ${report.name}`}
                    >
                      <TrashIcon className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>
                </CardBody>
              </Card>
            ))}
          </div>
        )}
      </section>

      {/* Templates Section */}
      <section data-guide="reports-templates">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 flex items-center gap-2">
          <ChartBarIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
          Report Templates
        </h2>
        {templatesLoading ? (
          <div className="flex items-center justify-center h-24">
            <Spinner size="md" />
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {(templates || []).map((template) => (
              <Card key={template.id} hover>
                <CardBody className="p-4">
                  <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">{template.name}</h3>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">{template.description}</p>
                  <div className="flex items-center gap-2 mt-3">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handleRunTemplate(template)}
                      disabled={executeReport.isPending}
                    >
                      <PlayIcon className="h-3.5 w-3.5 mr-1" />
                      Run
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => handleOpenBuilder({
                        entity_type: template.entity_type,
                        metric: template.metric,
                        metric_field: template.metric_field,
                        group_by: template.group_by,
                        date_group: template.date_group,
                        chart_type: template.chart_type,
                      })}
                    >
                      Customize
                    </Button>
                  </div>
                </CardBody>
              </Card>
            ))}
          </div>
        )}
      </section>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={confirmDeleteId != null}
        onClose={() => setConfirmDeleteId(null)}
        title="Delete Report"
        size="sm"
      >
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Are you sure you want to delete this report? This action cannot be undone.
        </p>
        <ModalFooter>
          <Button variant="secondary" size="sm" onClick={() => setConfirmDeleteId(null)}>
            Cancel
          </Button>
          <Button
            variant="danger"
            size="sm"
            onClick={handleDeleteReport}
            disabled={deleteReport.isPending}
          >
            {deleteReport.isPending ? <Spinner size="sm" className="mr-2" /> : null}
            Delete
          </Button>
        </ModalFooter>
      </Modal>
    </div>
  );
}

export default ReportsPage;
