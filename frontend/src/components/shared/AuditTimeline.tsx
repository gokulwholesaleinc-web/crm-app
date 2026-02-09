import { useState } from 'react';
import { useEntityAuditLog } from '../../hooks/useAudit';
import { Spinner } from '../ui';
import { formatDate } from '../../utils/formatters';
import type { AuditChangeDetail } from '../../types';

interface AuditTimelineProps {
  entityType: string;
  entityId: number;
}

function ChangeDetail({ change }: { change: AuditChangeDetail }) {
  return (
    <div className="text-xs mt-1 bg-gray-50 rounded px-2 py-1">
      <span className="font-medium text-gray-700">{change.field}</span>
      {change.old_value && (
        <span className="text-red-600 line-through ml-2">
          {change.old_value}
        </span>
      )}
      {change.new_value && (
        <span className="text-green-600 ml-2">{change.new_value}</span>
      )}
    </div>
  );
}

export function AuditTimeline({ entityType, entityId }: AuditTimelineProps) {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useEntityAuditLog(entityType, entityId, page);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Spinner />
      </div>
    );
  }

  const items = data?.items || [];
  const totalPages = data?.pages || 1;

  if (items.length === 0) {
    return (
      <div className="bg-white shadow rounded-lg p-6">
        <p className="text-sm text-gray-500 text-center">
          No change history recorded yet.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white shadow rounded-lg p-4 sm:p-6">
      <div className="flow-root">
        <ul className="-mb-8">
          {items.map((item, idx) => (
            <li key={item.id}>
              <div className="relative pb-8">
                {idx < items.length - 1 && (
                  <span
                    className="absolute top-4 left-4 -ml-px h-full w-0.5 bg-gray-200"
                    aria-hidden="true"
                  />
                )}
                <div className="relative flex space-x-3">
                  <div>
                    <span className="h-8 w-8 rounded-full bg-primary-100 flex items-center justify-center ring-8 ring-white">
                      <svg
                        className="h-4 w-4 text-primary-600"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                        />
                      </svg>
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm text-gray-900">
                      <span className="font-medium">
                        {item.user_name || 'System'}
                      </span>{' '}
                      <span className="text-gray-600">{item.action}</span>
                    </div>
                    <p className="text-xs text-gray-500 mt-0.5">
                      {formatDate(item.created_at)}
                    </p>
                    {item.changes && item.changes.length > 0 && (
                      <div className="mt-2 space-y-1">
                        {item.changes.map((change, i) => (
                          <ChangeDetail key={i} change={change} />
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {totalPages > 1 && (
        <div className="mt-6 flex items-center justify-between border-t border-gray-200 pt-4">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="text-sm text-primary-600 hover:text-primary-500 disabled:text-gray-400 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <span className="text-sm text-gray-500">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="text-sm text-primary-600 hover:text-primary-500 disabled:text-gray-400 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
