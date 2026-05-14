export type EntityType =
  | 'contact'
  | 'company'
  | 'lead'
  | 'proposal'
  | 'payment'
  | 'campaign'
  | 'activity';

// Sentinel returned for historical activity/audit rows that still carry
// `entity_type='opportunities'`. The Opportunities feature was removed in
// PR1 (#328) but the backend preserves the column for historical data,
// so the value still appears in the wild. Callers detect this and
// render a muted, non-clickable label instead of either (a) silently
// rendering nothing or (b) crashing on a missing route.
export const LEGACY_OPPORTUNITY_TYPE = 'opportunity-legacy' as const;
export type LegacyOpportunityType = typeof LEGACY_OPPORTUNITY_TYPE;

// Sentinel returned for historical activity/audit rows that still carry
// `entity_type='quotes'`. The Quotes feature was retired 2026-05-14 in
// favor of one-off Payment invoices with optional PDF attachments. The
// backend preserves the column for historical data; this sentinel lets
// the UI render a muted "(legacy quote)" label without a route.
export const LEGACY_QUOTE_TYPE = 'quote-legacy' as const;
export type LegacyQuoteType = typeof LEGACY_QUOTE_TYPE;

// Sentinel returned for historical activity/audit rows that still carry
// `entity_type='contracts'`. The Contracts feature was retired
// 2026-05-14 — contract terms fold into the Proposal T&C inline. The
// backend preserves the column for historical data; this sentinel lets
// the UI render a muted "(legacy contract)" label without a route.
export const LEGACY_CONTRACT_TYPE = 'contract-legacy' as const;
export type LegacyContractType = typeof LEGACY_CONTRACT_TYPE;

export type NormalizedEntityType =
  | EntityType
  | LegacyOpportunityType
  | LegacyQuoteType
  | LegacyContractType;

export const entityRoutes: Record<EntityType, string> = {
  contact: '/contacts',
  company: '/companies',
  lead: '/leads',
  proposal: '/proposals',
  payment: '/payments',
  campaign: '/campaigns',
  activity: '/activities',
};

// Some callers (activities, audit logs) carry the entity type as the plural
// table name — accept both forms.
const pluralAliases: Record<string, EntityType> = {
  contacts: 'contact',
  companies: 'company',
  leads: 'lead',
  proposals: 'proposal',
  payments: 'payment',
  campaigns: 'campaign',
  activities: 'activity',
};

export function normalizeEntityType(
  value: string | null | undefined,
): NormalizedEntityType | null {
  if (!value) return null;
  const lower = value.toLowerCase();
  if (lower === 'opportunity' || lower === 'opportunities') {
    return LEGACY_OPPORTUNITY_TYPE;
  }
  if (lower === 'quote' || lower === 'quotes') {
    return LEGACY_QUOTE_TYPE;
  }
  if (lower === 'contract' || lower === 'contracts') {
    return LEGACY_CONTRACT_TYPE;
  }
  if (lower in entityRoutes) return lower as EntityType;
  return pluralAliases[lower] ?? null;
}
