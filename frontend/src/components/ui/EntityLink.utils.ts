export type EntityType =
  | 'contact'
  | 'company'
  | 'lead'
  | 'opportunity'
  | 'quote'
  | 'proposal'
  | 'payment'
  | 'campaign'
  | 'activity';

export const entityRoutes: Record<EntityType, string> = {
  contact: '/contacts',
  company: '/companies',
  lead: '/leads',
  opportunity: '/opportunities',
  quote: '/quotes',
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
  opportunities: 'opportunity',
  quotes: 'quote',
  proposals: 'proposal',
  payments: 'payment',
  campaigns: 'campaign',
  activities: 'activity',
};

export function normalizeEntityType(value: string | null | undefined): EntityType | null {
  if (!value) return null;
  const lower = value.toLowerCase();
  if (lower in entityRoutes) return lower as EntityType;
  return pluralAliases[lower] ?? null;
}
