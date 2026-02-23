/**
 * Multi-step report builder wizard.
 * Steps: Entity -> Metric -> Grouping -> Filters -> Chart Type -> Preview & Save
 */

import { useState } from 'react';
import { Button } from '../../../components/ui/Button';
import { Spinner } from '../../../components/ui/Spinner';
import { ReportChart } from './ReportChart';
import { useExecuteReport, useCreateSavedReport } from '../../../hooks/useReports';
import type { ReportDefinition, ReportResult } from '../../../api/reports';

interface ReportBuilderProps {
  onClose: () => void;
  onSaved: () => void;
  initialDefinition?: Partial<ReportDefinition>;
}

const ENTITY_TYPES = [
  { value: 'contacts', label: 'Contacts' },
  { value: 'companies', label: 'Companies' },
  { value: 'leads', label: 'Leads' },
  { value: 'opportunities', label: 'Opportunities' },
  { value: 'payments', label: 'Payments' },
  { value: 'contracts', label: 'Contracts' },
  { value: 'activities', label: 'Activities' },
  { value: 'campaigns', label: 'Campaigns' },
];

const METRICS = [
  { value: 'count', label: 'Count' },
  { value: 'sum', label: 'Sum' },
  { value: 'avg', label: 'Average' },
  { value: 'min', label: 'Minimum' },
  { value: 'max', label: 'Maximum' },
];

const NUMERIC_FIELDS: Record<string, string[]> = {
  leads: ['score', 'budget_amount'],
  contacts: [],
  opportunities: ['amount', 'probability'],
  activities: ['call_duration_minutes'],
  campaigns: ['budget_amount', 'actual_cost', 'expected_revenue', 'actual_revenue', 'num_sent', 'num_responses', 'num_converted'],
  companies: ['annual_revenue', 'employee_count'],
  payments: ['amount'],
  contracts: ['value'],
};

const GROUP_BY_FIELDS: Record<string, string[]> = {
  leads: ['status', 'industry', 'owner_id'],
  contacts: ['status', 'owner_id'],
  opportunities: ['source', 'owner_id', 'pipeline_stage_id'],
  activities: ['activity_type', 'priority', 'owner_id'],
  campaigns: ['campaign_type', 'status'],
  companies: ['industry', 'status', 'segment', 'owner_id'],
  payments: ['status', 'currency', 'payment_method', 'owner_id'],
  contracts: ['status', 'currency', 'owner_id'],
};

const DATE_GROUPS = [
  { value: '', label: 'None' },
  { value: 'day', label: 'Day' },
  { value: 'week', label: 'Week' },
  { value: 'month', label: 'Month' },
  { value: 'quarter', label: 'Quarter' },
  { value: 'year', label: 'Year' },
];

const CHART_TYPES = [
  { value: 'bar', label: 'Bar Chart' },
  { value: 'line', label: 'Line Chart' },
  { value: 'pie', label: 'Pie Chart' },
  { value: 'table', label: 'Table' },
];

const TOTAL_STEPS = 6;

export function ReportBuilder({ onClose, onSaved, initialDefinition }: ReportBuilderProps) {
  const [step, setStep] = useState(1);
  const [entityType, setEntityType] = useState(initialDefinition?.entity_type || '');
  const [metric, setMetric] = useState(initialDefinition?.metric || 'count');
  const [metricField, setMetricField] = useState(initialDefinition?.metric_field || '');
  const [groupBy, setGroupBy] = useState(initialDefinition?.group_by || '');
  const [dateGroup, setDateGroup] = useState(initialDefinition?.date_group || '');
  const [chartType, setChartType] = useState(initialDefinition?.chart_type || 'bar');
  const [reportName, setReportName] = useState('');
  const [previewResult, setPreviewResult] = useState<ReportResult | null>(null);

  const executeReport = useExecuteReport();
  const createReport = useCreateSavedReport();

  const needsMetricField = metric !== 'count';
  const numericFields = NUMERIC_FIELDS[entityType] || [];
  const groupByFields = GROUP_BY_FIELDS[entityType] || [];

  const getDefinition = (): ReportDefinition => ({
    entity_type: entityType,
    metric,
    metric_field: needsMetricField && metricField ? metricField : null,
    group_by: groupBy || null,
    date_group: dateGroup || null,
    filters: null,
    chart_type: chartType,
  });

  const canAdvance = () => {
    switch (step) {
      case 1: return !!entityType;
      case 2: return metric === 'count' || !!metricField;
      case 3: return true; // grouping is optional
      case 4: return true; // filters step (skipped for simplicity)
      case 5: return !!chartType;
      case 6: return true;
      default: return false;
    }
  };

  const handleNext = async () => {
    if (step === 4) {
      // Skip filters step, go to chart type
      setStep(5);
      return;
    }
    if (step === 5) {
      // Preview step: execute the report
      const definition = getDefinition();
      try {
        const result = await executeReport.mutateAsync(definition);
        setPreviewResult(result);
      } catch {
        setPreviewResult(null);
      }
      setStep(6);
      return;
    }
    if (step < TOTAL_STEPS) {
      setStep(step + 1);
    }
  };

  const handleBack = () => {
    if (step === 5) {
      // Skip filters step going backward
      setStep(3);
      return;
    }
    if (step > 1) {
      setStep(step - 1);
    }
  };

  const handleSave = async () => {
    if (!reportName.trim()) return;
    const definition = getDefinition();
    await createReport.mutateAsync({
      name: reportName,
      entity_type: definition.entity_type,
      metric: definition.metric,
      metric_field: definition.metric_field,
      group_by: definition.group_by,
      date_group: definition.date_group,
      chart_type: definition.chart_type,
      filters: definition.filters,
    });
    onSaved();
  };

  const renderStepIndicator = () => (
    <div className="flex items-center gap-1 mb-6">
      {Array.from({ length: TOTAL_STEPS }, (_, i) => i + 1)
        .filter((s) => s !== 4) // Skip filters step in indicator
        .map((s) => (
          <div key={s} className="flex items-center">
            <div
              className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                s === step
                  ? 'bg-primary-500 text-white'
                  : s < step
                    ? 'bg-primary-100 text-primary-700'
                    : 'bg-gray-100 text-gray-400'
              }`}
            >
              {s === 4 ? 4 : s > 4 ? s - 1 : s}
            </div>
            {s < TOTAL_STEPS && s !== 4 && <div className="w-6 h-0.5 bg-gray-200 mx-1" />}
          </div>
        ))}
    </div>
  );

  const renderStep = () => {
    switch (step) {
      case 1:
        return (
          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-3">Select Entity Type</h3>
            <div className="grid grid-cols-2 gap-2">
              {ENTITY_TYPES.map((et) => (
                <button
                  key={et.value}
                  onClick={() => {
                    setEntityType(et.value);
                    setMetricField('');
                    setGroupBy('');
                  }}
                  className={`p-3 rounded-lg border-2 text-sm font-medium text-left transition-colors ${
                    entityType === et.value
                      ? 'border-primary-500 bg-primary-50 text-primary-700'
                      : 'border-gray-200 hover:border-gray-300 text-gray-700'
                  }`}
                >
                  {et.label}
                </button>
              ))}
            </div>
          </div>
        );

      case 2:
        return (
          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-3">Select Metric</h3>
            <div className="space-y-2 mb-4">
              {METRICS.map((m) => (
                <button
                  key={m.value}
                  onClick={() => {
                    setMetric(m.value);
                    if (m.value === 'count') setMetricField('');
                  }}
                  className={`w-full p-3 rounded-lg border-2 text-sm font-medium text-left transition-colors ${
                    metric === m.value
                      ? 'border-primary-500 bg-primary-50 text-primary-700'
                      : 'border-gray-200 hover:border-gray-300 text-gray-700'
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
            {needsMetricField && (
              <div>
                <h3 className="text-sm font-medium text-gray-700 mb-2">Select Field</h3>
                {numericFields.length === 0 ? (
                  <p className="text-sm text-gray-500">No numeric fields available for this entity. Use "Count" instead.</p>
                ) : (
                  <div className="space-y-2">
                    {numericFields.map((field) => (
                      <button
                        key={field}
                        onClick={() => setMetricField(field)}
                        className={`w-full p-3 rounded-lg border-2 text-sm font-medium text-left transition-colors ${
                          metricField === field
                            ? 'border-primary-500 bg-primary-50 text-primary-700'
                            : 'border-gray-200 hover:border-gray-300 text-gray-700'
                        }`}
                      >
                        {field.replace(/_/g, ' ')}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        );

      case 3:
        return (
          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-3">Group By Field</h3>
            <div className="space-y-2 mb-4">
              <button
                onClick={() => setGroupBy('')}
                className={`w-full p-3 rounded-lg border-2 text-sm font-medium text-left transition-colors ${
                  !groupBy && !dateGroup
                    ? 'border-primary-500 bg-primary-50 text-primary-700'
                    : 'border-gray-200 hover:border-gray-300 text-gray-700'
                }`}
              >
                No grouping (single aggregate)
              </button>
              {groupByFields.map((field) => (
                <button
                  key={field}
                  onClick={() => { setGroupBy(field); setDateGroup(''); }}
                  className={`w-full p-3 rounded-lg border-2 text-sm font-medium text-left transition-colors ${
                    groupBy === field
                      ? 'border-primary-500 bg-primary-50 text-primary-700'
                      : 'border-gray-200 hover:border-gray-300 text-gray-700'
                  }`}
                >
                  {field.replace(/_/g, ' ')}
                </button>
              ))}
            </div>
            <h3 className="text-sm font-medium text-gray-700 mb-2">Or Group By Date</h3>
            <div className="flex flex-wrap gap-2">
              {DATE_GROUPS.map((dg) => (
                <button
                  key={dg.value}
                  onClick={() => { setDateGroup(dg.value); if (dg.value) setGroupBy(''); }}
                  className={`px-4 py-2 rounded-lg border-2 text-sm font-medium transition-colors ${
                    dateGroup === dg.value
                      ? 'border-primary-500 bg-primary-50 text-primary-700'
                      : 'border-gray-200 hover:border-gray-300 text-gray-700'
                  }`}
                >
                  {dg.label}
                </button>
              ))}
            </div>
          </div>
        );

      case 5:
        return (
          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-3">Select Chart Type</h3>
            <div className="grid grid-cols-2 gap-2">
              {CHART_TYPES.map((ct) => (
                <button
                  key={ct.value}
                  onClick={() => setChartType(ct.value)}
                  className={`p-4 rounded-lg border-2 text-sm font-medium text-center transition-colors ${
                    chartType === ct.value
                      ? 'border-primary-500 bg-primary-50 text-primary-700'
                      : 'border-gray-200 hover:border-gray-300 text-gray-700'
                  }`}
                >
                  {ct.label}
                </button>
              ))}
            </div>
          </div>
        );

      case 6:
        return (
          <div>
            <h3 className="text-sm font-medium text-gray-700 mb-3">Preview & Save</h3>
            {executeReport.isPending ? (
              <div className="flex items-center justify-center h-32">
                <Spinner size="lg" />
              </div>
            ) : executeReport.isError ? (
              <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
                Failed to execute report. Please check your configuration.
              </div>
            ) : previewResult ? (
              <div className="border border-gray-200 rounded-lg p-4 mb-4">
                <ReportChart
                  chartType={previewResult.chart_type}
                  data={previewResult.data}
                  total={previewResult.total}
                />
                {previewResult.total != null && (
                  <div className="mt-3 text-sm text-gray-600 font-medium">
                    Total: {previewResult.total.toLocaleString()}
                  </div>
                )}
              </div>
            ) : null}
            <div className="mt-4">
              <label htmlFor="report-name" className="block text-sm font-medium text-gray-700 mb-1">
                Report Name
              </label>
              <input
                id="report-name"
                type="text"
                value={reportName}
                onChange={(e) => setReportName(e.target.value)}
                placeholder="Enter a name for this report..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:border-primary-500"
              />
            </div>
          </div>
        );

      default:
        return null;
    }
  };

  return (
    <div>
      {renderStepIndicator()}
      <div className="min-h-[300px]">{renderStep()}</div>
      <div className="flex items-center justify-between mt-6 pt-4 border-t border-gray-200">
        <div>
          {step > 1 && (
            <Button variant="secondary" size="sm" onClick={handleBack}>
              Back
            </Button>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={onClose}>
            Cancel
          </Button>
          {step < TOTAL_STEPS ? (
            <Button size="sm" onClick={handleNext} disabled={!canAdvance()}>
              Next
            </Button>
          ) : (
            <Button
              size="sm"
              onClick={handleSave}
              disabled={!reportName.trim() || createReport.isPending}
            >
              {createReport.isPending ? <Spinner size="sm" className="mr-2" /> : null}
              Save Report
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
