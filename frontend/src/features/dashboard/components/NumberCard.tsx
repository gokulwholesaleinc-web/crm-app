import clsx from 'clsx';

export interface NumberCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: React.ReactNode;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  className?: string;
}

export function NumberCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  className,
}: NumberCardProps) {
  return (
    <div
      className={clsx(
        'bg-white rounded-lg shadow p-6 border border-gray-200',
        className
      )}
    >
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-500 truncate">{title}</p>
          <div className="mt-2 flex items-baseline">
            <p className="text-2xl font-semibold text-gray-900">{value}</p>
            {trend && (
              <span
                className={clsx(
                  'ml-2 text-sm font-medium',
                  trend.isPositive ? 'text-green-600' : 'text-red-600'
                )}
              >
                {trend.isPositive ? '+' : ''}
                {trend.value}%
              </span>
            )}
          </div>
          {subtitle && (
            <p className="mt-1 text-sm text-gray-500">{subtitle}</p>
          )}
        </div>
        {icon && (
          <div className="flex-shrink-0 p-3 bg-primary-50 rounded-lg">
            <span className="h-6 w-6 text-primary-600">{icon}</span>
          </div>
        )}
      </div>
    </div>
  );
}
