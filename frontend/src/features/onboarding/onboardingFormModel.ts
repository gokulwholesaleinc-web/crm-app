/**
 * Pure model + validation for ``questionnaire`` / ``upload_request`` field
 * lists, split out of ``OnboardingFormBuilder`` so the builder file only exports
 * components (react-refresh) and the "Create template" wizard can reuse the
 * exact same ``cleanField`` + ``validate`` at commit time. The backend handler
 * for the kind is authoritative; this mirrors it client-side.
 */
import type { OnboardingQuestionnaireField } from '../../types';

export const TEXT_KINDS = new Set<OnboardingQuestionnaireField['kind']>([
  'short_text',
  'paragraph',
  'email',
  'url',
  'date',
]);
export const CHOICE_KINDS = new Set<OnboardingQuestionnaireField['kind']>([
  'single_choice',
  'multi_choice',
]);

export const MAX_FILES_CEILING = 50;
export const MAX_MB_CEILING = 500;

/** Lowercase slug for derived ids/option values; never empty. */
function slugify(value: string, fallback: string): string {
  const slug = value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  return slug || fallback;
}

/** Strip empty/irrelevant keys so the saved definition matches its kind. */
export function cleanField(
  field: OnboardingQuestionnaireField,
): OnboardingQuestionnaireField {
  const label = field.label.trim();
  const out: OnboardingQuestionnaireField = {
    id: field.id,
    kind: field.kind,
    label,
    required: Boolean(field.required),
  };
  const help = field.help?.trim();
  if (help) out.help = help;
  const section = field.section_label?.trim();
  if (section) {
    out.section_label = section;
    out.section_id = slugify(section, 'section');
  }
  if (field.kind === 'file_upload') {
    out.maxFiles = field.maxFiles ?? 1;
    out.maxMB = field.maxMB ?? 10;
    return out;
  }
  if (CHOICE_KINDS.has(field.kind)) {
    out.options = (field.options ?? []).map((o) => ({
      value: o.value,
      label: o.label.trim(),
    }));
    if (field.allow_other) out.allow_other = true;
    if (field.kind === 'single_choice' && field.display === 'dropdown') {
      out.display = 'dropdown';
    }
    return out;
  }
  // Text kinds.
  if (field.prefill) out.prefill = field.prefill;
  if (field.sensitive) out.sensitive = true;
  return out;
}

/** Client-side guard mirroring the backend validators (server is authoritative). */
export function validate(fields: OnboardingQuestionnaireField[]): string | null {
  if (fields.length === 0) return 'Add at least one field.';
  for (const f of fields) {
    if (!f.label.trim()) return 'Every field needs a label.';
    if (f.kind === 'file_upload') {
      const mf = f.maxFiles ?? 0;
      const mm = f.maxMB ?? 0;
      if (!Number.isInteger(mf) || mf < 1 || mf > MAX_FILES_CEILING)
        return `"${f.label}": max files must be 1–${MAX_FILES_CEILING}.`;
      if (!Number.isInteger(mm) || mm < 1 || mm > MAX_MB_CEILING)
        return `"${f.label}": max MB must be 1–${MAX_MB_CEILING}.`;
    } else if (CHOICE_KINDS.has(f.kind)) {
      const opts = f.options ?? [];
      if (opts.length === 0) return `"${f.label}": add at least one option.`;
      if (opts.some((o) => !o.label.trim()))
        return `"${f.label}": every option needs a label.`;
    }
  }
  return null;
}
