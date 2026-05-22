import { useCallback, useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Combobox } from '@headlessui/react';
import { CheckIcon, XMarkIcon } from '@heroicons/react/20/solid';
import { ChevronUpDownIcon } from '@heroicons/react/24/outline';
import clsx from 'clsx';
import { useDebouncedValue } from '../../hooks/useDebouncedValue';
import { listContacts } from '../../api/contacts';
import { listCompanies } from '../../api/companies';
import { listLeads } from '../../api/leads';
import { listProposals } from '../../api/proposals';
import { showError } from '../../utils/toast';
import { extractApiErrorDetail } from '../../utils/errors';

export type RecordPickerEntityType = 'contacts' | 'companies' | 'leads' | 'proposals';

export interface RecordPickerItem {
  id: number;
  label: string;
  // Optional secondary line — e.g., contact email, proposal number. Helps
  // disambiguate "John Smith" vs "John Smith" when two records share a name.
  detail?: string;
}

interface RecordSearchPickerProps {
  entityType: RecordPickerEntityType;
  value: RecordPickerItem[];
  onChange: (items: RecordPickerItem[]) => void;
  maxRecords?: number;
  disabled?: boolean;
  id?: string;
}

// Normalize the four list endpoints down to a single shape so the picker
// doesn't have to know per-entity field names. Each adapter returns 25
// matches max — enough for "type a few chars and pick" without paginating.
const SEARCH_PAGE_SIZE = 25;

type SearchFilters = { page: number; page_size: number; search?: string };

interface RecordAdapter {
  fetch: (filters: SearchFilters) => Promise<{ items: unknown[] }>;
  toItem: (raw: unknown) => RecordPickerItem;
}

const ADAPTERS: Record<RecordPickerEntityType, RecordAdapter> = {
  contacts: {
    fetch: (f) => listContacts(f),
    toItem: (raw) => {
      const c = raw as { id: number; full_name?: string | null; email?: string | null };
      return {
        id: c.id,
        label: c.full_name || c.email || `Contact #${c.id}`,
        detail: c.email ?? undefined,
      };
    },
  },
  companies: {
    fetch: (f) => listCompanies(f),
    toItem: (raw) => {
      const c = raw as { id: number; name?: string | null; industry?: string | null };
      return {
        id: c.id,
        label: c.name || `Company #${c.id}`,
        detail: c.industry ?? undefined,
      };
    },
  },
  leads: {
    fetch: (f) => listLeads(f),
    toItem: (raw) => {
      const l = raw as {
        id: number;
        full_name?: string | null;
        company_name?: string | null;
        email?: string | null;
      };
      return {
        id: l.id,
        label: l.full_name || l.company_name || `Lead #${l.id}`,
        detail: l.email ?? l.company_name ?? undefined,
      };
    },
  },
  proposals: {
    fetch: (f) => listProposals(f),
    toItem: (raw) => {
      const p = raw as { id: number; title?: string | null; proposal_number?: string | null };
      return {
        id: p.id,
        label: p.title || `Proposal #${p.id}`,
        detail: p.proposal_number ?? undefined,
      };
    },
  },
};

async function searchRecords(
  entityType: RecordPickerEntityType,
  query: string,
): Promise<RecordPickerItem[]> {
  const filters: SearchFilters = {
    page: 1,
    page_size: SEARCH_PAGE_SIZE,
    search: query || undefined,
  };
  const { fetch, toItem } = ADAPTERS[entityType];
  const response = await fetch(filters);
  return response.items.map(toItem);
}

const ENTITY_LABEL: Record<RecordPickerEntityType, string> = {
  contacts: 'contact',
  companies: 'company',
  leads: 'lead',
  proposals: 'proposal',
};

export function RecordSearchPicker({
  entityType,
  value,
  onChange,
  maxRecords,
  disabled = false,
  id,
}: RecordSearchPickerProps) {
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebouncedValue(query, 200);
  const selectedIds = useMemo(() => new Set(value.map((v) => v.id)), [value]);
  const atMax = typeof maxRecords === 'number' && value.length >= maxRecords;
  const entityWord = ENTITY_LABEL[entityType];

  const {
    data: matches = [],
    isFetching,
    isError,
    error,
  } = useQuery<RecordPickerItem[]>({
    queryKey: ['record-picker', entityType, debouncedQuery],
    queryFn: () => searchRecords(entityType, debouncedQuery),
    // Show the most-recent results while typing instead of flashing a
    // "Loading..." between every keystroke. The 200ms debounce above plus
    // keepPreviousData means the dropdown only blanks on the first open.
    placeholderData: (prev) => prev,
    staleTime: 30_000,
  });

  // Surface fetch failures even when the dropdown is closed — otherwise a
  // 5xx looks identical to "no matches" and the user might silently
  // submit a stale partial selection. Fire once per error transition,
  // not per refetch, so we don't spam toasts on a thrashy connection.
  const [lastErroredQueryKey, setLastErroredQueryKey] = useState<string | null>(null);
  useEffect(() => {
    const key = `${entityType}|${debouncedQuery}`;
    if (isError && lastErroredQueryKey !== key) {
      showError(
        extractApiErrorDetail(error) ??
          `Failed to search ${entityWord} records. Check your connection and try again.`,
      );
      setLastErroredQueryKey(key);
    } else if (!isError && lastErroredQueryKey === key) {
      // The same query succeeded later — clear the latch so a future
      // failure on this key re-toasts.
      setLastErroredQueryKey(null);
    }
  }, [isError, error, entityType, debouncedQuery, entityWord, lastErroredQueryKey]);

  const handleSelect = useCallback(
    (next: RecordPickerItem[] | null) => {
      // Combobox can hand back `null` if the input is cleared with no
      // selection — coalesce so we never call onChange(null).
      const safe = next ?? [];
      // Respect the cap. If a paste-like multi-add overshoots, drop the
      // overflow rather than silently re-shrinking back to the cap on the
      // next render.
      if (typeof maxRecords === 'number' && safe.length > maxRecords) {
        onChange(safe.slice(0, maxRecords));
        return;
      }
      onChange(safe);
      // Clear the query after each pick so the user can search the next
      // record without first deleting the prior token.
      setQuery('');
    },
    [maxRecords, onChange],
  );

  // When the parent flips entityType, the previously-selected IDs are
  // from a different table and are now meaningless — wipe them so we
  // don't accidentally POST contact #5 against /sharing as a company.
  useEffect(() => {
    if (value.length > 0) onChange([]);
    setQuery('');
    // We intentionally only watch entityType. Listening to `value` here
    // would trip an infinite loop with the onChange() above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityType]);

  return (
    <div>
      <Combobox<RecordPickerItem[]>
        multiple
        value={value}
        onChange={handleSelect}
        disabled={disabled}
      >
        <div className="relative">
          <div
            className={clsx(
              'flex flex-wrap items-center gap-1.5 rounded-lg border border-gray-300 bg-white p-2 text-sm shadow-sm focus-within:border-primary-500 focus-within:ring-2 focus-within:ring-primary-500 dark:border-gray-600 dark:bg-gray-700',
              disabled && 'cursor-not-allowed opacity-60',
            )}
          >
            {value.map((item) => (
              <span
                key={item.id}
                className="inline-flex max-w-full items-center gap-1 rounded-full bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary-700 dark:bg-primary-900/30 dark:text-primary-300"
              >
                <span className="truncate" title={item.detail ? `${item.label} — ${item.detail}` : item.label}>
                  {item.label}
                </span>
                <button
                  type="button"
                  onClick={() => onChange(value.filter((v) => v.id !== item.id))}
                  aria-label={`Remove ${item.label}`}
                  className="rounded-full hover:bg-primary-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 dark:hover:bg-primary-800/50"
                  disabled={disabled}
                >
                  <XMarkIcon className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              </span>
            ))}
            <Combobox.Input
              id={id}
              autoComplete="off"
              spellCheck={false}
              placeholder={
                atMax
                  ? `${maxRecords} ${entityWord} records selected (max)`
                  : value.length === 0
                  ? `Search ${entityWord} records by name`
                  : `Add another ${entityWord}`
              }
              className={clsx(
                'min-w-[8rem] flex-1 border-0 bg-transparent p-0 text-sm text-gray-900 placeholder:text-gray-400 focus:outline-none focus:ring-0 dark:text-gray-100 dark:placeholder:text-gray-500',
                atMax && 'cursor-not-allowed',
              )}
              displayValue={() => query}
              onChange={(e) => setQuery(e.target.value)}
              readOnly={atMax}
            />
            <Combobox.Button
              className="ml-auto inline-flex h-6 w-6 items-center justify-center text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
              aria-label="Show matches"
            >
              <ChevronUpDownIcon className="h-4 w-4" aria-hidden="true" />
            </Combobox.Button>
          </div>

          <Combobox.Options className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-gray-200 bg-white py-1 text-sm shadow-lg focus:outline-none dark:border-gray-700 dark:bg-gray-800">
            {isError && (
              <div className="px-3 py-2 text-xs text-red-600 dark:text-red-300">
                Failed to load matches. Check your connection and try again.
              </div>
            )}
            {!isError && !isFetching && matches.length === 0 && (
              <div className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400">
                {debouncedQuery
                  ? `No ${entityWord} records match "${debouncedQuery}".`
                  : `Type to search ${entityWord} records.`}
              </div>
            )}
            {!isError && isFetching && matches.length === 0 && (
              <div className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400">
                Searching {entityWord}…
              </div>
            )}
            {matches.map((match) => {
              const isSelected = selectedIds.has(match.id);
              return (
                <Combobox.Option
                  key={match.id}
                  value={match}
                  className={({ active }) =>
                    clsx(
                      'flex cursor-pointer items-center justify-between gap-3 px-3 py-2',
                      active && 'bg-primary-50 dark:bg-primary-900/30',
                    )
                  }
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium text-gray-900 dark:text-gray-100">
                      {match.label}
                    </p>
                    {match.detail && (
                      <p className="truncate text-xs text-gray-500 dark:text-gray-400">
                        {match.detail}
                      </p>
                    )}
                  </div>
                  {isSelected && (
                    <CheckIcon className="h-4 w-4 text-primary-600 dark:text-primary-400" aria-hidden="true" />
                  )}
                </Combobox.Option>
              );
            })}
          </Combobox.Options>
        </div>
      </Combobox>
      <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
        {value.length} selected
        {typeof maxRecords === 'number' && ` / ${maxRecords} max`}
      </p>
    </div>
  );
}
