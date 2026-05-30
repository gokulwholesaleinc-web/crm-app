/**
 * Client Onboarding Types (Phase 1)
 *
 * Mirrors the backend ``onboarding`` module's wire contract (see
 * CLIENT_ONBOARDING_PLAN.md §4.4 and the build-order note §B/§C). Phase 1
 * surfaces the team template library + the field-placement editor only;
 * the public client-fill flow is Phase 2.
 */

/**
 * The four placeable field kinds. This type is onboarding-specific and
 * intentionally wider than the proposals picker's narrow
 * ``'signature' | 'date'`` — keeping them separate stops the proposals UI
 * from ever offering text/address.
 */
export type OnboardingFieldKind = 'signature' | 'date' | 'text' | 'address';

/**
 * Optional auto-fill source for a field's value. Resolution is Phase 2;
 * Phase 1 only stores the choice. ``contact.email`` is intentionally
 * disallowed (§4.4).
 */
export type OnboardingFieldPrefill = 'contact.name' | 'company.name' | null;

/**
 * A single field placed on the template PDF. Coordinates are PDF points
 * with origin = bottom-left of the page; ``page`` is 1-indexed (the
 * backend converts to 0-indexed for the stamper). ``id`` is unique within
 * the document and slug-safe (``^[a-z0-9_]+$``).
 */
export interface OnboardingFieldDefinition {
  id: string;
  kind: OnboardingFieldKind;
  label: string;
  description?: string | null;
  required: boolean;
  prefill: OnboardingFieldPrefill;
  page: number;
  x: number;
  y: number;
  w: number;
  h: number;
}

/** A team-library onboarding template row. */
export interface OnboardingTemplate {
  id: number;
  name: string;
  description?: string | null;
  /** null = universal template; a service slug scopes it to one service. */
  service_tag?: string | null;
  owner_id?: number | null;
  /** Storage ref; null until the first PDF upload. */
  pdf_path?: string | null;
  pdf_version: number;
  field_definitions: OnboardingFieldDefinition[];
  requires_esign: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface OnboardingTemplateCreate {
  name: string;
  description?: string | null;
  service_tag?: string | null;
  requires_esign?: boolean;
}

export interface OnboardingTemplateUpdate {
  name?: string | null;
  description?: string | null;
  service_tag?: string | null;
  requires_esign?: boolean | null;
  /** Reassigns the whole list; rejected (422) until a PDF is uploaded. */
  field_definitions?: OnboardingFieldDefinition[] | null;
}

export interface OnboardingTemplateFilters {
  service_tag?: string;
  include_inactive?: boolean;
}
