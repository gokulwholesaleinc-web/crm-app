import { ReactNode } from 'react';
import clsx from 'clsx';
import {
  FolderOpenIcon,
  MagnifyingGlassIcon,
  PlusIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { Button } from './Button';

export type EmptyStateVariant = 'default' | 'search' | 'error' | 'create';

export interface EmptyStateProps {
  variant?: EmptyStateVariant;
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  secondaryAction?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

const defaultIcons: Record<EmptyStateVariant, ReactNode> = {
  default: <FolderOpenIcon className="h-12 w-12" />,
  search: <MagnifyingGlassIcon className="h-12 w-12" />,
  error: <ExclamationTriangleIcon className="h-12 w-12" />,
  create: <PlusIcon className="h-12 w-12" />,
};

export function EmptyState({
  variant = 'default',
  icon,
  title,
  description,
  action,
  secondaryAction,
  className,
}: EmptyStateProps) {
  const displayIcon = icon || defaultIcons[variant];

  return (
    <div
      className={clsx(
        'flex flex-col items-center justify-center py-12 px-4 text-center',
        className
      )}
    >
      <div
        className={clsx(
          'mx-auto',
          variant === 'error' ? 'text-red-400' : 'text-gray-400 dark:text-gray-500'
        )}
      >
        {displayIcon}
      </div>
      <h3 className="mt-4 text-lg font-medium text-gray-900 dark:text-gray-100">{title}</h3>
      {description && (
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400 max-w-md">{description}</p>
      )}
      {(action || secondaryAction) && (
        <div className="mt-6 flex items-center gap-3">
          {action && (
            <Button
              variant="primary"
              onClick={action.onClick}
              leftIcon={variant === 'create' ? <PlusIcon className="h-5 w-5" /> : undefined}
            >
              {action.label}
            </Button>
          )}
          {secondaryAction && (
            <Button variant="secondary" onClick={secondaryAction.onClick}>
              {secondaryAction.label}
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

// Common empty state presets
export function NoResultsEmptyState({
  searchTerm,
  onClear,
  className,
}: {
  searchTerm?: string;
  onClear?: () => void;
  className?: string;
}) {
  return (
    <EmptyState
      variant="search"
      title="No results found"
      description={
        searchTerm
          ? `We couldn't find any results for "${searchTerm}". Try adjusting your search or filters.`
          : 'Try adjusting your search or filters to find what you are looking for.'
      }
      action={onClear ? { label: 'Clear search', onClick: onClear } : undefined}
      className={className}
    />
  );
}

export function ErrorEmptyState({
  onRetry,
  className,
}: {
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <EmptyState
      variant="error"
      title="Something went wrong"
      description="We encountered an error while loading this content. Please try again."
      action={onRetry ? { label: 'Try again', onClick: onRetry } : undefined}
      className={className}
    />
  );
}
