import { safeStorage } from '../../utils/safeStorage';
import type { BillingTermsValue } from '../../components/forms/BillingTermsField';

const VERSION = 'v1';
const KEY_PREFIX = 'crm_proposal_draft:';

export type ProposalDraftMode = 'create' | 'edit';

export interface ProposalFormDraftFields {
  title: string;
  content: string;
  contactId: number | null;
  companyId: number | null;
  executiveSummary: string;
  scopeOfWork: string;
  pricingSection: string;
  timelineField: string;
  terms: string;
  validUntil: string;
  termsAndConditions: string;
}

export interface ProposalFormDraftValue {
  formData: ProposalFormDraftFields;
  billing: BillingTermsValue;
  pendingSigningDocNames: string[];
}

export interface ProposalFormDraftRecord {
  version: 1;
  mode: ProposalDraftMode;
  proposalId: number | null;
  updatedAt: string;
  value: ProposalFormDraftValue;
}

export function getProposalDraftKey(
  userId: number | string | null | undefined,
  mode: ProposalDraftMode,
  proposalId?: number | null,
): string | null {
  if (userId === null || userId === undefined || userId === '') return null;
  const scopedId = mode === 'edit' ? proposalId ?? 'unknown' : 'new';
  return `${KEY_PREFIX}${userId}:${mode}:${scopedId}:${VERSION}`;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}

function cleanString(value: unknown): string {
  return typeof value === 'string' ? value : '';
}

function cleanNullableNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function sanitizeFormData(raw: unknown): ProposalFormDraftFields | null {
  if (!isPlainObject(raw)) return null;
  return {
    title: cleanString(raw.title),
    content: cleanString(raw.content),
    contactId: cleanNullableNumber(raw.contactId),
    companyId: cleanNullableNumber(raw.companyId),
    executiveSummary: cleanString(raw.executiveSummary),
    scopeOfWork: cleanString(raw.scopeOfWork),
    pricingSection: cleanString(raw.pricingSection),
    timelineField: cleanString(raw.timelineField),
    terms: cleanString(raw.terms),
    validUntil: cleanString(raw.validUntil),
    termsAndConditions: cleanString(raw.termsAndConditions),
  };
}

function sanitizeBilling(raw: unknown): BillingTermsValue | null {
  if (!isPlainObject(raw)) return null;
  const paymentType = raw.payment_type === 'subscription' ? 'subscription' : 'one_time';
  const interval =
    raw.recurring_interval === 'month' || raw.recurring_interval === 'year'
      ? raw.recurring_interval
      : null;
  const intervalCount =
    typeof raw.recurring_interval_count === 'number' &&
    Number.isFinite(raw.recurring_interval_count)
      ? raw.recurring_interval_count
      : null;
  return {
    payment_type: paymentType,
    recurring_interval: interval,
    recurring_interval_count: intervalCount,
    amount:
      typeof raw.amount === 'string' || typeof raw.amount === 'number'
        ? String(raw.amount)
        : '',
    currency: typeof raw.currency === 'string' && raw.currency ? raw.currency : 'USD',
  };
}

function sanitizeDraftValue(raw: unknown): ProposalFormDraftValue | null {
  if (!isPlainObject(raw)) return null;
  const formData = sanitizeFormData(raw.formData);
  const billing = sanitizeBilling(raw.billing);
  if (!formData || !billing) return null;
  return {
    formData,
    billing,
    pendingSigningDocNames: Array.isArray(raw.pendingSigningDocNames)
      ? raw.pendingSigningDocNames.filter(
          (name): name is string => typeof name === 'string' && name.length > 0,
        )
      : [],
  };
}

function sanitizeRecord(raw: unknown): ProposalFormDraftRecord | null {
  if (!isPlainObject(raw)) return null;
  if (raw.version !== 1) return null;
  if (raw.mode !== 'create' && raw.mode !== 'edit') return null;
  if (typeof raw.updatedAt !== 'string' || !raw.updatedAt) return null;
  const value = sanitizeDraftValue(raw.value);
  if (!value) return null;
  return {
    version: 1,
    mode: raw.mode,
    proposalId: cleanNullableNumber(raw.proposalId),
    updatedAt: raw.updatedAt,
    value,
  };
}

export function readProposalDraft(key: string | null): ProposalFormDraftRecord | null {
  if (!key) return null;
  return sanitizeRecord(safeStorage.getJson<unknown>(key));
}

export function writeProposalDraft(
  key: string | null,
  mode: ProposalDraftMode,
  proposalId: number | null | undefined,
  value: ProposalFormDraftValue,
): ProposalFormDraftRecord | null {
  if (!key) return null;
  const record: ProposalFormDraftRecord = {
    version: 1,
    mode,
    proposalId: mode === 'edit' ? proposalId ?? null : null,
    updatedAt: new Date().toISOString(),
    value,
  };
  return safeStorage.setJson(key, record) ? record : null;
}

export function clearProposalDraft(key: string | null): void {
  if (!key) return;
  safeStorage.remove(key);
}

export function purgeProposalDrafts(): void {
  try {
    const keys: string[] = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (key?.startsWith(KEY_PREFIX)) keys.push(key);
    }
    keys.forEach((key) => safeStorage.remove(key));
  } catch {
    // Storage may be unavailable during logout/unauthorized recovery.
  }
}

export function isProposalFormDraftEmpty(value: ProposalFormDraftValue): boolean {
  const textValues = [
    value.formData.title,
    value.formData.content,
    value.formData.executiveSummary,
    value.formData.scopeOfWork,
    value.formData.pricingSection,
    value.formData.timelineField,
    value.formData.terms,
    value.formData.validUntil,
    value.formData.termsAndConditions,
    value.billing.amount,
  ];
  return (
    textValues.every((entry) => String(entry ?? '').trim() === '') &&
    value.formData.contactId == null &&
    value.formData.companyId == null &&
    value.pendingSigningDocNames.length === 0 &&
    value.billing.payment_type === 'one_time' &&
    value.billing.recurring_interval == null &&
    value.billing.recurring_interval_count == null &&
    (value.billing.currency || 'USD') === 'USD'
  );
}

export function formatProposalDraftTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return 'recently';
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  }).format(date);
}
