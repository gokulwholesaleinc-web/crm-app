/**
 * Shared e-sign field-kind metadata + validation, extracted from
 * ``OnboardingTemplateEditor`` so the editor (editing an existing template) and
 * the "Create template" wizard (authoring a new one) reuse one source of truth
 * for the placeable kinds, their display chips, the prefill options, and the
 * per-field save-time validation.
 *
 * NOTE: ``ESIGN_PREFILL_OPTIONS`` is deliberately SEPARATE from the
 * questionnaire builder's ``PREFILL_OPTIONS`` (``OnboardingFormBuilder.tsx``) —
 * the two carry different user-facing labels ("Contact name" here vs "Client
 * name" there). Do NOT collapse them; that would silently change a label.
 */
import {
  PencilSquareIcon,
  CalendarDaysIcon,
  Bars3BottomLeftIcon,
  MapPinIcon,
} from '@heroicons/react/24/outline';
import type { OnboardingFieldDefinition, OnboardingFieldKind } from '../../types';

/** The four placeable e-sign field kinds, in toolbar order. */
export const FIELD_KINDS: OnboardingFieldKind[] = ['signature', 'date', 'text', 'address'];

export const KIND_META: Record<
  OnboardingFieldKind,
  { label: string; icon: typeof PencilSquareIcon; accent: string; box: string }
> = {
  signature: {
    label: 'Signature',
    icon: PencilSquareIcon,
    accent: 'bg-primary-600',
    box: 'border-primary-500 bg-primary-500/15',
  },
  date: {
    label: 'Date',
    icon: CalendarDaysIcon,
    accent: 'bg-emerald-600',
    box: 'border-emerald-500 bg-emerald-500/15',
  },
  text: {
    label: 'Text',
    icon: Bars3BottomLeftIcon,
    accent: 'bg-sky-600',
    box: 'border-sky-500 bg-sky-500/15',
  },
  address: {
    label: 'Address',
    icon: MapPinIcon,
    accent: 'bg-amber-600',
    box: 'border-amber-500 bg-amber-500/15',
  },
};

/** Prefill choices for an e-sign field. SEPARATE from the questionnaire set. */
export const ESIGN_PREFILL_OPTIONS: { value: string; label: string }[] = [
  { value: '', label: 'No prefill' },
  { value: 'contact.name', label: 'Contact name' },
  { value: 'company.name', label: 'Company name' },
];

/** A field id must be a lowercase slug (letters, numbers, underscores). */
export const SLUG_RE = /^[a-z0-9_]+$/;

/** A field is saveable only when it has a non-empty label and a unique slug id. */
export function fieldErrors(
  field: OnboardingFieldDefinition,
  all: OnboardingFieldDefinition[],
): string[] {
  const errors: string[] = [];
  if (!field.label.trim()) errors.push('Label is required.');
  if (!SLUG_RE.test(field.id))
    errors.push('Id must be lowercase letters, numbers, or underscores.');
  if (all.filter((f) => f.id === field.id).length > 1) errors.push('Id must be unique.');
  return errors;
}

/** Build a unique, slug-safe id for a new field of the given kind. */
export function nextFieldId(
  kind: OnboardingFieldKind,
  existing: OnboardingFieldDefinition[],
): string {
  const used = new Set(existing.map((f) => f.id));
  let n = 1;
  let candidate = `${kind}_${n}`;
  while (used.has(candidate)) {
    n += 1;
    candidate = `${kind}_${n}`;
  }
  return candidate;
}
