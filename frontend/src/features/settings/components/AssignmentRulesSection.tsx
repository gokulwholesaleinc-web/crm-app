/**
 * Lead Auto-Assignment rules section for Settings page.
 * Lists rules, create/edit/delete, shows assignment stats.
 */

import { useState } from 'react';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import { Spinner } from '../../../components/ui/Spinner';
import {
  useAssignmentRules,
  useCreateAssignmentRule,
  useUpdateAssignmentRule,
  useDeleteAssignmentRule,
  useAssignmentStats,
} from '../../../hooks/useAssignment';
import type {
  AssignmentRule,
  AssignmentRuleCreate,
  AssignmentRuleUpdate,
} from '../../../types';
import {
  PlusIcon,
  TrashIcon,
  PencilSquareIcon,
  ChartBarIcon,
} from '@heroicons/react/24/outline';

function RuleForm({
  rule,
  onSubmit,
  onCancel,
  isLoading,
}: {
  rule?: AssignmentRule;
  onSubmit: (data: AssignmentRuleCreate | AssignmentRuleUpdate) => void;
  onCancel: () => void;
  isLoading: boolean;
}) {
  const [name, setName] = useState(rule?.name || '');
  const [assignmentType, setAssignmentType] = useState<'round_robin' | 'load_balance'>(
    rule?.assignment_type || 'round_robin'
  );
  const [userIdsStr, setUserIdsStr] = useState(
    rule?.user_ids?.join(', ') || ''
  );
  const [filterSource, setFilterSource] = useState(
    (rule?.filters as Record<string, unknown>)?.source_id?.toString() || ''
  );
  const [filterIndustry, setFilterIndustry] = useState(
    ((rule?.filters as Record<string, unknown>)?.industry as string) || ''
  );
  const [isActive, setIsActive] = useState(rule?.is_active ?? true);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const userIds = userIdsStr
      .split(',')
      .map((s) => parseInt(s.trim(), 10))
      .filter((n) => !isNaN(n));

    const filters: Record<string, unknown> = {};
    if (filterSource) filters.source_id = parseInt(filterSource, 10);
    if (filterIndustry) filters.industry = filterIndustry;

    onSubmit({
      name,
      assignment_type: assignmentType,
      user_ids: userIds,
      filters: Object.keys(filters).length > 0 ? filters : null,
      is_active: isActive,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="rule-name" className="block text-sm font-medium text-gray-700">
          Rule Name
        </label>
        <input
          id="rule-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
        />
      </div>
      <div>
        <label htmlFor="assignment-type" className="block text-sm font-medium text-gray-700">
          Assignment Type
        </label>
        <select
          id="assignment-type"
          value={assignmentType}
          onChange={(e) =>
            setAssignmentType(e.target.value as 'round_robin' | 'load_balance')
          }
          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
        >
          <option value="round_robin">Round Robin</option>
          <option value="load_balance">Load Balance</option>
        </select>
      </div>
      <div>
        <label htmlFor="user-ids" className="block text-sm font-medium text-gray-700">
          User IDs (comma-separated)
        </label>
        <input
          id="user-ids"
          type="text"
          value={userIdsStr}
          onChange={(e) => setUserIdsStr(e.target.value)}
          required
          placeholder="1, 2, 3"
          className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label htmlFor="filter-source" className="block text-sm font-medium text-gray-700">
            Filter: Source ID (optional)
          </label>
          <input
            id="filter-source"
            type="number"
            value={filterSource}
            onChange={(e) => setFilterSource(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
          />
        </div>
        <div>
          <label htmlFor="filter-industry" className="block text-sm font-medium text-gray-700">
            Filter: Industry (optional)
          </label>
          <input
            id="filter-industry"
            type="text"
            value={filterIndustry}
            onChange={(e) => setFilterIndustry(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
          />
        </div>
      </div>
      <div className="flex items-center gap-2">
        <input
          id="rule-active"
          type="checkbox"
          checked={isActive}
          onChange={(e) => setIsActive(e.target.checked)}
          className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
        />
        <label htmlFor="rule-active" className="text-sm text-gray-700">
          Active
        </label>
      </div>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={isLoading}>
          {isLoading ? <Spinner size="sm" /> : rule ? 'Update' : 'Create'}
        </Button>
      </div>
    </form>
  );
}

function RuleStats({ ruleId }: { ruleId: number }) {
  const { data: stats, isLoading } = useAssignmentStats(ruleId);

  if (isLoading) return <Spinner size="sm" />;
  if (!stats?.length) return <p className="text-sm text-gray-500">No stats available.</p>;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
      {stats.map((s) => (
        <div
          key={s.user_id}
          className="bg-gray-50 rounded-lg p-3 text-center"
        >
          <p className="text-xs text-gray-500">User #{s.user_id}</p>
          <p className="text-lg font-semibold text-gray-900">
            {s.active_leads_count}
          </p>
          <p className="text-xs text-gray-500">active leads</p>
        </div>
      ))}
    </div>
  );
}

export function AssignmentRulesSection() {
  const { data: rules, isLoading } = useAssignmentRules();
  const createMutation = useCreateAssignmentRule();
  const updateMutation = useUpdateAssignmentRule();
  const deleteMutation = useDeleteAssignmentRule();
  const [showForm, setShowForm] = useState(false);
  const [editingRule, setEditingRule] = useState<AssignmentRule | null>(null);
  const [showStatsId, setShowStatsId] = useState<number | null>(null);

  const handleCreate = (data: AssignmentRuleCreate | AssignmentRuleUpdate) => {
    createMutation.mutate(data as AssignmentRuleCreate, {
      onSuccess: () => setShowForm(false),
    });
  };

  const handleUpdate = (data: AssignmentRuleCreate | AssignmentRuleUpdate) => {
    if (!editingRule) return;
    updateMutation.mutate(
      { id: editingRule.id, data: data as AssignmentRuleUpdate },
      { onSuccess: () => setEditingRule(null) }
    );
  };

  return (
    <Card>
      <CardHeader
        title="Lead Auto-Assignment"
        description="Automatically assign new leads to team members"
        action={
          <Button
            size="sm"
            leftIcon={<PlusIcon className="h-4 w-4" />}
            onClick={() => {
              setShowForm(true);
              setEditingRule(null);
            }}
          >
            Add Rule
          </Button>
        }
      />
      <CardBody className="p-4 sm:p-6">
        {showForm && !editingRule && (
          <div className="mb-4 p-4 border border-gray-200 rounded-lg">
            <h4 className="text-sm font-medium text-gray-900 mb-3">New Rule</h4>
            <RuleForm
              onSubmit={handleCreate}
              onCancel={() => setShowForm(false)}
              isLoading={createMutation.isPending}
            />
          </div>
        )}

        {isLoading ? (
          <div className="flex justify-center py-8">
            <Spinner size="lg" />
          </div>
        ) : !rules?.length ? (
          <p className="text-sm text-gray-500 text-center py-8">
            No assignment rules configured. Click "Add Rule" to set up auto-assignment.
          </p>
        ) : (
          <div className="space-y-3">
            {rules.map((rule) => (
              <div
                key={rule.id}
                className="border border-gray-200 rounded-lg"
              >
                {editingRule?.id === rule.id ? (
                  <div className="p-4">
                    <h4 className="text-sm font-medium text-gray-900 mb-3">
                      Edit Rule
                    </h4>
                    <RuleForm
                      rule={rule}
                      onSubmit={handleUpdate}
                      onCancel={() => setEditingRule(null)}
                      isLoading={updateMutation.isPending}
                    />
                  </div>
                ) : (
                  <div className="p-4">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <span
                          className={`inline-block h-2.5 w-2.5 rounded-full ${
                            rule.is_active ? 'bg-green-500' : 'bg-gray-300'
                          }`}
                        />
                        <div>
                          <p className="text-sm font-medium text-gray-900">
                            {rule.name}
                          </p>
                          <p className="text-xs text-gray-500">
                            {rule.assignment_type === 'round_robin'
                              ? 'Round Robin'
                              : 'Load Balance'}{' '}
                            | {rule.user_ids.length} users
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            setShowStatsId(showStatsId === rule.id ? null : rule.id)
                          }
                          aria-label="View stats"
                        >
                          <ChartBarIcon className="h-4 w-4" aria-hidden="true" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditingRule(rule)}
                          aria-label="Edit rule"
                        >
                          <PencilSquareIcon className="h-4 w-4" aria-hidden="true" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            if (window.confirm('Delete this rule?')) {
                              deleteMutation.mutate(rule.id);
                            }
                          }}
                          aria-label="Delete rule"
                        >
                          <TrashIcon className="h-4 w-4 text-red-500" aria-hidden="true" />
                        </Button>
                      </div>
                    </div>
                    {rule.filters && Object.keys(rule.filters).length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {Object.entries(rule.filters).map(([key, value]) => (
                          <span
                            key={key}
                            className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700"
                          >
                            {key}: {String(value)}
                          </span>
                        ))}
                      </div>
                    )}
                    {showStatsId === rule.id && (
                      <div className="mt-3 pt-3 border-t border-gray-200">
                        <h5 className="text-sm font-medium text-gray-700 mb-2">
                          Assignment Stats
                        </h5>
                        <RuleStats ruleId={rule.id} />
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </CardBody>
    </Card>
  );
}
