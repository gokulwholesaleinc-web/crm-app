import type { MouseEvent } from 'react';
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
  // Legacy opportunity rows have no destination route — Opportunities was
  // removed in PR1 #328. Render an explanatory muted label instead of
  // silently dropping the row or routing to a 404. We intentionally
  // ignore `variant` here: the legacy treatment is always "muted, not a
  // link" so callers don't accidentally style it as clickable.
  // Click handler shared by both legacy spans. Without stopPropagation,
  // a parent row's onClick (e.g. "open detail") would fire when the user
  // taps the muted label — surprising UX for a chip that looks
  // non-interactive.
  const legacyClickHandler = stopPropagation ? (e: MouseEvent) => e.stopPropagation() : undefined;

  if (type === LEGACY_OPPORTUNITY_TYPE) {
    return (
      <span
        className={clsx(
          'text-gray-400 dark:text-gray-500 italic',
          className,
        )}
        title={title ?? 'Opportunity records were retired — original entity is preserved for audit history.'}
        onClick={legacyClickHandler}
      >
        {children}{' '}
        <span className="text-[10px] uppercase tracking-wide">(legacy opportunity)</span>
      </span>
    );
  }

  // Quotes retired 2026-05-14 — mirror the legacy-opportunity treatment
  // so historical activity/audit rows render a muted non-clickable label
  // instead of routing to a 404.
  if (type === LEGACY_QUOTE_TYPE) {
    return (
      <span
        className={clsx(
          'text-gray-400 dark:text-gray-500 italic',
          className,
        )}
        title={title ?? 'Quotes were replaced by Payment invoices — original entity is preserved for audit history.'}
        onClick={legacyClickHandler}
      >
        {children}{' '}
        <span className="text-[10px] uppercase tracking-wide">(legacy quote)</span>
      </span>
    );
  }

  // Contracts retired 2026-05-14 — contract terms now fold into the
  // Proposal T&C inline. Mirror the legacy-opportunity/quote treatment.
  if (type === LEGACY_CONTRACT_TYPE) {
    return (
      <span
        className={clsx(
          'text-gray-400 dark:text-gray-500 italic',
          className,
        )}
        title={title ?? 'Contracts were folded into Proposals — original entity is preserved for audit history.'}
        onClick={legacyClickHandler}
      >
        {children}{' '}
        <span className="text-[10px] uppercase tracking-wide">(legacy contract)</span>
      </span>
    );
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
