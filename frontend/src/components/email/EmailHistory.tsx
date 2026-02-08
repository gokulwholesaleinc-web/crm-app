import { Spinner } from '../ui';
import { useEntityEmails } from '../../hooks/useEmail';
import { formatDate } from '../../utils/formatters';

interface EmailHistoryProps {
  entityType: string;
  entityId: number;
}

const STATUS_CLASSES: Record<string, string> = {
  sent: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
  pending: 'bg-yellow-100 text-yellow-800',
};

export function EmailHistory({ entityType, entityId }: EmailHistoryProps) {
  const { data, isLoading } = useEntityEmails(entityType, entityId);
  const emails = data?.items ?? [];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Spinner />
      </div>
    );
  }

  if (emails.length === 0) {
    return (
      <div className="bg-white shadow rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          <p className="text-sm text-gray-500 text-center py-4">
            No emails sent yet.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white shadow rounded-lg">
      <div className="px-4 py-5 sm:p-6">
        <ul className="space-y-4">
          {emails.map((email) => (
            <li
              key={email.id}
              className="flex items-start justify-between pb-4 border-b border-gray-100 last:border-0"
            >
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {email.subject}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  To: {email.to_email}
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  {email.sent_at ? formatDate(email.sent_at) : formatDate(email.created_at)}
                </p>
              </div>
              <div className="ml-4 flex items-center gap-3 flex-shrink-0">
                {email.open_count > 0 && (
                  <span className="text-xs text-gray-500">
                    {email.open_count} open{email.open_count !== 1 ? 's' : ''}
                  </span>
                )}
                {email.click_count > 0 && (
                  <span className="text-xs text-gray-500">
                    {email.click_count} click{email.click_count !== 1 ? 's' : ''}
                  </span>
                )}
                <span
                  className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                    STATUS_CLASSES[email.status] ?? 'bg-gray-100 text-gray-800'
                  }`}
                >
                  {email.status}
                </span>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
