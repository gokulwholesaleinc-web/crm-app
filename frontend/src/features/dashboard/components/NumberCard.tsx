import { Link } from 'react-router-dom';
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
  href?: string;
  className?: string;
}

export function NumberCard({
  title,
  value,
  subtitle,
  icon,
  trend,
  href,
  className,
}: NumberCardProps) {
  const cardContent = (
    <div className="flex items-center justify-between">
      <div className="flex-1 min-w-0">
        <p className="text-xs sm:text-sm font-medium text-gray-500 dark:text-gray-400 truncate">{title}</p>
        <div className="mt-1 sm:mt-2 flex items-baseline flex-wrap">
          <p className="text-xl sm:text-2xl font-semibold text-gray-900 dark:text-gray-100 truncate tabular-nums">{value}</p>
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
        <div className="flex-shrink-0 p-3 bg-primary-50 dark:bg-primary-900/30 rounded-lg">
          <span className="h-6 w-6 text-primary-600">{icon}</span>
        </div>
      )}
    </div>
  );

  const baseClasses = clsx(
    'bg-white dark:bg-gray-800 rounded-lg shadow p-4 sm:p-6 border border-gray-200 dark:border-gray-700',
    href && 'cursor-pointer hover:shadow-md hover:border-primary-300 dark:hover:border-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-gray-900 transition-shadow',
    className
  );

  if (href) {
    return (
      <Link to={href} className={clsx(baseClasses, 'block')} aria-label={`View ${title}`}>
        {cardContent}
      </Link>
    );
  }

  return (
    <div className={baseClasses}>
      {cardContent}
    </div>
  );
}
