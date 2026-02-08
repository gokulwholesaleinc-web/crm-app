import { Spinner } from '../ui';
import { useEntityEmails } from '../../hooks/useEmail';
import type { EmailQueueItem } from '../../api/email';

interface EmailHistoryProps {
  entityType: string;
  entityId: number;
}

function statusBadge(status: string) {
  const colors: Record<string, string> = {
    sent: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
    pending: 'bg-yellow-100 text-yellow-800',
  };
  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
        colors[status] || 'bg-gray-100 text-gray-800'
      }`}
    >
      {status}
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
        <p className="text-sm text-gray-500">No emails sent yet.</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {emails.map((email: EmailQueueItem) => (
        <div
          key={email.id}
          className="border border-gray-200 rounded-lg p-4 hover:bg-gray-50 transition-colors"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-gray-900 truncate">
                {email.subject}
              </p>
              <p className="text-xs text-gray-500 mt-0.5">
                To: {email.to_email}
              </p>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {statusBadge(email.status)}
            </div>
          </div>
          <div className="mt-2 flex items-center gap-4 text-xs text-gray-400">
            <span>{formatDate(email.created_at)}</span>
            {email.open_count > 0 && (
              <span>Opened {email.open_count}x</span>
            )}
            {email.click_count > 0 && (
              <span>Clicked {email.click_count}x</span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
