import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { MagnifyingGlassIcon } from '@heroicons/react/24/outline';
import { useQueries } from '@tanstack/react-query';
import { listContacts } from '../../api/contacts';
import { listCompanies } from '../../api/companies';
import { listLeads } from '../../api/leads';
import { listProposals } from '../../api/proposals';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';

interface SearchResult {
  id: number;
  entity: 'contact' | 'company' | 'lead' | 'proposal';
  label: string;
  sublabel?: string;
  href: string;
}

// Each list endpoint returns a different DTO shape; the toResult adapter
// picks just the id/label/sublabel we render. The argument is typed as
// `Record<string, unknown>` and adapters cast inside — the alternative
// (per-entity generics on EntityConfig) blows up the union type without
// changing the behavior at this surface.
type SearchableRecord = Record<string, unknown>;

interface EntityConfig {
  entity: SearchResult['entity'];
  groupLabel: string;
  routePrefix: string;
  fetch: (q: string) => Promise<{ items: unknown[] }>;
  toResult: (item: SearchableRecord) => Pick<SearchResult, 'id' | 'label' | 'sublabel'>;
}

interface MaybeNamed { name?: string }

const ENTITIES: EntityConfig[] = [
  {
    entity: 'contact',
    groupLabel: 'Contacts',
    routePrefix: '/contacts',
    fetch: (q) => listContacts({ search: q, page_size: 5 }) as Promise<{ items: unknown[] }>,
    toResult: (raw) => {
      const c = raw as { id: number; full_name?: string; email?: string; company?: MaybeNamed };
      return {
        id: c.id,
        label: c.full_name || c.email || `Contact #${c.id}`,
        sublabel: c.email && c.full_name ? c.email : c.company?.name,
      };
    },
  },
  {
    entity: 'company',
    groupLabel: 'Companies',
    routePrefix: '/companies',
    fetch: (q) => listCompanies({ search: q, page_size: 5 }) as Promise<{ items: unknown[] }>,
    toResult: (raw) => {
      const c = raw as { id: number; name: string; domain?: string; industry?: string };
      return { id: c.id, label: c.name, sublabel: c.domain || c.industry };
    },
  },
  {
    entity: 'lead',
    groupLabel: 'Leads',
    routePrefix: '/leads',
    fetch: (q) => listLeads({ search: q, page_size: 5 }) as Promise<{ items: unknown[] }>,
    toResult: (raw) => {
      const l = raw as { id: number; name?: string; company_name?: string; email?: string };
      return {
        id: l.id,
        label: l.name || l.company_name || `Lead #${l.id}`,
        sublabel: l.email || l.company_name,
      };
    },
  },
  // Quotes search category removed 2026-05-14 — quotes router unmounted.
  {
    entity: 'proposal',
    groupLabel: 'Proposals',
    routePrefix: '/proposals',
    fetch: (q) => listProposals({ search: q, page_size: 5 }) as Promise<{ items: unknown[] }>,
    toResult: (raw) => {
      const p = raw as { id: number; title: string; company?: MaybeNamed };
      return { id: p.id, label: p.title, sublabel: p.company?.name };
    },
  },
];

interface GlobalSearchProps {
  inputId: string;
  placeholder?: string;
  className?: string;
  // Mount-time focus is opt-in. CLAUDE.md cautions against `autoFocus`
  // on mobile; the mobile overlay still passes it because the overlay
  // is user-initiated (tap the magnifier) — exception, not default.
  focusOnMount?: boolean;
  onNavigated?: () => void;
}

/**
 * Spotlight-style global search. Token-based queries hit every list
 * endpoint in parallel (each backend already wraps build_token_search),
 * grouped results render in a dropdown, click or Enter navigates.
 */
export function GlobalSearch({
  inputId,
  placeholder = 'Search contacts, companies, deals...',
  className,
  focusOnMount,
  onNavigated,
}: GlobalSearchProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const listboxId = useId();

  const debounced = useDebouncedValue(query.trim(), 250);

  // Explicit focus call instead of `autoFocus` so the focus moves after
  // the mobile overlay's mount animation, avoiding the iOS keyboard
  // popping mid-transition (the CLAUDE.md autoFocus warning specifically
  // targets the autoFocus prop's pre-mount focus behavior).
  useEffect(() => {
    if (focusOnMount) inputRef.current?.focus();
  }, [focusOnMount]);

  // Parallel fan-out: one query per entity. enabled gate keeps the
  // network quiet until the user has typed at least 2 chars.
  const queries = useQueries({
    queries: ENTITIES.map((e) => ({
      queryKey: ['global-search', e.entity, debounced],
      queryFn: () => e.fetch(debounced),
      enabled: debounced.length >= 2,
      staleTime: 30_000,
    })),
  });

  const isLoading = queries.some((q) => q.isFetching) && debounced.length >= 2;

  const failedEntities = useMemo(
    () =>
      ENTITIES.flatMap((e, i) => (queries[i]?.isError ? [e.groupLabel] : []))
        .filter((v, i, arr) => arr.indexOf(v) === i),
    [queries]
  );

  // Surface per-query errors to console so a future Sentry hook or a
  // user-reported "search is broken for me" has something to chew on.
  useEffect(() => {
    queries.forEach((q, i) => {
      if (q.isError) {
        const entity = ENTITIES[i]?.entity ?? 'unknown';
        console.warn(`[global-search] ${entity} query failed`, q.error);
      }
    });
  }, [queries]);

  const grouped = useMemo(() => {
    return ENTITIES.map((e, i) => {
      const items = (queries[i]?.data?.items ?? []) as unknown[];
      return {
        entity: e.entity,
        groupLabel: e.groupLabel,
        results: items
          .map((item) => {
            const base = e.toResult(item as SearchableRecord);
            // Drop rows missing a numeric id — adapters cast unsafely and a
            // malformed API response would otherwise render `/contacts/undefined`.
            if (typeof base.id !== 'number' || !Number.isFinite(base.id)) {
              return null;
            }
            return {
              ...base,
              entity: e.entity,
              href: `${e.routePrefix}/${base.id}`,
            } as SearchResult;
          })
          .filter((r): r is SearchResult => r !== null),
      };
    }).filter((g) => g.results.length > 0);
  }, [queries]);

  const flat = useMemo(() => grouped.flatMap((g) => g.results), [grouped]);
  const totalCount = flat.length;

  useEffect(() => {
    setActiveIndex(0);
  }, [debounced]);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onDocClick);
    return () => document.removeEventListener('mousedown', onDocClick);
  }, [open]);

  const close = useCallback(() => {
    setOpen(false);
    setQuery('');
  }, []);

  const go = useCallback(
    (result: SearchResult) => {
      navigate(result.href);
      close();
      onNavigated?.();
    },
    [navigate, close, onNavigated]
  );

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      close();
      inputRef.current?.blur();
      return;
    }
    if (!open && (e.key === 'ArrowDown' || e.key === 'Enter')) {
      setOpen(true);
    }
    if (e.key === 'ArrowDown' && totalCount > 0) {
      e.preventDefault();
      setActiveIndex((i) => (i + 1) % totalCount);
    } else if (e.key === 'ArrowUp' && totalCount > 0) {
      e.preventDefault();
      setActiveIndex((i) => (i - 1 + totalCount) % totalCount);
    } else if (e.key === 'Enter' && totalCount > 0) {
      e.preventDefault();
      const target = flat[activeIndex];
      if (target) go(target);
    }
  };

  // Gate on the current input value too, not just the (potentially stale)
  // debounced value — prevents the dropdown re-opening with old results
  // when the input is refocused right after close().
  const showDropdown = open && debounced.length >= 2 && query.trim().length >= 2;
  const showEmpty =
    showDropdown && !isLoading && totalCount === 0 && failedEntities.length === 0;

  return (
    <div ref={containerRef} className={className}>
      <div className="relative w-full">
        <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
          <MagnifyingGlassIcon
            className="h-5 w-5 text-gray-400 dark:text-gray-500"
            aria-hidden="true"
          />
        </div>
        <input
          ref={inputRef}
          id={inputId}
          type="search"
          role="combobox"
          aria-expanded={showDropdown}
          aria-controls={listboxId}
          aria-activedescendant={
            showDropdown && totalCount > 0 ? `${listboxId}-${activeIndex}` : undefined
          }
          aria-autocomplete="list"
          autoComplete="off"
          placeholder={placeholder}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => debounced.length >= 2 && setOpen(true)}
          onKeyDown={onKeyDown}
          className="block w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg leading-5 bg-white dark:bg-gray-700 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:border-primary-500"
        />
      </div>

      {showDropdown && (
        <div
          id={listboxId}
          role="listbox"
          aria-label="Global search results"
          className="absolute z-40 mt-1 w-full max-w-[min(640px,calc(100vw-2rem))] max-h-[70vh] overflow-y-auto rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-lg"
        >
          {isLoading && totalCount === 0 && failedEntities.length === 0 && (
            <div className="px-3 py-3 text-sm text-gray-500 dark:text-gray-400" aria-live="polite">
              Searching…
            </div>
          )}
          {failedEntities.length > 0 && (
            <div
              className="px-3 py-2 text-xs border-b border-yellow-200 bg-yellow-50 text-yellow-800 dark:border-yellow-900 dark:bg-yellow-900/30 dark:text-yellow-200"
              role="status"
              aria-live="polite"
            >
              Couldn{'’'}t search {failedEntities.join(', ')}. Try again in a moment.
            </div>
          )}
          {showEmpty && (
            <div className="px-3 py-3 text-sm text-gray-500 dark:text-gray-400" aria-live="polite">
              No results for{' '}
              <span className="font-medium text-gray-700 dark:text-gray-200">
                &ldquo;{debounced}&rdquo;
              </span>
              .
            </div>
          )}
          {grouped.map((group) => (
            <div key={group.entity}>
              <div className="px-3 pt-2 pb-1 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                {group.groupLabel}
              </div>
              {group.results.map((r) => {
                const flatIndex = flat.indexOf(r);
                const isActive = flatIndex === activeIndex;
                return (
                  <button
                    key={`${r.entity}-${r.id}`}
                    id={`${listboxId}-${flatIndex}`}
                    role="option"
                    aria-selected={isActive}
                    type="button"
                    onMouseEnter={() => setActiveIndex(flatIndex)}
                    onClick={() => go(r)}
                    className={`block w-full text-left px-3 py-2 text-sm transition-colors ${
                      isActive
                        ? 'bg-primary-50 dark:bg-primary-900/30 text-gray-900 dark:text-gray-100'
                        : 'text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700/60'
                    }`}
                  >
                    <div className="font-medium truncate">{r.label}</div>
                    {r.sublabel && (
                      <div className="text-xs text-gray-500 dark:text-gray-400 truncate">
                        {r.sublabel}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
