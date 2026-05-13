import { Spinner } from '../ui';
import { useEntityEmails } from '../../hooks/useEmail';
import type { EmailQueueItem } from '../../api/email';

interface EmailHistoryProps {
  entityType: string;
  entityId: number;
}

// The previous map only handled sent/failed/pending — retry and
// throttled silently rendered as a benign gray pill, indistinguishable
// from a "neutral" badge to operators trying to diagnose why a
// recipient never received an email. Every queue state now has a
// distinct label and color so stalled mail can't hide.
const STATUS_STYLES: Record<string, { label: string; classes: string }> = {
  sent: { label: 'Sent', classes: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300' },
  pending: { label: 'Pending', classes: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300' },
  retry: { label: 'Retrying', classes: 'bg-amber-100 text-amber-900 dark:bg-amber-900/30 dark:text-amber-300' },
  throttled: { label: 'Throttled', classes: 'bg-amber-100 text-amber-900 dark:bg-amber-900/30 dark:text-amber-300' },
  failed: { label: 'Failed', classes: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300' },
};

function statusBadge(status: string) {
  const style = STATUS_STYLES[status] ?? {
    label: status,
    classes: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200',
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${style.classes}`}
    >
      {style.label}
    </span>
  );
}

function formatDate(dateString: string | null): string {
  if (!dateString) return '-';
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(dateString));
}

export function EmailHistory({ entityType, entityId }: EmailHistoryProps) {
  const { data, isLoading } = useEntityEmails(entityType, entityId);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Spinner size="sm" />
      </div>
    );
  }

  const emails = data?.items ?? [];

  if (emails.length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-gray-500 dark:text-gray-400">No emails sent yet.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {emails.map((email: EmailQueueItem) => {
        const isStuck = email.status === 'retry' || email.status === 'throttled';
        const isFailed = email.status === 'failed';
        return (
          <div
            key={email.id}
            className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                  {email.subject}
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                  To: {email.to_email}
                </p>
              </div>
              <div className="flex items-center gap-2 flex-shrink-0">
                {statusBadge(email.status)}
              </div>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-gray-400 dark:text-gray-500">
              <span>{formatDate(email.created_at)}</span>
              {email.open_count > 0 && (
                <span>Opened {email.open_count}x</span>
              )}
              {email.click_count > 0 && (
                <span>Clicked {email.click_count}x</span>
              )}
              {isStuck && email.next_retry_at && (
                <span>Next retry {formatDate(email.next_retry_at)}</span>
              )}
              {email.retry_count > 0 && (
                <span>{email.retry_count} retr{email.retry_count === 1 ? 'y' : 'ies'}</span>
              )}
            </div>
            {(isStuck || isFailed) && email.error && (
              <p className="mt-2 text-xs text-red-700 dark:text-red-300 break-words">
                {email.error}
              </p>
            )}
          </div>
        );
      })}
    </div>
  );
}
