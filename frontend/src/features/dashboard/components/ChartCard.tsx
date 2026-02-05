import clsx from 'clsx';

export interface ChartCardProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}

export function ChartCard({
  title,
  subtitle,
  children,
  actions,
  className,
}: ChartCardProps) {
  return (
    <div
      className={clsx(
        'bg-white rounded-lg shadow border border-gray-200',
        className
      )}
    >
      <div className="px-4 sm:px-6 py-3 sm:py-4 border-b border-gray-200">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base sm:text-lg font-medium text-gray-900">{title}</h3>
            {subtitle && (
              <p className="mt-0.5 sm:mt-1 text-xs sm:text-sm text-gray-500">{subtitle}</p>
            )}
          </div>
          {actions && <div className="flex items-center space-x-2">{actions}</div>}
        </div>
      </div>
      <div className="p-4 sm:p-6">{children}</div>
    </div>
  );
}
