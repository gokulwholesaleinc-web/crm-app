import clsx from 'clsx';

interface SkeletonProps {
  className?: string;
  width?: string;
  height?: string;
}

export function Skeleton({ className, width, height }: SkeletonProps) {
  return (
    <div
      className={clsx('animate-pulse rounded bg-gray-200 dark:bg-gray-700', className)}
      style={{ width, height }}
      aria-hidden="true"
    />
  );
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={clsx('space-y-3', className)} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className={clsx(
            'h-4 animate-pulse rounded bg-gray-200 dark:bg-gray-700',
            i === lines - 1 && 'w-3/4'
          )}
        />
      ))}
    </div>
  );
}

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div
      className={clsx(
        'rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-6',
        className
      )}
      aria-hidden="true"
    >
      <div className="flex items-center justify-between">
        <div className="space-y-2 flex-1">
          <div className="h-4 w-24 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
          <div className="h-8 w-32 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
        </div>
        <div className="h-12 w-12 animate-pulse rounded-lg bg-gray-200 dark:bg-gray-700" />
      </div>
    </div>
  );
}

export function SkeletonTable({ rows = 5, cols = 5, className }: { rows?: number; cols?: number; className?: string }) {
  return (
    <div className={clsx('overflow-hidden', className)} aria-hidden="true">
      <div className="flex gap-4 px-6 py-3 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        {Array.from({ length: cols }).map((_, i) => (
          <div key={i} className="h-4 flex-1 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
        ))}
      </div>
      {Array.from({ length: rows }).map((_, rowIdx) => (
        <div
          key={rowIdx}
          className="flex gap-4 px-6 py-4 border-b border-gray-200 dark:border-gray-700"
        >
          {Array.from({ length: cols }).map((_, colIdx) => (
            <div
              key={colIdx}
              className={clsx(
                'h-4 flex-1 animate-pulse rounded bg-gray-200 dark:bg-gray-700',
                colIdx === 0 && 'w-40',
                colIdx === cols - 1 && 'w-20'
              )}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonChart({ className }: { className?: string }) {
  return (
    <div
      className={clsx(
        'rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800',
        className
      )}
      aria-hidden="true"
    >
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
        <div className="h-5 w-40 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
        <div className="mt-1 h-4 w-56 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
      </div>
      <div className="p-6 space-y-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4">
            <div className="h-4 w-24 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
            <div className="flex-1 h-4 animate-pulse rounded-full bg-gray-200 dark:bg-gray-700" />
            <div className="h-4 w-12 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function SkeletonKanban({ columns = 4, className }: { columns?: number; className?: string }) {
  return (
    <div className={clsx('flex gap-4 overflow-x-auto', className)} aria-hidden="true">
      {Array.from({ length: columns }).map((_, colIdx) => (
        <div
          key={colIdx}
          className="flex-shrink-0 w-72 rounded-lg bg-gray-100 dark:bg-gray-800 p-3"
        >
          <div className="h-5 w-28 mb-3 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
          {Array.from({ length: 3 - colIdx % 2 }).map((_, cardIdx) => (
            <div
              key={cardIdx}
              className="mb-2 rounded-lg bg-white dark:bg-gray-700 p-3 shadow-sm space-y-2"
            >
              <div className="h-4 w-3/4 animate-pulse rounded bg-gray-200 dark:bg-gray-600" />
              <div className="h-3 w-1/2 animate-pulse rounded bg-gray-200 dark:bg-gray-600" />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export function SkeletonDetailPage({ className }: { className?: string }) {
  return (
    <div className={clsx('space-y-6', className)} aria-hidden="true">
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <div className="h-8 w-64 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
          <div className="h-4 w-40 animate-pulse rounded bg-gray-200 dark:bg-gray-700" />
        </div>
        <div className="flex gap-2">
          <div className="h-10 w-24 animate-pulse rounded-lg bg-gray-200 dark:bg-gray-700" />
          <div className="h-10 w-24 animate-pulse rounded-lg bg-gray-200 dark:bg-gray-700" />
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <SkeletonCard />
          <SkeletonCard />
        </div>
        <div className="space-y-6">
          <SkeletonCard />
        </div>
      </div>
    </div>
  );
}
