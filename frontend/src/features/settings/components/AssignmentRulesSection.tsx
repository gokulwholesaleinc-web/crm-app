/**
 * Lead Auto-Assignment rules section for Settings page.
 * Lists rules, create/edit/delete, shows assignment stats.
 */

import { useState } from 'react';
import { Card, CardHeader, CardBody } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import { Spinner } from '../../../components/ui/Spinner';
import { ConfirmDialog } from '../../../components/ui/ConfirmDialog';
import {
  useAssignmentRules,
  useCreateAssignmentRule,
  useUpdateAssignmentRule,
  useDeleteAssignmentRule,
  useAssignmentStats,
} from '../../../hooks/useAssignment';
import { useUsers } from '../../../hooks/useAuth';
import { useLeadSources } from '../../../hooks/useLeads';
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
  XMarkIcon,
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
  const [selectedUserIds, setSelectedUserIds] = useState<number[]>(rule?.user_ids ?? []);
  const [filterSource, setFilterSource] = useState(
    (rule?.filters as Record<string, unknown>)?.source_id?.toString() || ''
  );
  const [filterIndustry, setFilterIndustry] = useState(
    ((rule?.filters as Record<string, unknown>)?.industry as string) || ''
  );
  const [isActive, setIsActive] = useState(rule?.is_active ?? true);

  const { data: allUsers } = useUsers();
  const { data: leadSources } = useLeadSources();

  const availableUsers = allUsers?.filter((u) => !selectedUserIds.includes(u.id)) ?? [];

  const toggleUser = (userId: number) => {
    setSelectedUserIds((prev) =>
      prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId]
    );
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const filters: Record<string, unknown> = {};
    if (filterSource) filters.source_id = parseInt(filterSource, 10);
    if (filterIndustry) filters.industry = filterIndustry;

    onSubmit({
      name,
      assignment_type: assignmentType,
      user_ids: selectedUserIds,
      filters: Object.keys(filters).length > 0 ? filters : null,
      is_active: isActive,
    });
  };

  const selectedUsers = allUsers?.filter((u) => selectedUserIds.includes(u.id)) ?? [];

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="rule-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          Rule Name
        </label>
        <input
          id="rule-name"
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
        />
      </div>
      <div>
        <label htmlFor="assignment-type" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          Assignment Type
        </label>
        <select
          id="assignment-type"
          value={assignmentType}
          onChange={(e) =>
            setAssignmentType(e.target.value as 'round_robin' | 'load_balance')
          }
          className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
        >
          <option value="round_robin">Round Robin</option>
          <option value="load_balance">Load Balance</option>
        </select>
      </div>
      <div>
        <span className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Assign to Users
        </span>
        {selectedUsers.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-2">
            {selectedUsers.map((u) => (
              <span
                key={u.id}
                className="inline-flex items-center gap-1 pl-2.5 pr-1 py-0.5 rounded-full text-xs font-medium bg-primary-100 dark:bg-primary-900/40 text-primary-800 dark:text-primary-300"
              >
                {u.full_name}
                <button
                  type="button"
                  onClick={() => toggleUser(u.id)}
                  className="flex items-center justify-center h-4 w-4 rounded-full hover:bg-primary-200 dark:hover:bg-primary-800 text-primary-600 dark:text-primary-400"
                  aria-label={`Remove ${u.full_name}`}
                >
                  <XMarkIcon className="h-3 w-3" aria-hidden="true" />
                </button>
              </span>
            ))}
          </div>
        )}
        <select
          id="user-picker"
          value=""
          onChange={(e) => {
            const id = Number(e.target.value);
            if (id) toggleUser(id);
          }}
          className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
        >
          <option value="">Add a user...</option>
          {availableUsers.map((u) => (
            <option key={u.id} value={u.id}>
              {u.full_name} ({u.email})
            </option>
          ))}
        </select>
        {selectedUserIds.length === 0 && (
          <p className="mt-1 text-xs text-red-600 dark:text-red-400">At least one user is required.</p>
        )}
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label htmlFor="filter-source" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Filter by Lead Source (optional)
          </label>
          <select
            id="filter-source"
            value={filterSource}
            onChange={(e) => setFilterSource(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
          >
            <option value="">Any source...</option>
            {leadSources?.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="filter-industry" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Filter: Industry (optional)
          </label>
          <input
            id="filter-industry"
            type="text"
            value={filterIndustry}
            onChange={(e) => setFilterIndustry(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
          />
        </div>
      </div>
      <div className="flex items-center gap-2">
        <input
          id="rule-active"
          type="checkbox"
          checked={isActive}
          onChange={(e) => setIsActive(e.target.checked)}
          className="rounded border-gray-300 dark:border-gray-600 text-primary-600 focus:ring-primary-500"
        />
        <label htmlFor="rule-active" className="text-sm text-gray-700 dark:text-gray-300">
          Active
        </label>
      </div>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={isLoading || selectedUserIds.length === 0}>
          {isLoading ? <Spinner size="sm" /> : rule ? 'Update' : 'Create'}
        </Button>
      </div>
    </form>
  );
}

function RuleStats({ ruleId }: { ruleId: number }) {
  const { data: stats, isLoading } = useAssignmentStats(ruleId);
  const { data: allUsers } = useUsers();

  if (isLoading) return <Spinner size="sm" />;
  if (!stats?.length) return <p className="text-sm text-gray-500">No stats available.</p>;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
      {stats.map((s) => {
        const user = allUsers?.find((u) => u.id === s.user_id);
        const displayName = user ? user.full_name : `User #${s.user_id}`;
        return (
          <div
            key={s.user_id}
            className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3 text-center"
          >
            <p className="text-xs text-gray-500 dark:text-gray-400">{displayName}</p>
            <p className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {s.active_leads_count}
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400">active leads</p>
          </div>
        );
      })}
    </div>
  );
}

export function AssignmentRulesSection() {
  const { data: rules, isLoading } = useAssignmentRules();
  const createMutation = useCreateAssignmentRule();
  const updateMutation = useUpdateAssignmentRule();
  const deleteMutation = useDeleteAssignmentRule();
  const { data: leadSources } = useLeadSources();
  const [showForm, setShowForm] = useState(false);
  const [editingRule, setEditingRule] = useState<AssignmentRule | null>(null);
  const [showStatsId, setShowStatsId] = useState<number | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; rule: AssignmentRule | null }>({
    isOpen: false,
    rule: null,
  });

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
          <div className="mb-4 p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
            <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">New Rule</h4>
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
                className="border border-gray-200 dark:border-gray-700 rounded-lg"
              >
                {editingRule?.id === rule.id ? (
                  <div className="p-4">
                    <h4 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-3">
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
                          <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
                            {rule.name}
                          </p>
                          <p className="text-xs text-gray-500 dark:text-gray-400">
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
                          onClick={() => setDeleteConfirm({ isOpen: true, rule })}
                          aria-label="Delete rule"
                        >
                          <TrashIcon className="h-4 w-4 text-red-500" aria-hidden="true" />
                        </Button>
                      </div>
                    </div>
                    {rule.filters && Object.keys(rule.filters).length > 0 && (
                      <div className="mt-2 flex flex-wrap gap-1">
                        {Object.entries(rule.filters).map(([key, value]) => {
                          let displayValue = String(value);
                          if (key === 'source_id') {
                            const src = leadSources?.find((s) => s.id === Number(value));
                            displayValue = src ? src.name : displayValue;
                          }
                          return (
                            <span
                              key={key}
                              className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300"
                            >
                              {key === 'source_id' ? 'source' : key}: {displayValue}
                            </span>
                          );
                        })}
                      </div>
                    )}
                    {showStatsId === rule.id && (
                      <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
                        <h5 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
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
      <ConfirmDialog
        isOpen={deleteConfirm.isOpen}
        onClose={() => setDeleteConfirm({ isOpen: false, rule: null })}
        onConfirm={() => {
          if (deleteConfirm.rule) {
            deleteMutation.mutate(deleteConfirm.rule.id, {
              onSuccess: () => setDeleteConfirm({ isOpen: false, rule: null }),
              onError: () => setDeleteConfirm({ isOpen: false, rule: null }),
            });
          }
        }}
        title="Delete Rule"
        message={`Are you sure you want to delete "${deleteConfirm.rule?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />
    </Card>
  );
}
