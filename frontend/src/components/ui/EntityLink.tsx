import { Link } from 'react-router-dom';
import clsx from 'clsx';

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

const entityRoutes: Record<EntityType, string> = {
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

export type EntityLinkVariant = 'primary' | 'muted' | 'inherit';

const variantStyles: Record<EntityLinkVariant, string> = {
  // Brand-blue link, used when the entity name is the dominant text in a cell.
  primary:
    'text-primary-600 hover:text-primary-900 hover:underline dark:text-primary-400 dark:hover:text-primary-300',
  // Used inside secondary/subtitle rows where the surrounding text is gray.
  muted:
    'text-gray-700 hover:text-primary-700 hover:underline dark:text-gray-300 dark:hover:text-primary-300',
  // No color of its own — picks up the parent's color, only adds underline on hover.
  // Use when the link sits inside a colored container (badge, kanban card title row).
  inherit: 'hover:underline',
};

export interface EntityLinkProps {
  type: EntityType;
  id: number | string | null | undefined;
  children: React.ReactNode;
  variant?: EntityLinkVariant;
  className?: string;
  title?: string;
  /**
   * When true, clicks won't bubble to ancestor handlers (row click, drag handle, card click).
   * Defaults to true since this is the common case in tables and kanban cards.
   */
  stopPropagation?: boolean;
}

export function EntityLink({
  type,
  id,
  children,
  variant = 'primary',
  className,
  title,
  stopPropagation = true,
}: EntityLinkProps) {
  if (id === null || id === undefined || id === '') {
    return <span className={className}>{children}</span>;
  }

  return (
    <Link
      to={`${entityRoutes[type]}/${id}`}
      className={clsx('focus-visible:outline-none focus-visible:underline', variantStyles[variant], className)}
      title={title}
      onClick={stopPropagation ? (e) => e.stopPropagation() : undefined}
    >
      {children}
    </Link>
  );
}
