import { useState, useMemo } from 'react';
import { Combobox } from '@headlessui/react';
import { ChevronUpDownIcon, CheckIcon } from '@heroicons/react/20/solid';
import clsx from 'clsx';

export interface SearchableSelectOption {
  value: number;
  label: string;
}

export interface SearchableSelectProps {
  label?: string;
  id?: string;
  value: number | null;
  onChange: (value: number | null) => void;
  options: SearchableSelectOption[];
  placeholder?: string;
  name?: string;
}

function matchesSearch(text: string, query: string): boolean {
  const tokens = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (tokens.length === 0) return true;
  const target = text.toLowerCase();
  return tokens.every((token) => target.includes(token));
}

export function SearchableSelect({
  label,
  id,
  value,
  onChange,
  options,
  placeholder = 'Search...',
  name,
}: SearchableSelectProps) {
  const [query, setQuery] = useState('');

  const selectedOption = useMemo(
    () => options.find((o) => o.value === value) ?? null,
    [options, value]
  );

  const filteredOptions = useMemo(
    () => (query === '' ? options : options.filter((o) => matchesSearch(o.label, query))),
    [options, query]
  );

  const comboboxId = id || label?.toLowerCase().replace(/\s+/g, '-');

  return (
    <div className="w-full">
      <Combobox
        value={selectedOption}
        onChange={(opt: SearchableSelectOption | null) => {
          onChange(opt?.value ?? null);
          setQuery('');
        }}
        nullable
        name={name}
      >
        {label && (
          <Combobox.Label
            htmlFor={comboboxId}
            className="block text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            {label}
          </Combobox.Label>
        )}
        <div className="relative mt-1">
          <Combobox.Input
            id={comboboxId}
            autoComplete="off"
            className={clsx(
              'block w-full rounded-md border shadow-sm sm:text-sm',
              'border-gray-300 dark:border-gray-600',
              'bg-white dark:bg-gray-700',
              'text-gray-900 dark:text-gray-100',
              'placeholder:text-gray-400 dark:placeholder:text-gray-500',
              'focus-visible:border-primary-500 focus-visible:ring-1 focus-visible:ring-primary-500',
              'pr-10 py-2 pl-3'
            )}
            displayValue={(opt: SearchableSelectOption | null) => opt?.label ?? ''}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={placeholder}
          />
          <Combobox.Button
            className="absolute inset-y-0 right-0 flex items-center pr-2"
            aria-label={`Toggle ${label ?? 'options'} list`}
          >
            <ChevronUpDownIcon className="h-5 w-5 text-gray-400" aria-hidden="true" />
          </Combobox.Button>

          <Combobox.Options
            className={clsx(
              'absolute z-20 mt-1 max-h-60 w-full overflow-auto rounded-md py-1 text-sm shadow-lg',
              'bg-white dark:bg-gray-800',
              'border border-gray-200 dark:border-gray-700',
              'focus-visible:outline-none'
            )}
          >
            <Combobox.Option
              value={null}
              className={({ active }) =>
                clsx(
                  'relative cursor-default select-none py-2 pl-10 pr-4',
                  active
                    ? 'bg-primary-600 text-white'
                    : 'text-gray-500 dark:text-gray-400'
                )
              }
            >
              -- None --
            </Combobox.Option>
            {filteredOptions.map((option) => (
              <Combobox.Option
                key={option.value}
                value={option}
                className={({ active }) =>
                  clsx(
                    'relative cursor-default select-none py-2 pl-10 pr-4',
                    active
                      ? 'bg-primary-600 text-white'
                      : 'text-gray-900 dark:text-gray-100'
                  )
                }
              >
                {({ selected, active }) => (
                  <>
                    <span className={clsx('block truncate', selected ? 'font-semibold' : 'font-normal')}>
                      {option.label}
                    </span>
                    {selected && (
                      <span
                        className={clsx(
                          'absolute inset-y-0 left-0 flex items-center pl-3',
                          active ? 'text-white' : 'text-primary-600 dark:text-primary-400'
                        )}
                      >
                        <CheckIcon className="h-5 w-5" aria-hidden="true" />
                      </span>
                    )}
                  </>
                )}
              </Combobox.Option>
            ))}
            {filteredOptions.length === 0 && query !== '' && (
              <div className="relative cursor-default select-none py-2 px-4 text-gray-500 dark:text-gray-400">
                No results found.
              </div>
            )}
          </Combobox.Options>
        </div>
      </Combobox>
    </div>
  );
}
