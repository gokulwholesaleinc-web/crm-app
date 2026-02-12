/**
 * Workflows list page for managing automation rules
 */

import { useState } from 'react';
import clsx from 'clsx';
import {
  PlusIcon,
  FunnelIcon,
  BoltIcon,
  PlayIcon,
  PauseIcon,
} from '@heroicons/react/24/outline';
import { Button, Select, Spinner, Modal, ConfirmDialog } from '../../components/ui';
import { WorkflowForm } from './components/WorkflowForm';
import {
  useWorkflows,
  useCreateWorkflow,
  useUpdateWorkflow,
  useDeleteWorkflow,
} from '../../hooks/useWorkflows';
import { formatDate } from '../../utils/formatters';
import { formatStatusLabel } from '../../utils';
import type { WorkflowRule, WorkflowRuleCreate, WorkflowRuleUpdate } from '../../types';

const entityOptions = [
  { value: '', label: 'All Entities' },
  { value: 'lead', label: 'Lead' },
  { value: 'contact', label: 'Contact' },
  { value: 'company', label: 'Company' },
  { value: 'opportunity', label: 'Opportunity' },
  { value: 'activity', label: 'Activity' },
];

const statusFilterOptions = [
  { value: '', label: 'All Status' },
  { value: 'true', label: 'Active' },
  { value: 'false', label: 'Inactive' },
];

function WorkflowCard({
  workflow,
  onEdit,
  onDelete,
  onToggle,
}: {
  workflow: WorkflowRule;
  onEdit: () => void;
  onDelete: () => void;
  onToggle: () => void;
}) {
  return (
    <div className="bg-white rounded-lg shadow-sm border p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span
              className={clsx(
                'text-xs font-medium px-2 py-0.5 rounded-full',
                workflow.is_active
                  ? 'bg-green-100 text-green-700'
                  : 'bg-gray-100 text-gray-600'
              )}
            >
              {workflow.is_active ? 'Active' : 'Inactive'}
            </span>
            <span className="text-xs text-gray-500">
              {formatStatusLabel(workflow.trigger_entity)}
            </span>
          </div>
          <h3 className="text-lg font-semibold text-gray-900 truncate">{workflow.name}</h3>
          {workflow.description && (
            <p className="text-sm text-gray-600 mt-1 line-clamp-2">{workflow.description}</p>
          )}
        </div>
        <div className="flex items-center gap-1 ml-4">
          <button
            onClick={onToggle}
            className={clsx(
              'p-1.5 rounded-lg hover:bg-gray-100',
              workflow.is_active
                ? 'text-yellow-500 hover:text-yellow-600'
                : 'text-green-500 hover:text-green-600'
            )}
            aria-label={workflow.is_active ? 'Deactivate workflow' : 'Activate workflow'}
          >
            {workflow.is_active ? (
              <PauseIcon className="h-5 w-5" />
            ) : (
              <PlayIcon className="h-5 w-5" />
            )}
          </button>
          <button
            onClick={onEdit}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600"
            aria-label="Edit workflow"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
              />
            </svg>
          </button>
          <button
            onClick={onDelete}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-red-500"
            aria-label="Delete workflow"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
              />
            </svg>
          </button>
        </div>
      </div>

      {/* Trigger info */}
      <div className="flex items-center gap-4 mt-4 text-xs text-gray-500">
        <span>
          Trigger: <span className="font-medium text-gray-700">{formatStatusLabel(workflow.trigger_event)}</span>
        </span>
        <span>Created: {formatDate(workflow.created_at)}</span>
      </div>

      {/* Conditions / Actions summary */}
      <div className="flex items-center gap-4 mt-2 text-xs text-gray-500">
        {workflow.conditions && (
          <span className="inline-flex items-center gap-1">
            <FunnelIcon className="h-3.5 w-3.5" />
            Has conditions
          </span>
        )}
        {workflow.actions && workflow.actions.length > 0 && (
          <span className="inline-flex items-center gap-1">
            <BoltIcon className="h-3.5 w-3.5" />
            {workflow.actions.length} action{workflow.actions.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>
    </div>
  );
}

export function WorkflowsPage() {
  const [showFilters, setShowFilters] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingWorkflow, setEditingWorkflow] = useState<WorkflowRule | null>(null);
  const [entityFilter, setEntityFilter] = useState('');
  const [activeFilter, setActiveFilter] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; workflow: WorkflowRule | null }>({
    isOpen: false,
    workflow: null,
  });

  const { data: workflows, isLoading } = useWorkflows({
    trigger_entity: entityFilter || undefined,
    is_active: activeFilter ? activeFilter === 'true' : undefined,
  });

  const createWorkflow = useCreateWorkflow();
  const updateWorkflow = useUpdateWorkflow();
  const deleteWorkflow = useDeleteWorkflow();

  const handleDeleteClick = (workflow: WorkflowRule) => {
    setDeleteConfirm({ isOpen: true, workflow });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm.workflow) return;
    try {
      await deleteWorkflow.mutateAsync(deleteConfirm.workflow.id);
      setDeleteConfirm({ isOpen: false, workflow: null });
    } catch (error) {
      console.error('Failed to delete workflow:', error);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteConfirm({ isOpen: false, workflow: null });
  };

  const handleEdit = (workflow: WorkflowRule) => {
    setEditingWorkflow(workflow);
    setShowForm(true);
  };

  const handleToggle = async (workflow: WorkflowRule) => {
    try {
      await updateWorkflow.mutateAsync({
        id: workflow.id,
        data: { is_active: !workflow.is_active },
      });
    } catch (error) {
      console.error('Failed to toggle workflow:', error);
    }
  };

  const handleFormSubmit = async (data: WorkflowRuleCreate | WorkflowRuleUpdate) => {
    try {
      if (editingWorkflow) {
        await updateWorkflow.mutateAsync({ id: editingWorkflow.id, data: data as WorkflowRuleUpdate });
      } else {
        await createWorkflow.mutateAsync(data as WorkflowRuleCreate);
      }
      setShowForm(false);
      setEditingWorkflow(null);
    } catch (error) {
      console.error('Failed to save workflow:', error);
    }
  };

  const handleFormCancel = () => {
    setShowForm(false);
    setEditingWorkflow(null);
  };

  const workflowList = Array.isArray(workflows) ? workflows : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900">Workflows</h1>
          <p className="text-sm text-gray-500 mt-1">
            Automate actions based on triggers and conditions
          </p>
        </div>
        <Button
          leftIcon={<PlusIcon className="h-5 w-5" />}
          onClick={() => setShowForm(true)}
          className="w-full sm:w-auto"
        >
          New Workflow
        </Button>
      </div>

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 sm:gap-4">
        <Button
          variant="ghost"
          size="sm"
          leftIcon={<FunnelIcon className="h-4 w-4" />}
          onClick={() => setShowFilters(!showFilters)}
          className="w-full sm:w-auto justify-center sm:justify-start"
        >
          Filters
        </Button>

        <div className="text-sm text-gray-500 text-center sm:text-right">
          {workflowList.length} workflow{workflowList.length !== 1 ? 's' : ''}
        </div>
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <div className="bg-gray-50 rounded-lg p-3 sm:p-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4">
            <Select
              label="Entity"
              options={entityOptions}
              value={entityFilter}
              onChange={(e) => setEntityFilter(e.target.value)}
            />
            <Select
              label="Status"
              options={statusFilterOptions}
              value={activeFilter}
              onChange={(e) => setActiveFilter(e.target.value)}
            />
          </div>
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : workflowList.length === 0 ? (
        <div className="text-center py-12">
          <BoltIcon className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900">No workflows</h3>
          <p className="mt-1 text-sm text-gray-500">
            Get started by creating a new workflow rule.
          </p>
          <div className="mt-6">
            <Button onClick={() => setShowForm(true)}>
              <PlusIcon className="h-5 w-5 mr-2" />
              New Workflow
            </Button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {workflowList.map((workflow) => (
            <WorkflowCard
              key={workflow.id}
              workflow={workflow}
              onEdit={() => handleEdit(workflow)}
              onDelete={() => handleDeleteClick(workflow)}
              onToggle={() => handleToggle(workflow)}
            />
          ))}
        </div>
      )}

      {/* Form Modal */}
      <Modal
        isOpen={showForm}
        onClose={handleFormCancel}
        title={editingWorkflow ? 'Edit Workflow' : 'New Workflow'}
        size="lg"
      >
        <WorkflowForm
          workflow={editingWorkflow || undefined}
          onSubmit={handleFormSubmit}
          onCancel={handleFormCancel}
          isLoading={createWorkflow.isPending || updateWorkflow.isPending}
        />
      </Modal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={deleteConfirm.isOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title="Delete Workflow"
        message={`Are you sure you want to delete "${deleteConfirm.workflow?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteWorkflow.isPending}
      />
    </div>
  );
}

export default WorkflowsPage;
