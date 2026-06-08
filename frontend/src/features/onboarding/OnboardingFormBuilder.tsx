import { useId, useMemo, useState } from 'react';
import {
  PlusIcon,
  TrashIcon,
  ChevronUpIcon,
  ChevronDownIcon,
} from '@heroicons/react/24/outline';
import { Modal, ModalFooter, Button, Input, Select, Switch } from '../../components/ui';
import type {
  OnboardingQuestionnaireField,
  OnboardingQuestionKind,
  OnboardingFieldOption,
} from '../../types';
import {
  TEXT_KINDS,
  CHOICE_KINDS,
  MAX_FILES_CEILING,
  MAX_MB_CEILING,
  cleanField,
  validate,
} from './onboardingFormModel';

/**
 * Author the field list for a ``questionnaire`` or ``upload_request`` template.
 *
 * The backend validates the authoritative shape per kind
 * (``kinds/questionnaire.py`` / ``kinds/upload_request.py``); this builder
 * produces conforming definitions and saves them via the widened PATCH
 * (``field_definitions`` → ``list[dict]``). Sections are flat: each field
 * carries ``section_label`` (+ a derived ``section_id``) and the public renderer
 * groups contiguous same-section fields.
 */
interface OnboardingFormBuilderProps {
  isOpen: boolean;
  onClose: () => void;
  templateName: string;
  kind: 'questionnaire' | 'upload_request';
  currentFields: OnboardingQuestionnaireField[];
  /** Persist the field list (PATCH). Rejects propagate so the modal stays open. */
  onSave: (fields: OnboardingQuestionnaireField[]) => Promise<void>;
}

const QUESTION_KINDS: { value: OnboardingQuestionKind; label: string }[] = [
  { value: 'short_text', label: 'Short text' },
  { value: 'paragraph', label: 'Paragraph' },
  { value: 'single_choice', label: 'Single choice' },
  { value: 'multi_choice', label: 'Multiple choice' },
  { value: 'date', label: 'Date' },
  { value: 'email', label: 'Email' },
  { value: 'url', label: 'URL' },
];

const PREFILL_OPTIONS = [
  { value: '', label: 'No prefill' },
  { value: 'contact.name', label: 'Client name' },
  { value: 'company.name', label: 'Company name' },
];

/** Smallest ``${prefix}${n}`` not already used. */
function nextId(prefix: string, used: Set<string>): string {
  let n = 1;
  while (used.has(`${prefix}${n}`)) n += 1;
  return `${prefix}${n}`;
}

function blankQuestion(used: Set<string>): OnboardingQuestionnaireField {
  return { id: nextId('q', used), kind: 'short_text', label: '', required: false };
}

function blankUpload(used: Set<string>): OnboardingQuestionnaireField {
  return {
    id: nextId('f', used),
    kind: 'file_upload',
    label: '',
    required: false,
    maxFiles: 1,
    maxMB: 10,
  };
}

interface OnboardingFormBuilderBodyProps {
  kind: 'questionnaire' | 'upload_request';
  /** The current field list (controlled). */
  value: OnboardingQuestionnaireField[];
  /** Emits the (raw, uncleaned) field list on every edit. */
  onChange: (fields: OnboardingQuestionnaireField[]) => void;
}

/**
 * The controlled authoring surface — the field list + add button + inline
 * validation, with NO Modal. Hosted by the Modal builder (editing an existing
 * template) AND inline by the "Create template" wizard. Holds raw fields; the
 * host applies {@link cleanField} + {@link validate} when it commits.
 */
export function OnboardingFormBuilderBody({
  kind,
  value,
  onChange,
}: OnboardingFormBuilderBodyProps) {
  const isUpload = kind === 'upload_request';
  const validationError = useMemo(() => validate(value), [value]);

  const update = (id: string, patch: Partial<OnboardingQuestionnaireField>) =>
    onChange(value.map((f) => (f.id === id ? { ...f, ...patch } : f)));

  const addField = () => {
    // Derive the used-id set from the current value so a rapid double-click
    // can't mint two fields with the same id.
    const used = new Set(value.map((f) => f.id));
    onChange([...value, isUpload ? blankUpload(used) : blankQuestion(used)]);
  };

  const removeField = (id: string) => onChange(value.filter((f) => f.id !== id));

  const move = (index: number, delta: number) => {
    const target = index + delta;
    if (target < 0 || target >= value.length) return;
    const next = [...value];
    const a = next[index];
    const b = next[target];
    if (a === undefined || b === undefined) return;
    next[index] = b;
    next[target] = a;
    onChange(next);
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-500 dark:text-gray-400">
        {isUpload
          ? 'Define the files the client uploads. Each field becomes a labelled upload slot.'
          : 'Build the questions the client answers. Group related questions by giving them the same section.'}
      </p>

      {value.length === 0 ? (
        <p className="rounded-md border border-dashed border-gray-300 dark:border-gray-600 p-6 text-center text-sm text-gray-400 dark:text-gray-500">
          No fields yet. Add the first one below.
        </p>
      ) : (
        <ul className="space-y-3">
          {value.map((field, index) => (
            <FieldCard
              key={field.id}
              field={field}
              index={index}
              total={value.length}
              isUpload={isUpload}
              onChange={(patch) => update(field.id, patch)}
              onRemove={() => removeField(field.id)}
              onMoveUp={() => move(index, -1)}
              onMoveDown={() => move(index, 1)}
            />
          ))}
        </ul>
      )}

      <Button
        type="button"
        variant="secondary"
        leftIcon={<PlusIcon className="h-4 w-4" aria-hidden="true" />}
        onClick={addField}
      >
        {isUpload ? 'Add file field' : 'Add question'}
      </Button>

      {validationError && value.length > 0 && (
        <p role="status" className="text-sm text-amber-700 dark:text-amber-300">
          {validationError}
        </p>
      )}
    </div>
  );
}

export function OnboardingFormBuilder({
  isOpen,
  onClose,
  templateName,
  kind,
  currentFields,
  onSave,
}: OnboardingFormBuilderProps) {
  const [fields, setFields] = useState<OnboardingQuestionnaireField[]>(
    () => currentFields.map((f) => ({ ...f })),
  );
  const [saving, setSaving] = useState(false);

  const isUpload = kind === 'upload_request';
  const validationError = useMemo(() => validate(fields), [fields]);

  const handleSave = async () => {
    if (validationError) return;
    setSaving(true);
    try {
      await onSave(fields.map(cleanField));
      onClose();
    } catch {
      // The caller toasts the server error (e.g. a 422 detail); keep the modal
      // open so the author can fix and retry.
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={`${isUpload ? 'Edit files' : 'Edit questions'} — ${templateName}`}
      size="xl"
    >
      <OnboardingFormBuilderBody kind={kind} value={fields} onChange={setFields} />

      <ModalFooter>
        <Button type="button" variant="secondary" onClick={onClose} disabled={saving}>
          Cancel
        </Button>
        <Button
          type="button"
          variant="primary"
          onClick={handleSave}
          disabled={Boolean(validationError) || saving}
          isLoading={saving}
        >
          Save
        </Button>
      </ModalFooter>
    </Modal>
  );
}

interface FieldCardProps {
  field: OnboardingQuestionnaireField;
  index: number;
  total: number;
  isUpload: boolean;
  onChange: (patch: Partial<OnboardingQuestionnaireField>) => void;
  onRemove: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}

function FieldCard({
  field,
  index,
  total,
  isUpload,
  onChange,
  onRemove,
  onMoveUp,
  onMoveDown,
}: FieldCardProps) {
  const isChoice = CHOICE_KINDS.has(field.kind);
  const isText = TEXT_KINDS.has(field.kind);

  return (
    <li className="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/40 p-3 space-y-3">
      <div className="flex items-start gap-2">
        <div className="flex-1">
          <Input
            label={isUpload ? 'File label' : 'Question'}
            value={field.label}
            onChange={(e) => onChange({ label: e.target.value })}
            name={`field-label-${field.id}`}
            autoComplete="off"
            placeholder={isUpload ? 'e.g. Government ID...' : 'e.g. What is your EIN?...'}
            required
          />
        </div>
        <div className="flex flex-shrink-0 items-center gap-0.5 pt-6">
          <button
            type="button"
            onClick={onMoveUp}
            disabled={index === 0}
            aria-label="Move field up"
            className="rounded p-1 text-gray-400 hover:text-gray-700 disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:hover:text-gray-200"
          >
            <ChevronUpIcon className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={onMoveDown}
            disabled={index === total - 1}
            aria-label="Move field down"
            className="rounded p-1 text-gray-400 hover:text-gray-700 disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:hover:text-gray-200"
          >
            <ChevronDownIcon className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={onRemove}
            aria-label="Remove field"
            className="rounded p-1 text-gray-400 hover:text-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
          >
            <TrashIcon className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {!isUpload && (
          <Select
            label="Type"
            value={field.kind}
            onChange={(e) =>
              onChange({ kind: e.target.value as OnboardingQuestionKind })
            }
            options={QUESTION_KINDS}
            name={`field-kind-${field.id}`}
          />
        )}
        <Input
          label="Section (optional)"
          value={field.section_label ?? ''}
          onChange={(e) => onChange({ section_label: e.target.value })}
          name={`field-section-${field.id}`}
          autoComplete="off"
          placeholder="e.g. Business details..."
          helperText="Fields sharing a section are grouped together."
        />
      </div>

      <Input
        label="Help text (optional)"
        value={field.help ?? ''}
        onChange={(e) => onChange({ help: e.target.value })}
        name={`field-help-${field.id}`}
        autoComplete="off"
        placeholder="Guidance shown under the field..."
      />

      {isUpload && (
        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Max files"
            type="number"
            min={1}
            max={MAX_FILES_CEILING}
            value={String(field.maxFiles ?? 1)}
            onChange={(e) => onChange({ maxFiles: Number(e.target.value) })}
            name={`field-maxfiles-${field.id}`}
            inputMode="numeric"
          />
          <Input
            label="Max MB per file"
            type="number"
            min={1}
            max={MAX_MB_CEILING}
            value={String(field.maxMB ?? 10)}
            onChange={(e) => onChange({ maxMB: Number(e.target.value) })}
            name={`field-maxmb-${field.id}`}
            inputMode="numeric"
          />
        </div>
      )}

      {isChoice && (
        <OptionsEditor
          field={field}
          onChange={(options) => onChange({ options })}
        />
      )}

      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 pt-1">
        <Switch
          checked={Boolean(field.required)}
          onChange={(v) => onChange({ required: v })}
          label="Required"
          size="sm"
        />
        {isChoice && (
          <Switch
            checked={Boolean(field.allow_other)}
            onChange={(v) => onChange({ allow_other: v })}
            label="Allow “Other”"
            size="sm"
          />
        )}
        {field.kind === 'single_choice' && (
          <Switch
            checked={field.display === 'dropdown'}
            onChange={(v) => onChange({ display: v ? 'dropdown' : null })}
            label="Show as dropdown"
            size="sm"
          />
        )}
        {isText && (
          <Switch
            checked={Boolean(field.sensitive)}
            onChange={(v) => onChange({ sensitive: v })}
            label="Sensitive (encrypted)"
            size="sm"
          />
        )}
        {isText && field.kind === 'short_text' && (
          <div className="w-44">
            <Select
              label="Prefill"
              value={field.prefill ?? ''}
              onChange={(e) =>
                onChange({
                  prefill: (e.target.value || null) as OnboardingQuestionnaireField['prefill'],
                })
              }
              options={PREFILL_OPTIONS}
              name={`field-prefill-${field.id}`}
            />
          </div>
        )}
      </div>
    </li>
  );
}

interface OptionsEditorProps {
  field: OnboardingQuestionnaireField;
  onChange: (options: OnboardingFieldOption[]) => void;
}

function OptionsEditor({ field, onChange }: OptionsEditorProps) {
  const options = field.options ?? [];
  const baseId = useId();

  const addOption = () => {
    const used = new Set(options.map((o) => o.value));
    onChange([...options, { value: nextId('opt', used), label: '' }]);
  };
  const updateOption = (idx: number, label: string) =>
    onChange(options.map((o, i) => (i === idx ? { ...o, label } : o)));
  const removeOption = (idx: number) =>
    onChange(options.filter((_, i) => i !== idx));

  return (
    <fieldset className="rounded-md border border-gray-200 dark:border-gray-700 p-2">
      <legend className="px-1 text-xs font-medium text-gray-600 dark:text-gray-400">
        Options
      </legend>
      <ul className="space-y-1.5">
        {options.map((opt, idx) => (
          <li key={opt.value} className="flex items-center gap-2">
            <label htmlFor={`${baseId}-opt-${idx}`} className="sr-only">
              Option {idx + 1} label
            </label>
            <input
              id={`${baseId}-opt-${idx}`}
              type="text"
              value={opt.label}
              onChange={(e) => updateOption(idx, e.target.value)}
              placeholder="Option label..."
              autoComplete="off"
              className="block w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-1.5 text-sm text-gray-900 dark:text-gray-100 placeholder:text-gray-400 focus-visible:border-primary-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary-500"
            />
            <button
              type="button"
              onClick={() => removeOption(idx)}
              aria-label={`Remove option ${idx + 1}`}
              className="rounded p-1 text-gray-400 hover:text-red-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500"
            >
              <TrashIcon className="h-4 w-4" aria-hidden="true" />
            </button>
          </li>
        ))}
      </ul>
      <button
        type="button"
        onClick={addOption}
        className="mt-2 inline-flex items-center gap-1 rounded px-1.5 py-1 text-xs font-medium text-primary-600 hover:text-primary-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-primary-400"
      >
        <PlusIcon className="h-3.5 w-3.5" aria-hidden="true" />
        Add option
      </button>
    </fieldset>
  );
}

export default OnboardingFormBuilder;
