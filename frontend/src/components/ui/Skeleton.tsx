import clsx from 'clsx';

interface SkeletonProps {
  className?: string;
  width?: string;
  height?: string;
}

export function Skeleton({ className, width, height }: SkeletonProps) {
  return (
    <div
      className={clsx(
        'animate-pulse rounded-md bg-gray-200 dark:bg-gray-700',
        className
      )}
      style={{ width, height }}
      aria-hidden="true"
    />
  );
}

export function SkeletonText({
  lines = 3,
  className,
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={clsx('space-y-3', className)} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          className={clsx(
            'h-4',
            i === lines - 1 ? 'w-2/3' : 'w-full'
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
        'bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6',
        className
      )}
      aria-hidden="true"
    >
      <div className="flex items-center justify-between mb-4">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-8 w-8 rounded-lg" />
      </div>
      <Skeleton className="h-8 w-32 mb-2" />
      <Skeleton className="h-3 w-20" />
    </div>
  );
}

export function SkeletonTable({
  rows = 5,
  cols = 5,
  className,
}: {
  rows?: number;
  cols?: number;
  className?: string;
}) {
  return (
    <div
      className={clsx(
        'bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden',
        className
      )}
      aria-hidden="true"
    >
      {/* Header */}
      <div className="bg-gray-50 dark:bg-gray-900 px-6 py-3 flex gap-6">
        {Array.from({ length: cols }).map((_, i) => (
          <Skeleton key={i} className="h-3 flex-1" />
        ))}
      </div>
      {/* Rows */}
      <div className="divide-y divide-gray-200 dark:divide-gray-700">
        {Array.from({ length: rows }).map((_, rowIdx) => (
          <div key={rowIdx} className="px-6 py-4 flex gap-6">
            {Array.from({ length: cols }).map((_, colIdx) => (
              <Skeleton
                key={colIdx}
                className={clsx(
                  'h-4 flex-1',
                  colIdx === 0 ? 'max-w-[200px]' : 'max-w-[120px]'
                )}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function SkeletonChart({ className }: { className?: string }) {
  return (
    <div
      className={clsx(
        'bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700',
        className
      )}
      aria-hidden="true"
    >
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
        <Skeleton className="h-5 w-40 mb-2" />
        <Skeleton className="h-3 w-56" />
      </div>
      <div className="p-6 space-y-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 flex-1 rounded-full" />
            <Skeleton className="h-4 w-12" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function SkeletonKanban({ columns = 5 }: { columns?: number }) {
  return (
    <div className="flex gap-4 overflow-hidden" aria-hidden="true">
      {Array.from({ length: columns }).map((_, colIdx) => (
        <div
          key={colIdx}
          className="flex-shrink-0 w-72 bg-gray-50 dark:bg-gray-900 rounded-lg p-3"
        >
          <div className="flex items-center justify-between mb-3">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-5 w-8 rounded-full" />
          </div>
          <div className="space-y-3">
            {Array.from({ length: 2 + (colIdx % 2) }).map((_, cardIdx) => (
              <div
                key={cardIdx}
                className="bg-white dark:bg-gray-800 rounded-lg p-4 shadow-sm border border-gray-200 dark:border-gray-700"
              >
                <Skeleton className="h-4 w-full mb-2" />
                <Skeleton className="h-3 w-2/3 mb-3" />
                <div className="flex items-center justify-between">
                  <Skeleton className="h-5 w-20" />
                  <Skeleton className="h-3 w-10" />
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export function SkeletonDetailPage() {
  return (
    <div className="space-y-6" aria-hidden="true">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <Skeleton className="h-7 w-48" />
          <Skeleton className="h-4 w-32" />
        </div>
        <div className="flex gap-3">
          <Skeleton className="h-9 w-20 rounded-lg" />
          <Skeleton className="h-9 w-20 rounded-lg" />
        </div>
      </div>
      {/* Content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
            <SkeletonText lines={4} />
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
            <Skeleton className="h-5 w-32 mb-4" />
            <SkeletonText lines={3} />
          </div>
        </div>
        <div className="space-y-6">
          <SkeletonCard />
          <SkeletonCard />
        </div>
      </div>
    </div>
  );
}
