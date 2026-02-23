import { useState } from 'react';
import { Button, Modal } from '../../../components/ui';
import { useCreateSavedFilter, useFilterAggregate } from '../../../hooks/useFilters';
import { showSuccess, showError } from '../../../utils/toast';
import type { FilterCondition, FilterGroup, AggregateResponse } from '../../../api/filters';
import {
  PlusIcon,
  TrashIcon,
  FunnelIcon,
  BookmarkIcon,
} from '@heroicons/react/24/outline';

// Field definitions for the contacts entity
const FIELD_OPTIONS = [
  { value: 'first_name', label: 'First Name', type: 'text' },
  { value: 'last_name', label: 'Last Name', type: 'text' },
  { value: 'email', label: 'Email', type: 'text' },
  { value: 'city', label: 'City', type: 'text' },
  { value: 'state', label: 'State', type: 'text' },
  { value: 'status', label: 'Status', type: 'select', options: ['active', 'inactive'] },
  { value: 'sales_code', label: 'Sales Code', type: 'text' },
  { value: 'job_title', label: 'Job Title', type: 'text' },
  { value: 'department', label: 'Department', type: 'text' },
] as const;

const COMPANY_FIELD_OPTIONS = [
  { value: 'name', label: 'Company Name', type: 'text' },
  { value: 'company_size', label: 'Company Size', type: 'select', options: ['1-10', '11-50', '51-200', '201-500', '501-1000', '1001-5000', '5000+'] },
  { value: 'segment', label: 'Segment', type: 'text' },
  { value: 'city', label: 'City', type: 'text' },
  { value: 'state', label: 'State', type: 'text' },
  { value: 'annual_revenue', label: 'Annual Revenue', type: 'number' },
  { value: 'industry', label: 'Industry', type: 'text' },
  { value: 'status', label: 'Status', type: 'select', options: ['prospect', 'customer', 'churned'] },
  { value: 'employee_count', label: 'Employee Count', type: 'number' },
] as const;

const OPERATOR_OPTIONS = [
  { value: 'eq', label: 'Equals' },
  { value: 'neq', label: 'Not Equals' },
  { value: 'contains', label: 'Contains' },
  { value: 'not_contains', label: 'Does Not Contain' },
  { value: 'gt', label: 'Greater Than' },
  { value: 'lt', label: 'Less Than' },
  { value: 'gte', label: 'Greater Than or Equal' },
  { value: 'lte', label: 'Less Than or Equal' },
  { value: 'is_empty', label: 'Is Empty' },
  { value: 'is_not_empty', label: 'Is Not Empty' },
  { value: 'between', label: 'Between' },
];

const NO_VALUE_OPS = ['is_empty', 'is_not_empty'];

interface ConditionRow {
  id: number;
  field: string;
  op: string;
  value: string;
  valueTo: string; // for "between" operator
}

interface SmartListBuilderProps {
  entityType: 'contacts' | 'companies';
  onApplyFilters: (filters: FilterGroup) => void;
  onClose: () => void;
}

let nextConditionId = 1;

function buildFilterGroup(conditions: ConditionRow[], groupOperator: 'and' | 'or'): FilterGroup {
  const parsedConditions: FilterCondition[] = conditions
    .filter((c) => c.field && c.op)
    .map((c) => {
      const condition: FilterCondition = {
        field: c.field,
        op: c.op,
      };

      if (!NO_VALUE_OPS.includes(c.op)) {
        if (c.op === 'between') {
          condition.value = [
            isNaN(Number(c.value)) ? c.value : Number(c.value),
            isNaN(Number(c.valueTo)) ? c.valueTo : Number(c.valueTo),
          ];
        } else {
          // Try to parse as number if the value looks numeric
          const numVal = Number(c.value);
          condition.value = isNaN(numVal) || c.value === '' ? c.value : numVal;
        }
      }

      return condition;
    });

  return {
    operator: groupOperator,
    conditions: parsedConditions,
  };
}

export function SmartListBuilder({ entityType, onApplyFilters, onClose }: SmartListBuilderProps) {
  const fieldOptions = entityType === 'companies' ? COMPANY_FIELD_OPTIONS : FIELD_OPTIONS;
  const [conditions, setConditions] = useState<ConditionRow[]>([
    { id: nextConditionId++, field: '', op: 'eq', value: '', valueTo: '' },
  ]);
  const [groupOperator, setGroupOperator] = useState<'and' | 'or'>('and');
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [filterName, setFilterName] = useState('');
  const [isPublic, setIsPublic] = useState(false);
  const [aggregateResult, setAggregateResult] = useState<AggregateResponse | null>(null);

  const createFilterMutation = useCreateSavedFilter();
  const aggregateMutation = useFilterAggregate();

  const addCondition = () => {
    setConditions((curr) => [
      ...curr,
      { id: nextConditionId++, field: '', op: 'eq', value: '', valueTo: '' },
    ]);
  };

  const removeCondition = (id: number) => {
    setConditions((curr) => curr.filter((c) => c.id !== id));
  };

  const updateCondition = (id: number, updates: Partial<ConditionRow>) => {
    setConditions((curr) =>
      curr.map((c) => (c.id === id ? { ...c, ...updates } : c))
    );
  };

  const getFieldDef = (fieldValue: string) => {
    return fieldOptions.find((f) => f.value === fieldValue);
  };

  const hasValidConditions = conditions.some((c) => c.field && c.op);

  const handleViewResults = async () => {
    if (!hasValidConditions) return;
    const filters = buildFilterGroup(conditions, groupOperator);
    const metricsToRequest = ['count'];
    if (entityType === 'companies') {
      metricsToRequest.push('sum:annual_revenue');
    }
    try {
      const result = await aggregateMutation.mutateAsync({
        entity_type: entityType,
        filters,
        metrics: metricsToRequest,
      });
      setAggregateResult(result);
    } catch {
      showError('Failed to run aggregate query');
    }
  };

  const handleApplyFilters = () => {
    if (!hasValidConditions) return;
    const filters = buildFilterGroup(conditions, groupOperator);
    onApplyFilters(filters);
  };

  const handleSave = async () => {
    if (!filterName.trim() || !hasValidConditions) return;
    const filters = buildFilterGroup(conditions, groupOperator);
    try {
      await createFilterMutation.mutateAsync({
        name: filterName.trim(),
        entity_type: entityType,
        filters,
        is_public: isPublic,
      });
      showSuccess('Smart list saved successfully');
      setShowSaveDialog(false);
      setFilterName('');
      setIsPublic(false);
    } catch {
      showError('Failed to save smart list');
    }
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          Smart List Builder
        </h3>
        <div className="flex items-center gap-2">
          <label htmlFor="group-operator" className="text-sm text-gray-600 dark:text-gray-400">
            Match
          </label>
          <select
            id="group-operator"
            value={groupOperator}
            onChange={(e) => setGroupOperator(e.target.value as 'and' | 'or')}
            className="rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm px-2 py-1 text-gray-900 dark:text-gray-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary-500"
          >
            <option value="and">All conditions (AND)</option>
            <option value="or">Any condition (OR)</option>
          </select>
        </div>
      </div>

      {/* Condition Rows */}
      <div className="space-y-3">
        {conditions.map((condition, index) => {
          const fieldDef = getFieldDef(condition.field);
          const isNoValueOp = NO_VALUE_OPS.includes(condition.op);
          const isBetween = condition.op === 'between';

          return (
            <div
              key={condition.id}
              className="flex flex-wrap items-center gap-2 p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-600"
            >
              {index > 0 && (
                <span className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase w-full mb-1">
                  {groupOperator}
                </span>
              )}

              {/* Field selector */}
              <select
                aria-label="Field"
                value={condition.field}
                onChange={(e) => updateCondition(condition.id, { field: e.target.value, value: '', valueTo: '' })}
                className="flex-1 min-w-[140px] rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm px-2 py-2 text-gray-900 dark:text-gray-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary-500"
              >
                <option value="">Select field...</option>
                {fieldOptions.map((f) => (
                  <option key={f.value} value={f.value}>
                    {f.label}
                  </option>
                ))}
              </select>

              {/* Operator selector */}
              <select
                aria-label="Operator"
                value={condition.op}
                onChange={(e) => updateCondition(condition.id, { op: e.target.value })}
                className="flex-1 min-w-[140px] rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm px-2 py-2 text-gray-900 dark:text-gray-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary-500"
              >
                {OPERATOR_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>

              {/* Value input */}
              {!isNoValueOp && (
                <>
                  {fieldDef && 'options' in fieldDef && fieldDef.options ? (
                    <select
                      aria-label="Value"
                      value={condition.value}
                      onChange={(e) => updateCondition(condition.id, { value: e.target.value })}
                      className="flex-1 min-w-[140px] rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm px-2 py-2 text-gray-900 dark:text-gray-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary-500"
                    >
                      <option value="">Select value...</option>
                      {fieldDef.options.map((opt: string) => (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type={fieldDef?.type === 'number' ? 'number' : 'text'}
                      aria-label="Value"
                      value={condition.value}
                      onChange={(e) => updateCondition(condition.id, { value: e.target.value })}
                      placeholder="Value..."
                      className="flex-1 min-w-[120px] rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm px-2 py-2 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary-500"
                    />
                  )}

                  {isBetween && (
                    <>
                      <span className="text-sm text-gray-500 dark:text-gray-400">and</span>
                      <input
                        type={fieldDef?.type === 'number' ? 'number' : 'text'}
                        aria-label="Value to"
                        value={condition.valueTo}
                        onChange={(e) => updateCondition(condition.id, { valueTo: e.target.value })}
                        placeholder="To..."
                        className="flex-1 min-w-[120px] rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm px-2 py-2 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary-500"
                      />
                    </>
                  )}
                </>
              )}

              {/* Remove button */}
              {conditions.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeCondition(condition.id)}
                  className="p-1.5 text-red-500 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-md"
                  aria-label="Remove condition"
                >
                  <TrashIcon className="h-4 w-4" />
                </button>
              )}
            </div>
          );
        })}
      </div>

      {/* Add condition */}
      <button
        type="button"
        onClick={addCondition}
        className="flex items-center gap-1 text-sm text-primary-600 hover:text-primary-700 font-medium"
      >
        <PlusIcon className="h-4 w-4" />
        Add condition
      </button>

      {/* Aggregate Results */}
      {aggregateResult && (
        <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
          <h4 className="text-sm font-semibold text-blue-900 dark:text-blue-200 mb-2">
            Results Preview
          </h4>
          <div className="flex flex-wrap gap-4 mb-3">
            <div className="text-sm text-blue-800 dark:text-blue-300">
              <span className="font-medium">Matching records:</span>{' '}
              <span className="font-bold text-lg">{aggregateResult.count}</span>
            </div>
            {Object.entries(aggregateResult.metrics).map(([key, value]) =>
              key !== 'count' ? (
                <div key={key} className="text-sm text-blue-800 dark:text-blue-300">
                  <span className="font-medium">{key}:</span>{' '}
                  <span className="font-bold">
                    {typeof value === 'number' ? value.toLocaleString() : value}
                  </span>
                </div>
              ) : null
            )}
          </div>
          {aggregateResult.sample_entities.length > 0 && (
            <div>
              <p className="text-xs font-medium text-blue-700 dark:text-blue-400 mb-1">
                Sample ({Math.min(5, aggregateResult.sample_entities.length)} of {aggregateResult.count}):
              </p>
              <div className="space-y-1">
                {aggregateResult.sample_entities.map((entity, i) => (
                  <div
                    key={entity.id as number ?? i}
                    className="text-xs text-blue-700 dark:text-blue-300 bg-blue-100 dark:bg-blue-900/30 px-2 py-1 rounded"
                  >
                    {entity.first_name ? `${String(entity.first_name)} ${String(entity.last_name ?? '')}` : String(entity.name ?? `ID: ${entity.id}`)}
                    {entity.email ? ` - ${String(entity.email)}` : ''}
                    {entity.status ? ` (${String(entity.status)})` : ''}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-gray-200 dark:border-gray-700">
        <Button
          variant="secondary"
          onClick={handleViewResults}
          disabled={!hasValidConditions || aggregateMutation.isPending}
          leftIcon={<FunnelIcon className="h-4 w-4" />}
        >
          {aggregateMutation.isPending ? 'Loading...' : 'View Results'}
        </Button>
        <Button
          onClick={handleApplyFilters}
          disabled={!hasValidConditions}
        >
          Apply Filters
        </Button>
        <Button
          variant="secondary"
          onClick={() => setShowSaveDialog(true)}
          disabled={!hasValidConditions}
          leftIcon={<BookmarkIcon className="h-4 w-4" />}
        >
          Save as Smart List
        </Button>
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
      </div>

      {/* Save Dialog */}
      <Modal
        isOpen={showSaveDialog}
        onClose={() => setShowSaveDialog(false)}
        title="Save Smart List"
        size="sm"
      >
        <div className="space-y-4">
          <div>
            <label htmlFor="filter-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Name
            </label>
            <input
              id="filter-name"
              type="text"
              value={filterName}
              onChange={(e) => setFilterName(e.target.value)}
              placeholder="e.g. High-value prospects..."
              className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm px-3 py-2 text-gray-900 dark:text-gray-100 placeholder-gray-400 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary-500"
            />
          </div>
          <div className="flex items-center gap-2">
            <input
              id="is-public"
              type="checkbox"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
            />
            <label htmlFor="is-public" className="text-sm text-gray-700 dark:text-gray-300">
              Make visible to all team members
            </label>
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowSaveDialog(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={!filterName.trim() || createFilterMutation.isPending}
            >
              {createFilterMutation.isPending ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
