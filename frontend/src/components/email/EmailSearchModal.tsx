import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { emailApi, type EmailSearchResult } from '../../api/email';
import { Spinner } from '../ui';
import { Modal } from '../ui/Modal';

interface EmailSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  /** When set, initial search is scoped to this entity. */
  entityType?: string;
  entityId?: number;
}

function formatDate(value: string | null): string {
  if (!value) return '';
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(value));
}

const SEARCH_ICON = (
  <svg className="h-5 w-5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
  </svg>
);

export function EmailSearchModal({ isOpen, onClose, entityType, entityId }: EmailSearchModalProps) {
  const [query, setQuery] = useState('');
  const [scopedToEntity, setScopedToEntity] = useState(Boolean(entityType && entityId));
  const [results, setResults] = useState<EmailSearchResult[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  const runSearch = useCallback(
    async (q: string, scoped: boolean) => {
      if (!q.trim()) {
        setResults([]);
        setTotal(0);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const params: Parameters<typeof emailApi.search>[0] = { q, page_size: 25 };
        if (scoped && entityType && entityId != null) {
          params.entity_type = entityType;
          params.entity_id = entityId;
        }
        const data = await emailApi.search(params);
        setResults(data.items);
        setTotal(data.total);
      } catch {
        setError('Search failed. Please try again.');
      } finally {
        setLoading(false);
      }
    },
    [entityType, entityId],
  );

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => runSearch(query, scopedToEntity), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query, scopedToEntity, runSearch]);

  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setResults([]);
      setTotal(0);
      setError(null);
      setScopedToEntity(Boolean(entityType && entityId));
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen, entityType, entityId]);

  const handleResultClick = (item: EmailSearchResult) => {
    if (item.entity_type && item.entity_id != null) {
      // `kind:id` deep-link so the entity page opens the Emails tab
      // and scrolls to the matched message instead of dumping the user
      // on the default Details tab.
      const target = `${item.kind}:${item.id}`;
      navigate(`/${item.entity_type}/${item.entity_id}?tab=emails&email=${encodeURIComponent(target)}`);
      onClose();
    }
  };

  const hasEntityFilter = Boolean(entityType && entityId);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="xl"
      showCloseButton={false}
      closeOnOverlayClick={true}
    >
      {/* Search input */}
      <div className="-mx-4 -mt-4 sm:-mx-6 sm:-mt-6 flex items-center gap-3 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
        {SEARCH_ICON}
        <input
          ref={inputRef}
          type="search"
          className="flex-1 bg-transparent text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none text-sm"
          placeholder="Search emails by subject, body, sender, or recipient..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          spellCheck={false}
          autoComplete="off"
        />
        {loading && <Spinner size="sm" />}
        <button
          type="button"
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded"
          aria-label="Close search"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Scope toggle */}
      {hasEntityFilter && (
        <div className="-mx-4 sm:-mx-6 px-4 py-2 border-b border-gray-100 dark:border-gray-700 flex items-center gap-2">
          <label className="flex items-center gap-2 cursor-pointer select-none text-sm text-gray-600 dark:text-gray-400">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              checked={!scopedToEntity}
              onChange={(e) => setScopedToEntity(!e.target.checked)}
            />
            Search across all emails
          </label>
          {scopedToEntity && (
            <span className="text-xs text-gray-400 dark:text-gray-500">
              (scoped to current {entityType?.replace(/s$/, '')})
            </span>
          )}
        </div>
      )}

      {/* Results */}
      <div className="-mx-4 sm:-mx-6 max-h-[60vh] overflow-y-auto">
        {error && (
          <p className="px-4 py-3 text-sm text-red-600 dark:text-red-400">{error}</p>
        )}

        {!loading && !error && query.trim() && results.length === 0 && (
          <p className="px-4 py-6 text-sm text-center text-gray-500 dark:text-gray-400">
            No emails found for &ldquo;{query}&rdquo;
          </p>
        )}

        {!query.trim() && (
          <p className="px-4 py-6 text-sm text-center text-gray-400 dark:text-gray-500">
            Type to search across your emails...
          </p>
        )}

        {results.length > 0 && (
          <>
            <p className="px-4 py-2 text-xs text-gray-400 dark:text-gray-500 border-b border-gray-100 dark:border-gray-700">
              {total} result{total !== 1 ? 's' : ''}
              {total > 25 ? ' (showing first 25)' : ''}
            </p>
            <ul role="listbox">
              {results.map((item) => (
                <li key={`${item.kind}-${item.id}`}>
                  <button
                    type="button"
                    className="w-full text-left px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-700/60 focus-visible:outline-none focus-visible:bg-gray-50 dark:focus-visible:bg-gray-700/60 border-b border-gray-100 dark:border-gray-700/50 last:border-0"
                    onClick={() => handleResultClick(item)}
                    aria-label={`${item.kind === 'sent' ? 'Sent' : 'Received'}: ${item.subject}`}
                  >
                    <div className="flex items-start justify-between gap-3 min-w-0">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 mb-0.5">
                          <span
                            className={`shrink-0 inline-block text-xs font-medium px-1.5 py-0.5 rounded ${
                              item.kind === 'sent'
                                ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
                                : 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300'
                            }`}
                          >
                            {item.kind === 'sent' ? 'Sent' : 'Received'}
                          </span>
                          <span className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                            {item.subject || '(No subject)'}
                          </span>
                        </div>
                        <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                          {item.kind === 'sent'
                            ? `To: ${item.to_email}`
                            : `From: ${item.from_email || 'Unknown'}`}
                        </p>
                        {item.snippet && (
                          <p className="text-xs text-gray-400 dark:text-gray-500 truncate mt-0.5">
                            {item.snippet}
                          </p>
                        )}
                      </div>
                      {item.sent_at && (
                        <span className="shrink-0 text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap">
                          {formatDate(item.sent_at)}
                        </span>
                      )}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </Modal>
  );
}
