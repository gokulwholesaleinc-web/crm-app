import { useState, useMemo, useId, ReactNode } from 'react';
import clsx from 'clsx';
import { MagnifyingGlassIcon, CheckIcon } from '@heroicons/react/24/outline';
import { Spinner } from '../ui/Spinner';

export interface ScrollableListPickerProps<T> {
  items: T[];
  selectedIds: Array<string | number>;
  onSelectionChange: (ids: Array<string | number>) => void;
  getItemId: (item: T) => string | number;
  renderItem: (item: T, isSelected: boolean) => ReactNode;
  searchPlaceholder?: string;
  filterFn?: (item: T, query: string) => boolean;
  isLoading?: boolean;
  emptyMessage?: string;
  multiSelect?: boolean;
  disabledIds?: Array<string | number>;
  maxHeight?: string;
  showSelectAll?: boolean;
}

export function ScrollableListPicker<T>({
  items,
  selectedIds,
  onSelectionChange,
  getItemId,
  renderItem,
  searchPlaceholder = 'Search...',
  filterFn,
  isLoading = false,
  emptyMessage = 'No items available.',
  multiSelect = true,
  disabledIds = [],
  maxHeight = 'max-h-[40vh]',
  showSelectAll = true,
}: ScrollableListPickerProps<T>) {
  const [query, setQuery] = useState('');
  const searchId = useId();

  const disabledSet = useMemo(() => new Set(disabledIds), [disabledIds]);

  const visibleItems = useMemo(() => {
    if (!query.trim() || !filterFn) return items;
    return items.filter((item) => filterFn(item, query));
  }, [items, query, filterFn]);

  const handleToggle = (id: string | number) => {
    if (disabledSet.has(id)) return;
    if (!multiSelect) {
      onSelectionChange(selectedIds.includes(id) ? [] : [id]);
      return;
    }
    onSelectionChange(
      selectedIds.includes(id)
        ? selectedIds.filter((s) => s !== id)
        : [...selectedIds, id]
    );
  };

  const handleSelectAll = () => {
    const visibleIds = new Set(visibleItems.map(getItemId));
    // Keep selections that are outside the current filter view, then add all
    // visible non-disabled items. Without this, filtering to 3 items and
    // clicking "Select All" would silently clear the other N selected items.
    const preserved = selectedIds.filter((id) => !visibleIds.has(id));
    const toAdd = visibleItems
      .map(getItemId)
      .filter((id) => !disabledSet.has(id));
    onSelectionChange([...preserved, ...toAdd]);
  };

  const handleClear = () => {
    onSelectionChange([]);
  };

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  return (
    <div>
      <div className="relative mb-3">
        <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
        <label htmlFor={searchId} className="sr-only">{searchPlaceholder}</label>
        <input
          type="search"
          id={searchId}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={searchPlaceholder}
          className="w-full pl-10 pr-4 py-2 text-base sm:text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
        />
      </div>

      {multiSelect && showSelectAll && (
        <div className="flex items-center justify-between text-sm mb-3">
          <span className="text-gray-600">{selectedIds.length} selected</span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleSelectAll}
              disabled={visibleItems.length === 0}
              className="text-primary-600 hover:text-primary-700 disabled:opacity-40"
            >
              Select All
            </button>
            <span className="text-gray-300">|</span>
            <button
              type="button"
              onClick={handleClear}
              disabled={selectedIds.length === 0}
              className="text-gray-500 hover:text-gray-700 disabled:opacity-40"
            >
              Clear
            </button>
          </div>
        </div>
      )}

      <div className={clsx('overflow-y-auto', maxHeight)}>
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Spinner />
          </div>
        ) : visibleItems.length === 0 ? (
          <div className="text-center py-12 text-gray-500">
            <p>{emptyMessage}</p>
            {query && <p className="text-sm mt-1">Try adjusting your search.</p>}
          </div>
        ) : (
          <div className="space-y-2">
            {visibleItems.map((item) => {
              const id = getItemId(item);
              const isSelected = selectedSet.has(id);
              const isDisabled = disabledSet.has(id);

              return (
                <button
                  key={id}
                  type="button"
                  onClick={() => handleToggle(id)}
                  disabled={isDisabled}
                  aria-pressed={isSelected}
                  className={clsx(
                    'w-full flex items-center gap-3 p-3 rounded-lg border text-left transition-colors',
                    isDisabled
                      ? 'border-gray-200 bg-gray-50 opacity-50 cursor-not-allowed'
                      : isSelected
                      ? 'border-primary-500 bg-primary-50'
                      : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                  )}
                >
                  {multiSelect && (
                    <div
                      className={clsx(
                        'w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0',
                        isSelected ? 'border-primary-500 bg-primary-500' : 'border-gray-300'
                      )}
                      aria-hidden="true"
                    >
                      {isSelected && <CheckIcon className="h-3 w-3 text-white" />}
                    </div>
                  )}
                  {renderItem(item, isSelected)}
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
