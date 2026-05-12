import clsx from 'clsx';

const STATUS_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  draft: { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-700 dark:text-gray-300', dot: 'bg-gray-400' },
  sent: { bg: 'bg-blue-100 dark:bg-blue-900/30', text: 'text-blue-700 dark:text-blue-300', dot: 'bg-blue-500' },
  signed: { bg: 'bg-purple-100 dark:bg-purple-900/30', text: 'text-purple-700 dark:text-purple-300', dot: 'bg-purple-500' },
  active: { bg: 'bg-green-100 dark:bg-green-900/30', text: 'text-green-700 dark:text-green-300', dot: 'bg-green-500' },
  expired: { bg: 'bg-yellow-100 dark:bg-yellow-900/30', text: 'text-yellow-700 dark:text-yellow-300', dot: 'bg-yellow-500' },
  terminated: { bg: 'bg-red-100 dark:bg-red-900/30', text: 'text-red-700 dark:text-red-300', dot: 'bg-red-500' },
};

const DEFAULT_COLOR = { bg: 'bg-gray-100 dark:bg-gray-700', text: 'text-gray-700 dark:text-gray-300', dot: 'bg-gray-400' };

interface ContractStatusBadgeProps {
  status: string;
  size?: 'sm' | 'md';
  showDot?: boolean;
}

export function ContractStatusBadge({ status, size = 'md', showDot = false }: ContractStatusBadgeProps) {
  const colors = STATUS_COLORS[status] ?? DEFAULT_COLOR;
  return (
    <span
      className={clsx(
        'inline-flex items-center rounded-full font-medium capitalize',
        size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-0.5 text-xs',
        colors.bg,
        colors.text,
      )}
    >
      {showDot && (
        <span
          className={clsx('mr-1.5 h-1.5 w-1.5 rounded-full flex-shrink-0', colors.dot)}
          aria-hidden="true"
        />
      )}
      {status}
    </span>
  );
}
