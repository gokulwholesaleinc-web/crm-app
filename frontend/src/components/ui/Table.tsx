import { ReactNode } from 'react';
import clsx from 'clsx';
import {
  ChevronUpIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from '@heroicons/react/20/solid';

export type SortDirection = 'asc' | 'desc' | null;

export interface Column<T> {
  key: string;
  header: string;
  sortable?: boolean;
  render?: (row: T) => ReactNode;
  className?: string;
  headerClassName?: string;
}

export interface TableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (row: T) => string | number;
  sortColumn?: string;
  sortDirection?: SortDirection;
  onSort?: (column: string) => void;
  isLoading?: boolean;
  emptyMessage?: string;
  className?: string;
}

export interface PaginationProps {
  currentPage: number;
  totalPages: number;
  totalItems: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  className?: string;
}

export function Table<T>({
  columns,
  data,
  keyExtractor,
  sortColumn,
  sortDirection,
  onSort,
  isLoading = false,
  emptyMessage = 'No data available',
  className,
}: TableProps<T>) {
  const renderSortIcon = (column: Column<T>) => {
    if (!column.sortable) return null;

    const isActive = sortColumn === column.key;

    return (
      <span className="ml-2 flex-none">
        {isActive && sortDirection === 'asc' ? (
          <ChevronUpIcon className="h-4 w-4 text-primary-500" />
        ) : isActive && sortDirection === 'desc' ? (
          <ChevronDownIcon className="h-4 w-4 text-primary-500" />
        ) : (
          <ChevronUpIcon className="h-4 w-4 text-gray-300 group-hover:text-gray-400" />
        )}
      </span>
    );
  };

  return (
    <div className={clsx('overflow-hidden shadow ring-1 ring-black ring-opacity-5 rounded-lg', className)}>
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={clsx(
                    'px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider',
                    column.sortable && 'cursor-pointer select-none group hover:bg-gray-100',
                    column.headerClassName
                  )}
                  onClick={
                    column.sortable && onSort
                      ? () => onSort(column.key)
                      : undefined
                  }
                >
                  <div className="flex items-center">
                    {column.header}
                    {renderSortIcon(column)}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {isLoading ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-6 py-12 text-center text-sm text-gray-500"
                >
                  <div className="flex items-center justify-center">
                    <svg
                      className="animate-spin h-5 w-5 text-primary-500 mr-3"
                      xmlns="http://www.w3.org/2000/svg"
                      fill="none"
                      viewBox="0 0 24 24"
                    >
                      <circle
                        className="opacity-25"
                        cx="12"
                        cy="12"
                        r="10"
                        stroke="currentColor"
                        strokeWidth="4"
                      />
                      <path
                        className="opacity-75"
                        fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                      />
                    </svg>
                    Loading...
                  </div>
                </td>
              </tr>
            ) : data.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length}
                  className="px-6 py-12 text-center text-sm text-gray-500"
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              data.map((row) => (
                <tr key={keyExtractor(row)} className="hover:bg-gray-50 transition-colors">
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className={clsx(
                        'px-6 py-4 whitespace-nowrap text-sm text-gray-900',
                        column.className
                      )}
                    >
                      {column.render
                        ? column.render(row)
                        : (row as Record<string, unknown>)[column.key] as ReactNode}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function Pagination({
  currentPage,
  totalPages,
  totalItems,
  pageSize,
  onPageChange,
  className,
}: PaginationProps) {
  const startItem = (currentPage - 1) * pageSize + 1;
  const endItem = Math.min(currentPage * pageSize, totalItems);

  const canGoPrevious = currentPage > 1;
  const canGoNext = currentPage < totalPages;

  return (
    <div
      className={clsx(
        'flex items-center justify-between px-4 py-3 bg-white border-t border-gray-200',
        className
      )}
    >
      <div className="flex-1 flex justify-between sm:hidden">
        <button
          onClick={() => onPageChange(currentPage - 1)}
          disabled={!canGoPrevious}
          className={clsx(
            'relative inline-flex items-center px-4 py-2 text-sm font-medium rounded-md',
            canGoPrevious
              ? 'text-gray-700 bg-white hover:bg-gray-50 border border-gray-300'
              : 'text-gray-400 bg-gray-100 cursor-not-allowed'
          )}
        >
          Previous
        </button>
        <button
          onClick={() => onPageChange(currentPage + 1)}
          disabled={!canGoNext}
          className={clsx(
            'relative inline-flex items-center px-4 py-2 ml-3 text-sm font-medium rounded-md',
            canGoNext
              ? 'text-gray-700 bg-white hover:bg-gray-50 border border-gray-300'
              : 'text-gray-400 bg-gray-100 cursor-not-allowed'
          )}
        >
          Next
        </button>
      </div>
      <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
        <div>
          <p className="text-sm text-gray-700">
            Showing <span className="font-medium">{startItem}</span> to{' '}
            <span className="font-medium">{endItem}</span> of{' '}
            <span className="font-medium">{totalItems}</span> results
          </p>
        </div>
        <div>
          <nav
            className="relative z-0 inline-flex rounded-md shadow-sm -space-x-px"
            aria-label="Pagination"
          >
            <button
              onClick={() => onPageChange(currentPage - 1)}
              disabled={!canGoPrevious}
              className={clsx(
                'relative inline-flex items-center px-2 py-2 rounded-l-md border border-gray-300 bg-white text-sm font-medium',
                canGoPrevious
                  ? 'text-gray-500 hover:bg-gray-50'
                  : 'text-gray-300 cursor-not-allowed'
              )}
            >
              <span className="sr-only">Previous</span>
              <ChevronLeftIcon className="h-5 w-5" aria-hidden="true" />
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter((page) => {
                if (totalPages <= 7) return true;
                if (page === 1 || page === totalPages) return true;
                if (Math.abs(page - currentPage) <= 1) return true;
                return false;
              })
              .map((page, index, array) => {
                const showEllipsis =
                  index > 0 && page - array[index - 1] > 1;

                return (
                  <Fragment key={page}>
                    {showEllipsis && (
                      <span className="relative inline-flex items-center px-4 py-2 border border-gray-300 bg-white text-sm font-medium text-gray-700">
                        ...
                      </span>
                    )}
                    <button
                      onClick={() => onPageChange(page)}
                      className={clsx(
                        'relative inline-flex items-center px-4 py-2 border text-sm font-medium',
                        page === currentPage
                          ? 'z-10 bg-primary-50 border-primary-500 text-primary-600'
                          : 'bg-white border-gray-300 text-gray-500 hover:bg-gray-50'
                      )}
                    >
                      {page}
                    </button>
                  </Fragment>
                );
              })}
            <button
              onClick={() => onPageChange(currentPage + 1)}
              disabled={!canGoNext}
              className={clsx(
                'relative inline-flex items-center px-2 py-2 rounded-r-md border border-gray-300 bg-white text-sm font-medium',
                canGoNext
                  ? 'text-gray-500 hover:bg-gray-50'
                  : 'text-gray-300 cursor-not-allowed'
              )}
            >
              <span className="sr-only">Next</span>
              <ChevronRightIcon className="h-5 w-5" aria-hidden="true" />
            </button>
          </nav>
        </div>
      </div>
    </div>
  );
}

function Fragment({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
