import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
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

const REPLY_ARROW_ICON = (
  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6" />
  </svg>
);

function formatTimestamp(dateString: string): string {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(dateString));
}

interface EmailGroup {
  key: string;
  threadId: string | null;
  subject: string;
  participants: string[];
  latestTimestamp: string;
  messages: ThreadEmailItem[];
}

// Group emails by Gmail's thread_id. Messages without one fall into singleton
// groups so legacy Resend rows still render (they just lack threading).
function groupByThread(items: ThreadEmailItem[]): EmailGroup[] {
  const map = new Map<string, EmailGroup>();

  for (const email of items) {
    const key = email.thread_id
      ? `thread:${email.thread_id}`
      : `single:${email.direction}:${email.id}`;
    let group = map.get(key);
    if (!group) {
      group = {
        key,
        threadId: email.thread_id,
        subject: email.subject,
        participants: [],
        latestTimestamp: email.timestamp,
        messages: [],
      };
      map.set(key, group);
    }
    group.messages.push(email);

    const participant =
      email.direction === 'outbound' ? email.to_email : email.from_email || 'Unknown';
    if (participant && !group.participants.includes(participant)) {
      group.participants.push(participant);
    }

    if (new Date(email.timestamp) > new Date(group.latestTimestamp)) {
      group.latestTimestamp = email.timestamp;
    }
  }

  const groups = Array.from(map.values());
  for (const g of groups) {
    g.messages.sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
    );
    // Use the earliest message's subject so a "Re: Re: X" reply doesn't
    // overwrite the canonical thread topic in the header.
    g.subject = g.messages[0]?.subject || g.subject;
  }
  groups.sort(
    (a, b) =>
      new Date(b.latestTimestamp).getTime() - new Date(a.latestTimestamp).getTime(),
  );
  return groups;
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
  const bodyContent = email.body || '';

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
            <p className={`text-xs truncate ${isOutbound ? 'text-white/90' : 'text-gray-500 dark:text-gray-400'}`}>
              {isOutbound ? `To: ${email.to_email}` : `From: ${email.from_email || 'Unknown'}`}
            </p>
            {email.cc && (
              <p className={`text-xs truncate ${isOutbound ? 'text-white/80' : 'text-gray-400 dark:text-gray-500'}`}>
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
        <div className={`flex items-center gap-3 mt-1 text-xs ${isOutbound ? 'text-white/80' : 'text-gray-500 dark:text-gray-400'}`}>
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
              ? 'text-white/90 hover:text-white'
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
                ? 'border-white/20 text-white'
                : 'border-gray-200 dark:border-gray-600 text-gray-800 dark:text-gray-200'
            }`}
          >
            {email.body_html ? (
              <div
                dangerouslySetInnerHTML={{
                  __html: DOMPurify.sanitize(email.body_html, { FORBID_TAGS: ['style', 'form'], FORBID_ATTR: ['style'] }),
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
            {REPLY_ARROW_ICON}
            Reply
          </button>
        )}
      </div>
    </div>
  );
}

function ThreadCard({
  group,
  defaultExpanded,
  onReply,
}: {
  group: EmailGroup;
  defaultExpanded: boolean;
  onReply?: (email: ThreadEmailItem) => void;
}) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const isMultiMessage = group.messages.length > 1;
  const displayedParticipants = group.participants.slice(0, 2).join(', ');
  const extraParticipants =
    group.participants.length > 2 ? `, +${group.participants.length - 2}` : '';

  const headerId = `thread-${group.key}`;
  const panelId = `panel-${group.key}`;

  // Reply targets the newest message so outbound-only threads stay repliable.
  // Messages are sorted ascending by timestamp above, so the last entry is newest.
  const latestMessage = group.messages.at(-1);

  return (
    <section
      className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 overflow-hidden"
      aria-labelledby={headerId}
    >
      <div className="w-full px-3 sm:px-4 py-2 sm:py-3 flex items-center gap-3 bg-gray-50 dark:bg-gray-800/60">
        <button
          type="button"
          id={headerId}
          onClick={() => setExpanded((p) => !p)}
          className="flex items-center justify-between gap-3 text-left flex-1 min-w-0 hover:bg-gray-100 dark:hover:bg-gray-700/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded-md -mx-1 px-1 py-1"
          aria-expanded={expanded}
          aria-controls={panelId}
        >
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-0.5">
              <p className="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">
                {group.subject || '(No subject)'}
              </p>
              {isMultiMessage && (
                <Badge variant="gray" size="sm">
                  {group.messages.length} messages
                </Badge>
              )}
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
              {displayedParticipants}
              {extraParticipants} · {formatTimestamp(group.latestTimestamp)}
            </p>
          </div>
          <svg
            className={`h-4 w-4 shrink-0 text-gray-400 transition-transform ${
              expanded ? 'rotate-180' : ''
            }`}
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        {onReply && latestMessage && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onReply(latestMessage);
            }}
            className="inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 shrink-0"
            aria-label={`Reply to thread: ${group.subject || '(No subject)'}`}
          >
            {REPLY_ARROW_ICON}
            Reply
          </button>
        )}
      </div>
      {expanded && (
        <div id={panelId} className="px-3 sm:px-4 py-3 space-y-3">
          {group.messages.map((email) => (
            <EmailBubble
              key={`${email.direction}-${email.id}`}
              email={email}
              onReply={onReply}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export function EmailThread({ entityType, entityId, onReply, onCompose }: EmailThreadProps) {
  const [page, setPage] = useState(1);
  const [accumulated, setAccumulated] = useState<ThreadEmailItem[]>([]);
  const { data, isLoading } = useEmailThread(entityType, entityId, page);
  const prevPageRef = useRef(page);

  // Append new page data to accumulated list when data arrives
  useEffect(() => {
    if (!data?.items) return;
    if (page === 1) {
      setAccumulated(data.items);
    } else if (page !== prevPageRef.current) {
      // Older pages append to the beginning (they are older emails)
      setAccumulated((prev) => [...data.items, ...prev]);
    }
    prevPageRef.current = page;
  }, [data, page]);

  const groups = useMemo(() => groupByThread(accumulated), [accumulated]);

  const loadOlder = useCallback(() => {
    setPage((p) => p + 1);
  }, []);

  if (isLoading && page === 1) {
    return (
      <div className="flex items-center justify-center py-8">
        <Spinner size="sm" />
      </div>
    );
  }

  const totalPages = data?.pages ?? 1;

  if (accumulated.length === 0 && page === 1) {
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
            onClick={loadOlder}
            disabled={isLoading}
            className="text-sm text-primary-600 dark:text-primary-400 hover:text-primary-700 dark:hover:text-primary-300 font-medium focus-visible:outline-none focus-visible:underline disabled:opacity-50"
            aria-label="Load older emails"
          >
            {isLoading ? 'Loading...' : 'Load older emails'}
          </button>
        </div>
      )}

      {/* Thread cards (grouped by Gmail thread_id) */}
      {groups.map((group, index) => (
        <ThreadCard
          key={group.key}
          group={group}
          defaultExpanded={index === 0}
          onReply={onReply}
        />
      ))}
    </div>
  );
}
