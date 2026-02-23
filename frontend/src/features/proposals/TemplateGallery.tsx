import { useState } from 'react';
import { DocumentTextIcon, TrashIcon, PencilSquareIcon } from '@heroicons/react/24/outline';
import { Button, Modal, ConfirmDialog } from '../../components/ui';
import { TemplateEditor } from './TemplateEditor';
import { CreateFromTemplateFlow } from './CreateFromTemplateFlow';
import {
  useProposalTemplates,
  useCreateProposalTemplate,
  useUpdateProposalTemplate,
  useDeleteProposalTemplate,
} from '../../hooks/useProposals';
import { showSuccess, showError } from '../../utils/toast';
import type { ProposalTemplate, ProposalTemplateCreate } from '../../types';

interface TemplateGalleryProps {
  onProposalCreated: (proposalId: number) => void;
}

export function TemplateGallery({ onProposalCreated }: TemplateGalleryProps) {
  const [categoryFilter, setCategoryFilter] = useState<string>('');
  const [showEditor, setShowEditor] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<ProposalTemplate | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<ProposalTemplate | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; template: ProposalTemplate | null }>({
    isOpen: false,
    template: null,
  });

  const { data: templates, isLoading } = useProposalTemplates(categoryFilter || undefined);
  const createMutation = useCreateProposalTemplate();
  const updateMutation = useUpdateProposalTemplate();
  const deleteMutation = useDeleteProposalTemplate();

  const handleCreate = async (data: ProposalTemplateCreate) => {
    try {
      await createMutation.mutateAsync(data);
      setShowEditor(false);
      showSuccess('Template created successfully');
    } catch {
      showError('Failed to create template');
    }
  };

  const handleUpdate = async (data: ProposalTemplateCreate) => {
    if (!editingTemplate) return;
    try {
      await updateMutation.mutateAsync({ id: editingTemplate.id, data });
      setEditingTemplate(null);
      showSuccess('Template updated successfully');
    } catch {
      showError('Failed to update template');
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm.template) return;
    try {
      await deleteMutation.mutateAsync(deleteConfirm.template.id);
      setDeleteConfirm({ isOpen: false, template: null });
      showSuccess('Template deleted successfully');
    } catch {
      showError('Failed to delete template');
    }
  };

  const categoryOptions = [
    { value: '', label: 'All Categories' },
    { value: 'service', label: 'Service' },
    { value: 'product', label: 'Product' },
    { value: 'consulting', label: 'Consulting' },
    { value: 'retainer', label: 'Retainer' },
  ];

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex-1 sm:max-w-xs">
          <label htmlFor="template-category-filter" className="sr-only">Filter by category</label>
          <select
            id="template-category-filter"
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 py-2 text-sm"
          >
            {categoryOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <Button onClick={() => setShowEditor(true)}>
          New Template
        </Button>
      </div>

      {/* Template Cards */}
      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="animate-pulse bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 h-48" />
          ))}
        </div>
      ) : !templates || templates.length === 0 ? (
        <div className="text-center py-12">
          <DocumentTextIcon className="mx-auto h-12 w-12 text-gray-400" />
          <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">No templates</h3>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Create a reusable template to speed up proposal creation.
          </p>
          <div className="mt-4">
            <Button onClick={() => setShowEditor(true)}>Create Template</Button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {templates.map((template) => (
            <div
              key={template.id}
              className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 flex flex-col hover:border-primary-300 dark:hover:border-primary-600 transition-colors"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                  {template.name}
                </h3>
                {template.is_default && (
                  <span className="flex-shrink-0 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-primary-100 dark:bg-primary-900/30 text-primary-800 dark:text-primary-300">
                    Default
                  </span>
                )}
              </div>
              {template.description && (
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-2 line-clamp-2">
                  {template.description}
                </p>
              )}
              {template.category && (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 mb-2 self-start">
                  {template.category}
                </span>
              )}
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3 line-clamp-3 flex-1 font-mono">
                {template.body.substring(0, 150)}{template.body.length > 150 ? '...' : ''}
              </p>
              {template.legal_terms && (
                <p className="text-xs text-amber-600 dark:text-amber-400 mb-3">
                  Includes legal terms
                </p>
              )}
              <div className="flex gap-2 pt-2 border-t border-gray-100 dark:border-gray-700">
                <Button
                  variant="primary"
                  size="sm"
                  className="flex-1"
                  onClick={() => setSelectedTemplate(template)}
                >
                  Use Template
                </Button>
                <button
                  type="button"
                  onClick={() => setEditingTemplate(template)}
                  className="p-1.5 text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 transition-colors"
                  aria-label={`Edit template ${template.name}`}
                >
                  <PencilSquareIcon className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setDeleteConfirm({ isOpen: true, template })}
                  className="p-1.5 text-gray-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                  aria-label={`Delete template ${template.name}`}
                >
                  <TrashIcon className="h-4 w-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Template Modal */}
      <Modal
        isOpen={showEditor}
        onClose={() => setShowEditor(false)}
        title="Create Template"
        size="lg"
        fullScreenOnMobile
      >
        <TemplateEditor
          onSubmit={handleCreate}
          onCancel={() => setShowEditor(false)}
          isLoading={createMutation.isPending}
        />
      </Modal>

      {/* Edit Template Modal */}
      <Modal
        isOpen={!!editingTemplate}
        onClose={() => setEditingTemplate(null)}
        title="Edit Template"
        size="lg"
        fullScreenOnMobile
      >
        {editingTemplate && (
          <TemplateEditor
            onSubmit={handleUpdate}
            onCancel={() => setEditingTemplate(null)}
            isLoading={updateMutation.isPending}
            initialData={{
              name: editingTemplate.name,
              body: editingTemplate.body,
              description: editingTemplate.description,
              legal_terms: editingTemplate.legal_terms,
              category: editingTemplate.category,
              is_default: editingTemplate.is_default,
            }}
            submitLabel="Update Template"
          />
        )}
      </Modal>

      {/* Create From Template Flow */}
      <Modal
        isOpen={!!selectedTemplate}
        onClose={() => setSelectedTemplate(null)}
        title={`Create Proposal from "${selectedTemplate?.name ?? ''}"`}
        size="lg"
        fullScreenOnMobile
      >
        {selectedTemplate && (
          <CreateFromTemplateFlow
            template={selectedTemplate}
            onCancel={() => setSelectedTemplate(null)}
            onCreated={(proposalId) => {
              setSelectedTemplate(null);
              onProposalCreated(proposalId);
            }}
          />
        )}
      </Modal>

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={deleteConfirm.isOpen}
        onClose={() => setDeleteConfirm({ isOpen: false, template: null })}
        onConfirm={handleDeleteConfirm}
        title="Delete Template"
        message={`Are you sure you want to delete "${deleteConfirm.template?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
