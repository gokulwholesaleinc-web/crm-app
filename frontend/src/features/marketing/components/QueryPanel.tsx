import { type UseQueryResult } from '@tanstack/react-query';
import { type ReactNode } from 'react';
import { Card } from '../../../components/ui';
import { EmptyState } from '../../../components/ui/EmptyState';

/** Loading skeleton / error+retry / data for a single panel query — gives every
 *  reporting panel one consistent error + retry path and keeps charts from popping
 *  in (CLS). Shared across the Paid Media / Website Analytics / Campaigns tabs. */
export function QueryPanel<T>({
  q,
  height = 240,
  render,
}: {
  q: UseQueryResult<T>;
  height?: number;
  render: (data: T) => ReactNode;
}) {
  if (q.isLoading) {
    return (
      <div
        className="animate-pulse rounded-lg border border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800"
        style={{ height }}
        aria-hidden="true"
      />
    );
  }
  if (q.isError) {
    return (
      <Card padding="lg">
        <EmptyState variant="error" title="Couldn't load this panel" description="Something went wrong." />
        <div className="mt-3 flex justify-center">
          <button
            type="button"
            onClick={() => q.refetch()}
            className="rounded-md bg-gray-100 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500 dark:bg-gray-700 dark:text-gray-200"
          >
            Retry
          </button>
        </div>
      </Card>
    );
  }
  if (!q.data) return null;
  return <>{render(q.data)}</>;
}
