import { useRef, useState, Suspense, lazy } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  PlusIcon,
  ArrowUpTrayIcon,
  PencilSquareIcon,
  ArchiveBoxXMarkIcon,
  ClipboardDocumentCheckIcon,
} from '@heroicons/react/24/outline';
import { Button, Modal, ModalFooter, Input, ConfirmDialog, Badge } from '../../components/ui';
import { SkeletonTable } from '../../components/ui/Skeleton';
import { useAuthQuery } from '../../hooks/useAuthQuery';
import { usePageTitle } from '../../hooks/usePageTitle';
import { formatDate } from '../../utils/formatters';
import { showSuccess, showError } from '../../utils/toast';
import { extractApiErrorDetail } from '../../utils/errors';
import {
  listOnboardingTemplates,
  createOnboardingTemplate,
  uploadOnboardingTemplatePdf,
  downloadOnboardingTemplatePdf,
  updateOnboardingTemplate,
  retireOnboardingTemplate,
  ONBOARDING_PDF_MAX_BYTES,
} from '../../api/onboarding';
import type {
  OnboardingTemplate,
  OnboardingTemplateCreate,
  OnboardingFieldDefinition,
} from '../../types';

// The editor pulls in pdf.js — code-split it so the library list stays light.
const OnboardingTemplateEditor = lazy(() => import('./OnboardingTemplateEditor'));

const ONBOARDING_KEY = ['onboarding-templates'] as const;

function OnboardingLibraryPage() {
  usePageTitle('Onboarding');
  const queryClient = useQueryClient();
  const [includeInactive, setIncludeInactive] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [retireTarget, setRetireTarget] = useState<OnboardingTemplate | null>(null);
  const [editorState, setEditorState] = useState<{
    template: OnboardingTemplate;
    pdfUrl: string;
  } | null>(null);
  const [loadingEditorId, setLoadingEditorId] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const uploadTargetIdRef = useRef<number | null>(null);

  const {
    data: templates = [],
    isLoading,
    error,
  } = useAuthQuery<OnboardingTemplate[]>({
    queryKey: [...ONBOARDING_KEY, { includeInactive }],
    queryFn: () => listOnboardingTemplates({ include_inactive: includeInactive }),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ONBOARDING_KEY });

  const createMutation = useMutation({
    mutationFn: (data: OnboardingTemplateCreate) => createOnboardingTemplate(data),
    onSuccess: () => invalidate(),
  });

  const uploadMutation = useMutation({
    mutationFn: ({ id, file }: { id: number; file: File }) =>
      uploadOnboardingTemplatePdf(id, file),
    onSuccess: () => invalidate(),
  });

  const saveFieldsMutation = useMutation({
    mutationFn: ({ id, fields }: { id: number; fields: OnboardingFieldDefinition[] }) =>
      updateOnboardingTemplate(id, { field_definitions: fields }),
    onSuccess: () => invalidate(),
  });

  const retireMutation = useMutation({
    mutationFn: (id: number) => retireOnboardingTemplate(id),
    onSuccess: () => invalidate(),
  });

  const universal = templates.filter((t) => !t.service_tag);
  const perService = templates.filter((t) => Boolean(t.service_tag));

  const handleCreate = async (data: OnboardingTemplateCreate) => {
    try {
      await createMutation.mutateAsync(data);
      setShowCreate(false);
      showSuccess('Template created. Upload a PDF to start placing fields.');
    } catch (err) {
      // Surfaced via toast; the modal stays open because the success-path
      // setShowCreate(false) above wasn't reached. No re-throw — the form
      // fires this via `void`, so a rejection would only become an unhandled
      // promise rejection.
      showError(extractApiErrorDetail(err) ?? 'Failed to create template');
    }
  };

  const triggerUpload = (templateId: number) => {
    uploadTargetIdRef.current = templateId;
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    const targetId = uploadTargetIdRef.current;
    // Reset the input so re-selecting the same file fires onChange again.
    e.target.value = '';
    uploadTargetIdRef.current = null;
    if (!file || targetId == null) return;
    if (file.type !== 'application/pdf') {
      showError('Please choose a PDF file.');
      return;
    }
    if (file.size > ONBOARDING_PDF_MAX_BYTES) {
      showError('PDF is too large (25 MB max).');
      return;
    }
    try {
      const updated = await uploadMutation.mutateAsync({ id: targetId, file });
      showSuccess(
        updated.field_definitions.length === 0 && updated.pdf_version > 1
          ? 'PDF replaced. Existing field placements were cleared.'
          : 'PDF uploaded.',
      );
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to upload PDF');
    }
  };

  const openEditor = async (template: OnboardingTemplate) => {
    if (!template.pdf_path) {
      showError('Upload a PDF before placing fields.');
      return;
    }
    setLoadingEditorId(template.id);
    try {
      const blob = await downloadOnboardingTemplatePdf(template.id);
      const pdfUrl = URL.createObjectURL(blob);
      setEditorState({ template, pdfUrl });
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to load template PDF');
    } finally {
      setLoadingEditorId(null);
    }
  };

  const closeEditor = () => {
    setEditorState((curr) => {
      if (curr) URL.revokeObjectURL(curr.pdfUrl);
      return null;
    });
  };

  const handleSaveFields = async (fields: OnboardingFieldDefinition[]) => {
    if (!editorState) return;
    try {
      await saveFieldsMutation.mutateAsync({ id: editorState.template.id, fields });
      showSuccess('Fields saved.');
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to save fields');
      throw err;
    }
  };

  const handleRetireConfirm = async () => {
    if (!retireTarget) return;
    try {
      await retireMutation.mutateAsync(retireTarget.id);
      showSuccess('Template retired.');
      setRetireTarget(null);
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to retire template');
    }
  };

  return (
    <div className="space-y-6">
      {/* Hidden file input shared by every row's Upload button. */}
      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf"
        className="sr-only"
        aria-hidden="true"
        tabIndex={-1}
        onChange={handleFileChange}
      />

      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">
            Onboarding
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Reusable client onboarding document templates with placed fields.
          </p>
        </div>
        <Button leftIcon={<PlusIcon className="h-5 w-5" />} onClick={() => setShowCreate(true)} className="w-full sm:w-auto">
          New Template
        </Button>
      </div>

      {/* Inactive toggle */}
      <label className="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
        <input
          type="checkbox"
          checked={includeInactive}
          onChange={(e) => setIncludeInactive(e.target.checked)}
          className="h-4 w-4 rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
        />
        Show retired templates
      </label>

      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
          <p className="text-sm font-medium text-red-800 dark:text-red-300">
            {error instanceof Error ? error.message : 'An error occurred'}
          </p>
        </div>
      )}

      {isLoading ? (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700">
          <SkeletonTable rows={4} cols={4} />
        </div>
      ) : templates.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-transparent dark:border-gray-700 text-center py-12 px-4">
          <ClipboardDocumentCheckIcon className="mx-auto h-12 w-12 text-gray-400" aria-hidden="true" />
          <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">No templates yet</h3>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Create a template, upload its PDF, then place the fields clients fill in.
          </p>
          <div className="mt-6 flex justify-center">
            <Button onClick={() => setShowCreate(true)}>New Template</Button>
          </div>
        </div>
      ) : (
        <div className="space-y-8">
          <TemplateSection
            heading="Universal templates"
            subtitle="Apply to any service."
            templates={universal}
            emptyText="No universal templates."
            loadingEditorId={loadingEditorId}
            onUpload={triggerUpload}
            onEdit={openEditor}
            onRetire={setRetireTarget}
          />
          <TemplateSection
            heading="Per-service templates"
            subtitle="Scoped to a specific service."
            templates={perService}
            emptyText="No per-service templates."
            loadingEditorId={loadingEditorId}
            onUpload={triggerUpload}
            onEdit={openEditor}
            onRetire={setRetireTarget}
          />
        </div>
      )}

      {/* Create modal */}
      <Modal isOpen={showCreate} onClose={() => setShowCreate(false)} title="New Onboarding Template" size="md">
        <CreateTemplateForm
          onSubmit={handleCreate}
          onCancel={() => setShowCreate(false)}
          isLoading={createMutation.isPending}
        />
      </Modal>

      {/* Field editor */}
      {editorState && (
        <Suspense fallback={null}>
          <OnboardingTemplateEditor
            isOpen
            onClose={closeEditor}
            templateName={editorState.template.name}
            pdfUrl={editorState.pdfUrl}
            currentFields={editorState.template.field_definitions}
            onSave={handleSaveFields}
          />
        </Suspense>
      )}

      {/* Retire confirmation */}
      <ConfirmDialog
        isOpen={retireTarget !== null}
        onClose={() => setRetireTarget(null)}
        onConfirm={handleRetireConfirm}
        title="Retire Template"
        message={`Retire "${retireTarget?.name ?? ''}"? It will be hidden from the active library but kept for historical packets.`}
        confirmLabel="Retire"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={retireMutation.isPending}
      />
    </div>
  );
}

interface TemplateSectionProps {
  heading: string;
  subtitle: string;
  templates: OnboardingTemplate[];
  emptyText: string;
  loadingEditorId: number | null;
  onUpload: (id: number) => void;
  onEdit: (template: OnboardingTemplate) => void;
  onRetire: (template: OnboardingTemplate) => void;
}

function TemplateSection({
  heading,
  subtitle,
  templates,
  emptyText,
  loadingEditorId,
  onUpload,
  onEdit,
  onRetire,
}: TemplateSectionProps) {
  return (
    <section>
      <div className="mb-3">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">{heading}</h2>
        <p className="text-xs text-gray-500 dark:text-gray-400">{subtitle}</p>
      </div>
      {templates.length === 0 ? (
        <p className="text-sm text-gray-400 dark:text-gray-500">{emptyText}</p>
      ) : (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700 divide-y divide-gray-200 dark:divide-gray-700">
          {templates.map((template) => (
            <TemplateRow
              key={template.id}
              template={template}
              isLoadingEditor={loadingEditorId === template.id}
              onUpload={onUpload}
              onEdit={onEdit}
              onRetire={onRetire}
            />
          ))}
        </div>
      )}
    </section>
  );
}

interface TemplateRowProps {
  template: OnboardingTemplate;
  isLoadingEditor: boolean;
  onUpload: (id: number) => void;
  onEdit: (template: OnboardingTemplate) => void;
  onRetire: (template: OnboardingTemplate) => void;
}

function TemplateRow({ template, isLoadingEditor, onUpload, onEdit, onRetire }: TemplateRowProps) {
  const hasPdf = Boolean(template.pdf_path);
  const fieldCount = template.field_definitions.length;
  return (
    <div className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">{template.name}</p>
          {template.service_tag && (
            <Badge variant="blue" size="sm">
              {template.service_tag}
            </Badge>
          )}
          {!template.is_active && (
            <Badge variant="gray" size="sm">
              Retired
            </Badge>
          )}
          {template.requires_esign && (
            <Badge variant="yellow" size="sm">
              E-sign
            </Badge>
          )}
        </div>
        {template.description && (
          <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400 line-clamp-2">
            {template.description}
          </p>
        )}
        <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500" style={{ fontVariantNumeric: 'tabular-nums' }}>
          {hasPdf ? `${fieldCount} field${fieldCount === 1 ? '' : 's'}` : 'No PDF yet'} · Updated {formatDate(template.updated_at)}
        </p>
      </div>
      <div className="flex flex-shrink-0 flex-wrap gap-2">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          leftIcon={<ArrowUpTrayIcon className="h-4 w-4" aria-hidden="true" />}
          onClick={() => onUpload(template.id)}
        >
          {hasPdf ? 'Replace PDF' : 'Upload PDF'}
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          leftIcon={<PencilSquareIcon className="h-4 w-4" aria-hidden="true" />}
          onClick={() => onEdit(template)}
          disabled={!hasPdf}
          isLoading={isLoadingEditor}
          title={hasPdf ? undefined : 'Upload a PDF first'}
        >
          Edit fields
        </Button>
        {template.is_active && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            leftIcon={<ArchiveBoxXMarkIcon className="h-4 w-4" aria-hidden="true" />}
            onClick={() => onRetire(template)}
          >
            Retire
          </Button>
        )}
      </div>
    </div>
  );
}

interface CreateTemplateFormProps {
  onSubmit: (data: OnboardingTemplateCreate) => Promise<void>;
  onCancel: () => void;
  isLoading: boolean;
}

function CreateTemplateForm({ onSubmit, onCancel, isLoading }: CreateTemplateFormProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [serviceTag, setServiceTag] = useState('');
  const [requiresEsign, setRequiresEsign] = useState(false);

  const canSubmit = name.trim().length > 0;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    void onSubmit({
      name: name.trim(),
      description: description.trim() || null,
      service_tag: serviceTag.trim() || null,
      requires_esign: requiresEsign,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <Input
        label="Name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        name="onboarding-template-name"
        autoComplete="off"
        placeholder="e.g. New client intake packet..."
        required
      />
      <Input
        label="Description (optional)"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        name="onboarding-template-description"
        autoComplete="off"
        placeholder="What this template is for..."
      />
      <Input
        label="Service tag (optional)"
        value={serviceTag}
        onChange={(e) => setServiceTag(e.target.value)}
        name="onboarding-template-service-tag"
        autoComplete="off"
        placeholder="Leave blank for a universal template..."
        helperText="Scopes the template to one service. Blank = universal."
      />
      <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
        <input
          type="checkbox"
          checked={requiresEsign}
          onChange={(e) => setRequiresEsign(e.target.checked)}
          className="h-4 w-4 rounded border-gray-300 text-primary-600 focus-visible:ring-primary-500"
        />
        Requires e-signature
      </label>
      <ModalFooter>
        <Button type="button" variant="secondary" onClick={onCancel} disabled={isLoading}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={!canSubmit} isLoading={isLoading}>
          Create
        </Button>
      </ModalFooter>
    </form>
  );
}

export default OnboardingLibraryPage;
