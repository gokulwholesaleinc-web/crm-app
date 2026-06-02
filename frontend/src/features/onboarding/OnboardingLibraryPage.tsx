import { useRef, useState, Suspense, lazy } from 'react';
import clsx from 'clsx';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  PlusIcon,
  ArrowUpTrayIcon,
  PencilSquareIcon,
  ArchiveBoxXMarkIcon,
  ArrowUturnLeftIcon,
  ClipboardDocumentCheckIcon,
  Cog6ToothIcon,
} from '@heroicons/react/24/outline';
import { Button, Modal, ModalFooter, Input, ConfirmDialog, Badge, Switch } from '../../components/ui';
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
  restoreOnboardingTemplate,
  ONBOARDING_PDF_MAX_BYTES,
} from '../../api/onboarding';
import type {
  OnboardingTemplate,
  OnboardingTemplateCreate,
  OnboardingTemplateUpdate,
  OnboardingFieldDefinition,
} from '../../types';

// The editor pulls in pdf.js — code-split it so the library list stays light.
const OnboardingTemplateEditor = lazy(() => import('./OnboardingTemplateEditor'));
// The send panel pulls in the contacts query + packet API — code-split too.
const OnboardingSendPanel = lazy(() => import('./OnboardingSendPanel'));

const ONBOARDING_KEY = ['onboarding-templates'] as const;

/** Fields the edit-details form can change (subset of the PATCH contract). */
type OnboardingTemplateMetaUpdate = Pick<
  OnboardingTemplateUpdate,
  'name' | 'description' | 'service_tag' | 'requires_esign'
>;

/**
 * An edit-conflict 409 on the field-save PATCH. The backend returns 409 for
 * EITHER a stale PDF (pdf_version bumped under the open editor) OR a retired
 * template (no edits allowed). We don't disambiguate here — the server detail
 * is surfaced verbatim. The flattened ``ApiError`` from ``api/client.ts``
 * carries ``status_code``.
 */
function isEditConflict(err: unknown): boolean {
  return (
    typeof err === 'object' &&
    err !== null &&
    (err as { status_code?: number }).status_code === 409
  );
}

function OnboardingLibraryPage() {
  usePageTitle('Onboarding');
  const queryClient = useQueryClient();
  const [view, setView] = useState<'templates' | 'send'>('templates');
  const [includeInactive, setIncludeInactive] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [metaTarget, setMetaTarget] = useState<OnboardingTemplate | null>(null);
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
    mutationFn: ({
      id,
      fields,
      pdfVersion,
    }: {
      id: number;
      fields: OnboardingFieldDefinition[];
      pdfVersion: number;
    }) =>
      updateOnboardingTemplate(id, {
        field_definitions: fields,
        // Optimistic-lock token: rejected 409 if the PDF was replaced
        // (version bumped) while this editor was open.
        pdf_version: pdfVersion,
      }),
    onSuccess: () => invalidate(),
  });

  const editMetaMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: OnboardingTemplateMetaUpdate }) =>
      updateOnboardingTemplate(id, data),
    onSuccess: () => invalidate(),
  });

  const retireMutation = useMutation({
    mutationFn: (id: number) => retireOnboardingTemplate(id),
    onSuccess: () => invalidate(),
  });

  const restoreMutation = useMutation({
    mutationFn: (id: number) => restoreOnboardingTemplate(id),
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
    if (!template.has_pdf) {
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
      await saveFieldsMutation.mutateAsync({
        id: editorState.template.id,
        fields,
        // Captured when the editor opened — see editorState.template.
        pdfVersion: editorState.template.pdf_version,
      });
      showSuccess('Fields saved.');
    } catch (err) {
      // 409 = the edit conflicted: either the PDF was replaced under the open
      // editor (stale coords) or the template was retired. We don't know which,
      // so surface the server's detail verbatim, then close + refetch so the
      // user reopens against the current server state.
      if (isEditConflict(err)) {
        showError(extractApiErrorDetail(err) ?? 'This template can no longer be edited.');
        closeEditor();
        invalidate();
        return;
      }
      showError(extractApiErrorDetail(err) ?? 'Failed to save fields');
      throw err;
    }
  };

  const handleEditMeta = async (data: OnboardingTemplateMetaUpdate) => {
    if (!metaTarget) return;
    try {
      await editMetaMutation.mutateAsync({ id: metaTarget.id, data });
      setMetaTarget(null);
      showSuccess('Template details updated.');
    } catch (err) {
      // Toast only; the modal stays open so the user can retry. No re-throw —
      // the form fires this via `void`, so a rejection would only surface as
      // an unhandled promise rejection.
      showError(extractApiErrorDetail(err) ?? 'Failed to update template');
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

  const handleRestore = async (template: OnboardingTemplate) => {
    try {
      await restoreMutation.mutateAsync(template.id);
      showSuccess('Template restored.');
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to restore template');
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
        {view === 'templates' && (
          <Button leftIcon={<PlusIcon className="h-5 w-5" />} onClick={() => setShowCreate(true)} className="w-full sm:w-auto">
            New Template
          </Button>
        )}
      </div>

      {/* View toggle: manage the template library vs send a packet to a client. */}
      <div
        className="inline-flex items-center gap-1 rounded-lg bg-gray-100 p-1 dark:bg-gray-800"
        role="tablist"
        aria-label="Onboarding view"
      >
        {([
          ['templates', 'Templates'],
          ['send', 'Send to client'],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={view === key}
            onClick={() => setView(key)}
            className={clsx(
              'rounded-md px-3.5 py-1.5 text-sm font-medium transition-colors motion-reduce:transition-none',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500',
              view === key
                ? 'bg-primary-600 text-white shadow-sm'
                : 'text-gray-600 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white',
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {view === 'send' && (
        <Suspense fallback={<SkeletonTable rows={3} cols={2} />}>
          <OnboardingSendPanel templates={templates} />
        </Suspense>
      )}

      {view === 'templates' && (
      <>
      {/* Inactive toggle */}
      <Switch
        checked={includeInactive}
        onChange={setIncludeInactive}
        label="Show retired templates"
        size="sm"
      />

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
            onEditMeta={setMetaTarget}
            onRetire={setRetireTarget}
            onRestore={handleRestore}
          />
          <TemplateSection
            heading="Per-service templates"
            subtitle="Scoped to a specific service."
            templates={perService}
            emptyText="No per-service templates."
            loadingEditorId={loadingEditorId}
            onUpload={triggerUpload}
            onEdit={openEditor}
            onEditMeta={setMetaTarget}
            onRetire={setRetireTarget}
            onRestore={handleRestore}
          />
        </div>
      )}
      </>
      )}

      {/* Create modal */}
      <Modal isOpen={showCreate} onClose={() => setShowCreate(false)} title="New Onboarding Template" size="md">
        <CreateTemplateForm
          onSubmit={handleCreate}
          onCancel={() => setShowCreate(false)}
          isLoading={createMutation.isPending}
        />
      </Modal>

      {/* Edit-details modal */}
      <Modal
        isOpen={metaTarget !== null}
        onClose={() => setMetaTarget(null)}
        title="Edit Template Details"
        size="md"
      >
        {metaTarget && (
          <EditTemplateMetaForm
            key={metaTarget.id}
            template={metaTarget}
            onSubmit={handleEditMeta}
            onCancel={() => setMetaTarget(null)}
            isLoading={editMetaMutation.isPending}
          />
        )}
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
  onEditMeta: (template: OnboardingTemplate) => void;
  onRetire: (template: OnboardingTemplate) => void;
  onRestore: (template: OnboardingTemplate) => void;
}

function TemplateSection({
  heading,
  subtitle,
  templates,
  emptyText,
  loadingEditorId,
  onUpload,
  onEdit,
  onEditMeta,
  onRetire,
  onRestore,
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
              onEditMeta={onEditMeta}
              onRetire={onRetire}
              onRestore={onRestore}
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
  onEditMeta: (template: OnboardingTemplate) => void;
  onRetire: (template: OnboardingTemplate) => void;
  onRestore: (template: OnboardingTemplate) => void;
}

function TemplateRow({
  template,
  isLoadingEditor,
  onUpload,
  onEdit,
  onEditMeta,
  onRetire,
  onRestore,
}: TemplateRowProps) {
  const hasPdf = template.has_pdf;
  const isActive = template.is_active;
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
        {isActive ? (
          <>
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
            <Button
              type="button"
              variant="ghost"
              size="sm"
              leftIcon={<Cog6ToothIcon className="h-4 w-4" aria-hidden="true" />}
              onClick={() => onEditMeta(template)}
            >
              Edit details
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              leftIcon={<ArchiveBoxXMarkIcon className="h-4 w-4" aria-hidden="true" />}
              onClick={() => onRetire(template)}
            >
              Retire
            </Button>
          </>
        ) : (
          // Retired: every edit (PATCH/upload) 409s, so only restore is offered.
          <Button
            type="button"
            variant="secondary"
            size="sm"
            leftIcon={<ArrowUturnLeftIcon className="h-4 w-4" aria-hidden="true" />}
            onClick={() => onRestore(template)}
          >
            Restore
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

  const canSubmit = name.trim().length > 0;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    // E-sign is NOT set at create — a new template has no fields yet, so the
    // backend rejects requires_esign: true (422). It's enabled later via the
    // edit-details PATCH, once a signature field has been placed.
    void onSubmit({
      name: name.trim(),
      description: description.trim() || null,
      service_tag: serviceTag.trim() || null,
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
      <p className="text-xs text-gray-500 dark:text-gray-400">
        Upload a PDF and place a signature field to enable e-signature from Edit
        details.
      </p>
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

interface EditTemplateMetaFormProps {
  template: OnboardingTemplate;
  onSubmit: (data: OnboardingTemplateMetaUpdate) => Promise<void>;
  onCancel: () => void;
  isLoading: boolean;
}

function EditTemplateMetaForm({ template, onSubmit, onCancel, isLoading }: EditTemplateMetaFormProps) {
  const [name, setName] = useState(template.name);
  const [description, setDescription] = useState(template.description ?? '');
  const [serviceTag, setServiceTag] = useState(template.service_tag ?? '');
  const [requiresEsign, setRequiresEsign] = useState(template.requires_esign);

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
      <Switch
        checked={requiresEsign}
        onChange={setRequiresEsign}
        label="Requires e-signature"
        description="Adds the ESIGN consent step; needs a placed signature field."
      />
      <ModalFooter>
        <Button type="button" variant="secondary" onClick={onCancel} disabled={isLoading}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={!canSubmit} isLoading={isLoading}>
          Save details
        </Button>
      </ModalFooter>
    </form>
  );
}

export default OnboardingLibraryPage;
