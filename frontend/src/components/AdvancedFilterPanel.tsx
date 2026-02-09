/**
 * Reusable Advanced Filter Panel component.
 * Supports adding/removing filter conditions, AND/OR groups,
 * saving/loading filter presets, and URL sync.
 */

import { useState, useCallback } from 'react';
import {
  FunnelIcon,
  PlusIcon,
  TrashIcon,
  BookmarkIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { Button } from './ui/Button';
import { useSavedFilters, useCreateSavedFilter, useDeleteSavedFilter } from '../hooks/useFilters';
import type { FilterCondition, FilterGroup, SavedFilter } from '../api/filters';

// =============================================================================
// Field definitions per entity type
// =============================================================================

export interface FieldDef {
  name: string;
  label: string;
  type: 'string' | 'number' | 'date' | 'select';
  options?: { value: string; label: string }[];
}

const OPERATOR_LABELS: Record<string, string> = {
  eq: 'equals',
  neq: 'not equals',
  contains: 'contains',
  not_contains: 'does not contain',
  gt: 'greater than',
  lt: 'less than',
  gte: 'greater or equal',
  lte: 'less or equal',
  is_empty: 'is empty',
  is_not_empty: 'is not empty',
  in: 'is in',
  not_in: 'is not in',
  between: 'between',
};

const OPERATORS_BY_TYPE: Record<string, string[]> = {
  string: ['eq', 'neq', 'contains', 'not_contains', 'is_empty', 'is_not_empty'],
  number: ['eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'between', 'is_empty', 'is_not_empty'],
  date: ['eq', 'neq', 'gt', 'lt', 'gte', 'lte', 'between', 'is_empty', 'is_not_empty'],
  select: ['eq', 'neq', 'in', 'not_in', 'is_empty', 'is_not_empty'],
};

const NO_VALUE_OPS = new Set(['is_empty', 'is_not_empty']);

// Entity field definitions
export const ENTITY_FIELDS: Record<string, FieldDef[]> = {
  leads: [
    { name: 'first_name', label: 'First Name', type: 'string' },
    { name: 'last_name', label: 'Last Name', type: 'string' },
    { name: 'email', label: 'Email', type: 'string' },
    { name: 'company_name', label: 'Company', type: 'string' },
    { name: 'status', label: 'Status', type: 'select', options: [
      { value: 'new', label: 'New' },
      { value: 'contacted', label: 'Contacted' },
      { value: 'qualified', label: 'Qualified' },
      { value: 'unqualified', label: 'Unqualified' },
      { value: 'nurturing', label: 'Nurturing' },
    ]},
    { name: 'score', label: 'Score', type: 'number' },
    { name: 'budget_amount', label: 'Budget', type: 'number' },
    { name: 'created_at', label: 'Created Date', type: 'date' },
  ],
  contacts: [
    { name: 'first_name', label: 'First Name', type: 'string' },
    { name: 'last_name', label: 'Last Name', type: 'string' },
    { name: 'email', label: 'Email', type: 'string' },
    { name: 'phone', label: 'Phone', type: 'string' },
    { name: 'job_title', label: 'Job Title', type: 'string' },
    { name: 'city', label: 'City', type: 'string' },
    { name: 'country', label: 'Country', type: 'string' },
    { name: 'status', label: 'Status', type: 'select', options: [
      { value: 'active', label: 'Active' },
      { value: 'inactive', label: 'Inactive' },
    ]},
    { name: 'created_at', label: 'Created Date', type: 'date' },
  ],
  opportunities: [
    { name: 'name', label: 'Name', type: 'string' },
    { name: 'amount', label: 'Amount', type: 'number' },
    { name: 'probability', label: 'Probability', type: 'number' },
    { name: 'expected_close_date', label: 'Close Date', type: 'date' },
    { name: 'source', label: 'Source', type: 'string' },
    { name: 'created_at', label: 'Created Date', type: 'date' },
  ],
  companies: [
    { name: 'name', label: 'Name', type: 'string' },
    { name: 'industry', label: 'Industry', type: 'string' },
    { name: 'website', label: 'Website', type: 'string' },
    { name: 'city', label: 'City', type: 'string' },
    { name: 'country', label: 'Country', type: 'string' },
    { name: 'annual_revenue', label: 'Annual Revenue', type: 'number' },
    { name: 'employee_count', label: 'Employee Count', type: 'number' },
    { name: 'status', label: 'Status', type: 'select', options: [
      { value: 'active', label: 'Active' },
      { value: 'inactive', label: 'Inactive' },
      { value: 'prospect', label: 'Prospect' },
    ]},
    { name: 'created_at', label: 'Created Date', type: 'date' },
  ],
  activities: [
    { name: 'subject', label: 'Subject', type: 'string' },
    { name: 'activity_type', label: 'Type', type: 'select', options: [
      { value: 'call', label: 'Call' },
      { value: 'email', label: 'Email' },
      { value: 'meeting', label: 'Meeting' },
      { value: 'task', label: 'Task' },
      { value: 'note', label: 'Note' },
    ]},
    { name: 'priority', label: 'Priority', type: 'select', options: [
      { value: 'low', label: 'Low' },
      { value: 'normal', label: 'Normal' },
      { value: 'high', label: 'High' },
      { value: 'urgent', label: 'Urgent' },
    ]},
    { name: 'is_completed', label: 'Completed', type: 'select', options: [
      { value: 'true', label: 'Yes' },
      { value: 'false', label: 'No' },
    ]},
    { name: 'due_date', label: 'Due Date', type: 'date' },
    { name: 'created_at', label: 'Created Date', type: 'date' },
  ],
};

// =============================================================================
// Types
// =============================================================================

interface FilterRowData {
  id: string;
  field: string;
  op: string;
  value: string;
}

interface AdvancedFilterPanelProps {
  entityType: string;
  onApply: (filters: FilterGroup | null) => void;
  className?: string;
}

// =============================================================================
// Helper functions
// =============================================================================

function generateId(): string {
  return Math.random().toString(36).substring(2, 9);
}

function createEmptyRow(): FilterRowData {
  return { id: generateId(), field: '', op: 'eq', value: '' };
}

function buildFilterGroup(rows: FilterRowData[], operator: 'and' | 'or'): FilterGroup | null {
  const conditions: FilterCondition[] = rows
    .filter((r) => r.field && r.op)
    .map((r) => {
      const cond: FilterCondition = { field: r.field, op: r.op };
      if (!NO_VALUE_OPS.has(r.op)) {
        if (r.op === 'between') {
          const parts = r.value.split(',').map((s) => s.trim());
          cond.value = parts;
        } else if (r.op === 'in' || r.op === 'not_in') {
          cond.value = r.value.split(',').map((s) => s.trim());
        } else {
          cond.value = r.value;
        }
      }
      return cond;
    });

  if (conditions.length === 0) return null;
  return { operator, conditions };
}

function rowsFromFilterGroup(group: FilterGroup): FilterRowData[] {
  return group.conditions
    .filter((c): c is FilterCondition => 'field' in c)
    .map((c) => ({
      id: generateId(),
      field: c.field,
      op: c.op,
      value: Array.isArray(c.value) ? c.value.join(', ') : String(c.value ?? ''),
    }));
}

// =============================================================================
// Component
// =============================================================================

export function AdvancedFilterPanel({ entityType, onApply, className }: AdvancedFilterPanelProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [rows, setRows] = useState<FilterRowData[]>([createEmptyRow()]);
  const [operator, setOperator] = useState<'and' | 'or'>('and');
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [filterName, setFilterName] = useState('');
  const [activeFilterCount, setActiveFilterCount] = useState(0);

  const fields = ENTITY_FIELDS[entityType] || [];
  const { data: savedFilters } = useSavedFilters(entityType);
  const createFilterMutation = useCreateSavedFilter();
  const deleteFilterMutation = useDeleteSavedFilter();

  const getFieldDef = useCallback(
    (fieldName: string) => fields.find((f) => f.name === fieldName),
    [fields]
  );

  const handleAddRow = () => {
    setRows((prev) => [...prev, createEmptyRow()]);
  };

  const handleRemoveRow = (id: string) => {
    setRows((prev) => {
      const next = prev.filter((r) => r.id !== id);
      return next.length === 0 ? [createEmptyRow()] : next;
    });
  };

  const handleRowChange = (id: string, field: keyof FilterRowData, value: string) => {
    setRows((prev) =>
      prev.map((r) => {
        if (r.id !== id) return r;
        const updated = { ...r, [field]: value };
        if (field === 'field') {
          updated.op = 'eq';
          updated.value = '';
        }
        return updated;
      })
    );
  };

  const handleApply = () => {
    const group = buildFilterGroup(rows, operator);
    const count = rows.filter((r) => r.field && r.op).length;
    setActiveFilterCount(count);
    onApply(group);
  };

  const handleClear = () => {
    setRows([createEmptyRow()]);
    setOperator('and');
    setActiveFilterCount(0);
    onApply(null);
  };

  const handleSave = async () => {
    const group = buildFilterGroup(rows, operator);
    if (!group || !filterName.trim()) return;
    await createFilterMutation.mutateAsync({
      name: filterName.trim(),
      entity_type: entityType,
      filters: group,
    });
    setFilterName('');
    setShowSaveDialog(false);
  };

  const handleLoadPreset = (filter: SavedFilter) => {
    const loadedRows = rowsFromFilterGroup(filter.filters);
    setRows(loadedRows.length > 0 ? loadedRows : [createEmptyRow()]);
    setOperator(filter.filters.operator);
    const group = filter.filters;
    const count = group.conditions.filter((c): c is FilterCondition => 'field' in c).length;
    setActiveFilterCount(count);
    onApply(group);
  };

  const handleDeletePreset = async (id: number) => {
    await deleteFilterMutation.mutateAsync(id);
  };

  return (
    <div className={className}>
      <div className="flex items-center gap-2">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setIsOpen(!isOpen)}
          aria-label="Toggle advanced filters"
        >
          <FunnelIcon className="h-4 w-4 mr-1.5" aria-hidden="true" />
          Filters
          {activeFilterCount > 0 && (
            <span className="ml-1.5 inline-flex items-center justify-center h-5 w-5 rounded-full bg-primary-100 text-primary-700 text-xs font-medium">
              {activeFilterCount}
            </span>
          )}
        </Button>
        {activeFilterCount > 0 && (
          <button
            onClick={handleClear}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            Clear all
          </button>
        )}
      </div>

      {isOpen && (
        <div className="mt-3 bg-white border border-gray-200 rounded-lg shadow-sm p-4 space-y-4">
          {/* Operator toggle */}
          <div className="flex items-center gap-2 text-sm">
            <span className="text-gray-600">Match</span>
            <button
              onClick={() => setOperator('and')}
              className={`px-2.5 py-1 rounded-md text-sm font-medium transition-colors ${
                operator === 'and'
                  ? 'bg-primary-100 text-primary-700'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              ALL
            </button>
            <button
              onClick={() => setOperator('or')}
              className={`px-2.5 py-1 rounded-md text-sm font-medium transition-colors ${
                operator === 'or'
                  ? 'bg-primary-100 text-primary-700'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
            >
              ANY
            </button>
            <span className="text-gray-600">of the following conditions</span>
          </div>

          {/* Filter rows */}
          <div className="space-y-2">
            {rows.map((row) => {
              const fieldDef = getFieldDef(row.field);
              const fieldType = fieldDef?.type || 'string';
              const operators = OPERATORS_BY_TYPE[fieldType] || OPERATORS_BY_TYPE.string;
              const needsValue = !NO_VALUE_OPS.has(row.op);

              return (
                <div key={row.id} className="flex items-center gap-2">
                  {/* Field selector */}
                  <select
                    value={row.field}
                    onChange={(e) => handleRowChange(row.id, 'field', e.target.value)}
                    className="block w-40 rounded-md border-gray-300 text-sm focus:border-primary-500 focus:ring-primary-500"
                    aria-label="Filter field"
                  >
                    <option value="">Select field...</option>
                    {fields.map((f) => (
                      <option key={f.name} value={f.name}>
                        {f.label}
                      </option>
                    ))}
                  </select>

                  {/* Operator selector */}
                  <select
                    value={row.op}
                    onChange={(e) => handleRowChange(row.id, 'op', e.target.value)}
                    className="block w-40 rounded-md border-gray-300 text-sm focus:border-primary-500 focus:ring-primary-500"
                    aria-label="Filter operator"
                  >
                    {operators.map((op) => (
                      <option key={op} value={op}>
                        {OPERATOR_LABELS[op]}
                      </option>
                    ))}
                  </select>

                  {/* Value input */}
                  {needsValue && (
                    fieldDef?.type === 'select' && (row.op === 'eq' || row.op === 'neq') ? (
                      <select
                        value={row.value}
                        onChange={(e) => handleRowChange(row.id, 'value', e.target.value)}
                        className="block flex-1 min-w-0 rounded-md border-gray-300 text-sm focus:border-primary-500 focus:ring-primary-500"
                        aria-label="Filter value"
                      >
                        <option value="">Select...</option>
                        {fieldDef.options?.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type={fieldType === 'number' ? 'number' : fieldType === 'date' ? 'date' : 'text'}
                        value={row.value}
                        onChange={(e) => handleRowChange(row.id, 'value', e.target.value)}
                        placeholder={row.op === 'between' ? 'min, max' : 'Value...'}
                        className="block flex-1 min-w-0 rounded-md border-gray-300 text-sm focus:border-primary-500 focus:ring-primary-500"
                        aria-label="Filter value"
                      />
                    )
                  )}

                  {/* Remove row */}
                  <button
                    onClick={() => handleRemoveRow(row.id)}
                    className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
                    aria-label="Remove filter condition"
                  >
                    <TrashIcon className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              );
            })}
          </div>

          {/* Actions row */}
          <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-gray-100">
            <button
              onClick={handleAddRow}
              className="inline-flex items-center text-sm text-primary-600 hover:text-primary-700 font-medium"
            >
              <PlusIcon className="h-4 w-4 mr-1" aria-hidden="true" />
              Add condition
            </button>

            <div className="flex-1" />

            {/* Saved filter presets */}
            {savedFilters && savedFilters.length > 0 && (
              <div className="relative group">
                <Button variant="secondary" size="sm">
                  <BookmarkIcon className="h-4 w-4 mr-1" aria-hidden="true" />
                  Presets
                </Button>
                <div className="absolute right-0 top-full mt-1 w-56 bg-white border border-gray-200 rounded-lg shadow-lg z-10 hidden group-hover:block">
                  <div className="py-1">
                    {savedFilters.map((sf) => (
                      <div
                        key={sf.id}
                        className="flex items-center justify-between px-3 py-2 hover:bg-gray-50"
                      >
                        <button
                          onClick={() => handleLoadPreset(sf)}
                          className="text-sm text-gray-700 hover:text-gray-900 truncate flex-1 text-left"
                        >
                          {sf.name}
                        </button>
                        <button
                          onClick={() => handleDeletePreset(sf.id)}
                          className="ml-2 p-1 text-gray-400 hover:text-red-500"
                          aria-label={`Delete preset ${sf.name}`}
                        >
                          <XMarkIcon className="h-3.5 w-3.5" aria-hidden="true" />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            {/* Save current filter */}
            {!showSaveDialog ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setShowSaveDialog(true)}
              >
                <BookmarkIcon className="h-4 w-4 mr-1" aria-hidden="true" />
                Save
              </Button>
            ) : (
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={filterName}
                  onChange={(e) => setFilterName(e.target.value)}
                  placeholder="Filter name..."
                  className="block w-36 rounded-md border-gray-300 text-sm focus:border-primary-500 focus:ring-primary-500"
                  autoFocus
                />
                <Button
                  size="sm"
                  onClick={handleSave}
                  disabled={!filterName.trim() || createFilterMutation.isPending}
                >
                  Save
                </Button>
                <button
                  onClick={() => { setShowSaveDialog(false); setFilterName(''); }}
                  className="text-sm text-gray-500 hover:text-gray-700"
                >
                  Cancel
                </button>
              </div>
            )}

            <Button size="sm" onClick={handleApply}>
              Apply Filters
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
