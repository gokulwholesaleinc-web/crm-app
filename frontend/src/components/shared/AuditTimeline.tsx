/**
 * Reusable Audit Timeline component for any entity.
 * Displays change history as a vertical timeline.
 */

import { useState } from 'react';
import { Spinner } from '../ui';
import { useEntityAuditLog } from '../../hooks';
import { formatDate } from '../../utils/formatters';
import type { AuditLogEntry, AuditChangeDetail } from '../../types';

interface AuditTimelineProps {
  entityType: string;
  entityId: number;
}

const ACTION_LABELS: Record<string, string> = {
  create: 'Created',
  update: 'Updated',
  delete: 'Deleted',
};

const ACTION_COLORS: Record<string, { bg: string; icon: string }> = {
  create: { bg: 'bg-green-100', icon: 'text-green-600' },
  update: { bg: 'bg-blue-100', icon: 'text-blue-600' },
  delete: { bg: 'bg-red-100', icon: 'text-red-600' },
};

function formatFieldName(field: string): string {
  return field
    .replace(/_/g, ' ')
    .replace(/\bid\b/g, 'ID')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatChangeValue(value: unknown): string {
  if (value === null || value === undefined) return '(empty)';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function ChangeDetail({ change }: { change: AuditChangeDetail }) {
  return (
    <div className="flex items-start gap-2 text-xs">
      <span className="font-medium text-gray-700 min-w-0 flex-shrink-0">
        {formatFieldName(change.field)}:
      </span>
      <span className="text-gray-400 line-through truncate">
        {formatChangeValue(change.old_value)}
      </span>
      <span className="text-gray-400 flex-shrink-0">&rarr;</span>
      <span className="text-gray-900 truncate">
        {formatChangeValue(change.new_value)}
      </span>
    </div>
  );
}

function AuditEntry({ entry }: { entry: AuditLogEntry }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const colors = ACTION_COLORS[entry.action] ?? ACTION_COLORS.update;
  const hasChanges = entry.changes && entry.changes.length > 0;

  return (
    <li className="relative pb-8 last:pb-0">
      {/* Timeline connector line */}
      <span
        className="absolute left-4 top-8 -ml-px h-full w-0.5 bg-gray-200 last:hidden"
        aria-hidden="true"
      />

      <div className="relative flex items-start space-x-3">
        {/* Timeline dot */}
        <div className="relative">
          <div
            className={`h-8 w-8 rounded-full ${colors.bg} flex items-center justify-center ring-4 ring-white`}
          >
            {entry.action === 'create' ? (
              <svg
                className={`h-4 w-4 ${colors.icon}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
            ) : entry.action === 'delete' ? (
              <svg
                className={`h-4 w-4 ${colors.icon}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                />
              </svg>
            ) : (
              <svg
                className={`h-4 w-4 ${colors.icon}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"
                />
              </svg>
            )}
          </div>
        </div>

        {/* Entry content */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between">
            <p className="text-sm text-gray-900">
              <span className="font-medium">
                {entry.user_name || 'System'}
              </span>{' '}
              <span className="text-gray-500">
                {ACTION_LABELS[entry.action] ?? entry.action} this record
              </span>
            </p>
            <time className="text-xs text-gray-400 whitespace-nowrap ml-2 flex-shrink-0">
              {formatDate(entry.created_at)}
            </time>
          </div>

          {/* Changes details */}
          {hasChanges && (
            <div className="mt-1">
              <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className="text-xs text-primary-600 hover:text-primary-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded"
              >
                {isExpanded
                  ? 'Hide changes'
                  : `${entry.changes!.length} field${entry.changes!.length > 1 ? 's' : ''} changed`}
              </button>
              {isExpanded && (
                <div className="mt-2 space-y-1 bg-gray-50 rounded-md p-2">
                  {entry.changes!.map((change, idx) => (
                    <ChangeDetail key={idx} change={change} />
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </li>
  );
}

export function AuditTimeline({ entityType, entityId }: AuditTimelineProps) {
  const [page, setPage] = useState(1);
  const { data, isLoading, error } = useEntityAuditLog(
    entityType,
    entityId,
    page,
    20
  );

  const entries = data?.items ?? [];
  const totalPages = data?.pages ?? 1;

  if (error) {
    return (
      <div className="bg-white shadow rounded-lg p-4">
        <p className="text-sm text-red-500 text-center py-4">
          Failed to load change history. Please try again.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white shadow rounded-lg">
      <div className="px-4 py-5 sm:p-6">
        {isLoading ? (
          <div className="flex items-center justify-center py-4">
            <Spinner />
          </div>
        ) : entries.length === 0 ? (
          <p className="text-sm text-gray-500 text-center py-4">
            No change history recorded yet.
          </p>
        ) : (
          <>
            <ul className="space-y-0">
              {entries.map((entry) => (
                <AuditEntry key={entry.id} entry={entry} />
              ))}
            </ul>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="mt-6 flex items-center justify-between border-t border-gray-200 pt-4">
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="text-sm text-gray-600 hover:text-gray-900 disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded px-2 py-1"
                >
                  Previous
                </button>
                <span className="text-xs text-gray-500">
                  Page {page} of {totalPages}
                </span>
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="text-sm text-gray-600 hover:text-gray-900 disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded px-2 py-1"
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default AuditTimeline;
