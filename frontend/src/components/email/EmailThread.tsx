import { useState } from 'react';
import DOMPurify from 'dompurify';
import { Spinner, Badge, Button } from '../ui';
import { useEmailThread } from '../../hooks/useEmail';
import type { ThreadEmailItem } from '../../types/email';
import type { BadgeVariant } from '../ui/Badge';

interface EmailThreadProps {
  entityType: string;
  entityId: number;
  onReply?: (email: ThreadEmailItem) => void;
  onCompose?: () => void;
}

const STATUS_BADGE: Record<string, { variant: BadgeVariant; label: string }> = {
  sent: { variant: 'green', label: 'Sent' },
  failed: { variant: 'red', label: 'Failed' },
  pending: { variant: 'yellow', label: 'Pending' },
  received: { variant: 'blue', label: 'Received' },
};

function formatTimestamp(dateString: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(dateString));
}

function EmailBubble({
  email,
  onReply,
}: {
  email: ThreadEmailItem;
  onReply?: (email: ThreadEmailItem) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const isOutbound = email.direction === 'outbound';
  const status = isOutbound ? (email.status || 'pending') : 'received';
  const badge = STATUS_BADGE[status] ?? { variant: 'gray' as BadgeVariant, label: status };
  const bodyContent = email.body || email.body_html || '';

  return (
    <div
      className={`flex ${isOutbound ? 'justify-end' : 'justify-start'}`}
    >
      <div
        className={`max-w-[85%] sm:max-w-[70%] rounded-lg p-3 sm:p-4 ${
          isOutbound
            ? 'bg-primary-600 text-white dark:bg-primary-700'
            : 'bg-gray-100 text-gray-900 dark:bg-gray-700 dark:text-gray-100'
        }`}
      >
        {/* Header: from/to + status */}
        <div className="flex items-start justify-between gap-2 mb-1">
          <div className="min-w-0 flex-1">
            <p className={`text-xs truncate ${isOutbound ? 'text-primary-100' : 'text-gray-500 dark:text-gray-400'}`}>
              {isOutbound ? `To: ${email.to_email}` : `From: ${email.from_email || 'Unknown'}`}
            </p>
            {email.cc && (
              <p className={`text-xs truncate ${isOutbound ? 'text-primary-200' : 'text-gray-400 dark:text-gray-500'}`}>
                CC: {email.cc}
              </p>
            )}
          </div>
          <Badge variant={badge.variant} size="sm">
            {badge.label}
          </Badge>
        </div>

        {/* Subject */}
        <p className={`text-sm font-medium ${isOutbound ? 'text-white' : 'text-gray-900 dark:text-gray-100'}`}>
          {email.subject}
        </p>

        {/* Timestamp + metrics */}
        <div className={`flex items-center gap-3 mt-1 text-xs ${isOutbound ? 'text-primary-200' : 'text-gray-400 dark:text-gray-500'}`}>
          <span>{formatTimestamp(email.timestamp)}</span>
          {isOutbound && email.open_count != null && email.open_count > 0 && (
            <span>Opened {email.open_count}x</span>
          )}
        </div>

        {/* Expandable body */}
        <button
          type="button"
          onClick={() => setExpanded((prev) => !prev)}
          className={`mt-2 text-xs font-medium focus-visible:outline-none focus-visible:underline ${
            isOutbound
              ? 'text-primary-200 hover:text-white'
              : 'text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300'
          }`}
          aria-label={expanded ? 'Collapse email body' : 'Expand email body'}
          aria-expanded={expanded}
        >
          {expanded ? 'Hide body' : 'Show body'}
        </button>

        {expanded && (
          <div
            className={`mt-2 text-sm whitespace-pre-wrap break-words border-t pt-2 ${
              isOutbound
                ? 'border-primary-500 text-primary-50'
                : 'border-gray-200 dark:border-gray-600 text-gray-800 dark:text-gray-200'
            }`}
          >
            {email.body_html ? (
              <div
                dangerouslySetInnerHTML={{
                  __html: DOMPurify.sanitize(email.body_html),
                }}
              />
            ) : (
              bodyContent
            )}
          </div>
        )}

        {/* Reply button for inbound emails */}
        {!isOutbound && onReply && (
          <button
            type="button"
            onClick={() => onReply(email)}
            className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 focus-visible:outline-none focus-visible:underline"
            aria-label={`Reply to email from ${email.from_email || 'sender'}`}
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
            </svg>
            Reply
          </button>
        )}
      </div>
    </div>
  );
}

export function EmailThread({ entityType, entityId, onReply, onCompose }: EmailThreadProps) {
  const [page, setPage] = useState(1);
  const { data, isLoading } = useEmailThread(entityType, entityId, page);

  if (isLoading && page === 1) {
    return (
      <div className="flex items-center justify-center py-8">
        <Spinner size="sm" />
      </div>
    );
  }

  const emails = data?.items ?? [];
  const totalPages = data?.pages ?? 1;

  if (emails.length === 0 && page === 1) {
    return (
      <div className="text-center py-8">
        <svg className="mx-auto h-12 w-12 text-gray-300 dark:text-gray-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
        </svg>
        <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">No emails yet.</p>
        {onCompose && (
          <Button
            variant="primary"
            onClick={onCompose}
            className="mt-3"
          >
            Send First Email
          </Button>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Load older emails */}
      {totalPages > 1 && page < totalPages && (
        <div className="text-center">
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            disabled={isLoading}
            className="text-sm text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 font-medium focus-visible:outline-none focus-visible:underline disabled:opacity-50"
            aria-label="Load older emails"
          >
            {isLoading ? 'Loading...' : 'Load older emails'}
          </button>
        </div>
      )}

      {/* Email bubbles */}
      {emails.map((email) => (
        <EmailBubble
          key={`${email.direction}-${email.id}`}
          email={email}
          onReply={onReply}
        />
      ))}
    </div>
  );
}
