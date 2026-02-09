import clsx from 'clsx';

export type BadgeVariant =
  | 'gray'
  | 'red'
  | 'yellow'
  | 'green'
  | 'blue'
  | 'indigo'
  | 'purple'
  | 'pink';

export type BadgeSize = 'sm' | 'md' | 'lg';

export interface BadgeProps {
  variant?: BadgeVariant;
  size?: BadgeSize;
  children: React.ReactNode;
  dot?: boolean;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  gray: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300',
  red: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
  yellow: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
  green: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  blue: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  indigo: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300',
  purple: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
  pink: 'bg-pink-100 text-pink-800 dark:bg-pink-900/30 dark:text-pink-300',
};

const dotStyles: Record<BadgeVariant, string> = {
  gray: 'bg-gray-400',
  red: 'bg-red-400',
  yellow: 'bg-yellow-400',
  green: 'bg-green-400',
  blue: 'bg-blue-400',
  indigo: 'bg-indigo-400',
  purple: 'bg-purple-400',
  pink: 'bg-pink-400',
};

const sizeStyles: Record<BadgeSize, string> = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-2.5 py-0.5 text-sm',
  lg: 'px-3 py-1 text-sm',
};

export function Badge({
  variant = 'gray',
  size = 'md',
  children,
  dot = false,
  className,
}: BadgeProps) {
  return (
    <span
      className={clsx(
        'inline-flex items-center font-medium rounded-full',
        variantStyles[variant],
        sizeStyles[size],
        className
      )}
    >
      {dot && (
        <span
          className={clsx(
            'mr-1.5 h-1.5 w-1.5 rounded-full',
            dotStyles[variant]
          )}
          aria-hidden="true"
        />
      )}
      {children}
    </span>
  );
}

// Pre-configured status badges for common CRM use cases
export type StatusType =
  | 'new'
  | 'open'
  | 'in_progress'
  | 'qualified'
  | 'converted'
  | 'closed_won'
  | 'closed_lost'
  | 'pending'
  | 'completed'
  | 'cancelled';

const statusConfig: Record<StatusType, { variant: BadgeVariant; label: string }> = {
  new: { variant: 'blue', label: 'New' },
  open: { variant: 'blue', label: 'Open' },
  in_progress: { variant: 'yellow', label: 'In Progress' },
  qualified: { variant: 'indigo', label: 'Qualified' },
  converted: { variant: 'green', label: 'Converted' },
  closed_won: { variant: 'green', label: 'Closed Won' },
  closed_lost: { variant: 'red', label: 'Closed Lost' },
  pending: { variant: 'yellow', label: 'Pending' },
  completed: { variant: 'green', label: 'Completed' },
  cancelled: { variant: 'gray', label: 'Cancelled' },
};

export interface StatusBadgeProps {
  status: StatusType;
  size?: BadgeSize;
  showDot?: boolean;
  className?: string;
}

export function StatusBadge({
  status,
  size = 'md',
  showDot = true,
  className,
}: StatusBadgeProps) {
  const config = statusConfig[status];

  return (
    <Badge
      variant={config.variant}
      size={size}
      dot={showDot}
      className={className}
    >
      {config.label}
    </Badge>
  );
}
