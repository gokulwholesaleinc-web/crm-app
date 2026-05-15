import type { MouseEvent, ReactNode } from 'react';
import { Link } from 'react-router-dom';
import clsx from 'clsx';
import {
  entityRoutes,
  LEGACY_CONTRACT_TYPE,
  LEGACY_OPPORTUNITY_TYPE,
  LEGACY_QUOTE_TYPE,
  type NormalizedEntityType,
} from './EntityLink.utils';

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

// Legacy entity kinds share an identical "muted italic span with a chip"
// rendering — only the default title and chip text differ. Keeping the
// map module-local avoids a public API for retired modules and lets each
// branch in EntityLink collapse to a one-liner.
type LegacyKind = 'opportunity' | 'quote' | 'contract';

const LEGACY_LABEL_BY_KIND: Record<LegacyKind, { defaultTitle: string; chip: string }> = {
  opportunity: {
    defaultTitle:
      'Opportunity records were retired — original entity is preserved for audit history.',
    chip: '(legacy opportunity)',
  },
  quote: {
    defaultTitle:
      'Quotes were replaced by Payment invoices — original entity is preserved for audit history.',
    chip: '(legacy quote)',
  },
  contract: {
    defaultTitle:
      'Contracts were folded into Proposals — original entity is preserved for audit history.',
    chip: '(legacy contract)',
  },
};

interface LegacyEntityLabelProps {
  kind: LegacyKind;
  title?: string;
  className?: string;
  children: ReactNode;
  onClick?: (e: MouseEvent) => void;
}

function LegacyEntityLabel({ kind, title, className, children, onClick }: LegacyEntityLabelProps) {
  const { defaultTitle, chip } = LEGACY_LABEL_BY_KIND[kind];
  return (
    <span
      className={clsx('text-gray-400 dark:text-gray-500 italic', className)}
      title={title ?? defaultTitle}
      onClick={onClick}
    >
      {children}{' '}
      <span className="text-[10px] uppercase tracking-wide">{chip}</span>
    </span>
  );
}

export interface EntityLinkProps {
  type: NormalizedEntityType;
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
  // Legacy rows have no destination route — render an explanatory muted
  // label instead of silently dropping the row or routing to a 404. We
  // intentionally ignore `variant` here: the legacy treatment is always
  // "muted, not a link" so callers don't accidentally style it as
  // clickable. Without stopPropagation, a parent row's onClick (e.g.
  // "open detail") would fire when the user taps the muted label —
  // surprising UX for a chip that looks non-interactive.
  const legacyClickHandler = stopPropagation ? (e: MouseEvent) => e.stopPropagation() : undefined;

  if (type === LEGACY_OPPORTUNITY_TYPE) {
    return <LegacyEntityLabel kind="opportunity" title={title} className={className} onClick={legacyClickHandler}>{children}</LegacyEntityLabel>;
  }
  if (type === LEGACY_QUOTE_TYPE) {
    return <LegacyEntityLabel kind="quote" title={title} className={className} onClick={legacyClickHandler}>{children}</LegacyEntityLabel>;
  }
  if (type === LEGACY_CONTRACT_TYPE) {
    return <LegacyEntityLabel kind="contract" title={title} className={className} onClick={legacyClickHandler}>{children}</LegacyEntityLabel>;
  }

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
