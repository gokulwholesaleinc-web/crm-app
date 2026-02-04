import { ReactNode } from 'react';
import clsx from 'clsx';

export interface CardProps {
  children: ReactNode;
  className?: string;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  shadow?: 'none' | 'sm' | 'md' | 'lg';
  hover?: boolean;
}

const paddingStyles = {
  none: '',
  sm: 'p-4',
  md: 'p-6',
  lg: 'p-8',
};

const shadowStyles = {
  none: '',
  sm: 'shadow-sm',
  md: 'shadow-card',
  lg: 'shadow-soft',
};

export function Card({
  children,
  className,
  padding = 'md',
  shadow = 'md',
  hover = false,
}: CardProps) {
  return (
    <div
      className={clsx(
        'bg-white rounded-lg border border-gray-200',
        paddingStyles[padding],
        shadowStyles[shadow],
        hover && 'transition-shadow duration-200 hover:shadow-lg',
        className
      )}
    >
      {children}
    </div>
  );
}

export interface CardHeaderProps {
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}

export function CardHeader({
  title,
  description,
  action,
  className,
}: CardHeaderProps) {
  return (
    <div className={clsx('flex items-start justify-between', className)}>
      <div>
        <h3 className="text-lg font-semibold text-gray-900">{title}</h3>
        {description && (
          <p className="mt-1 text-sm text-gray-500">{description}</p>
        )}
      </div>
      {action && <div className="ml-4 flex-shrink-0">{action}</div>}
    </div>
  );
}

export interface CardBodyProps {
  children: ReactNode;
  className?: string;
}

export function CardBody({ children, className }: CardBodyProps) {
  return <div className={clsx('mt-4', className)}>{children}</div>;
}

export interface CardFooterProps {
  children: ReactNode;
  className?: string;
  border?: boolean;
}

export function CardFooter({
  children,
  className,
  border = true,
}: CardFooterProps) {
  return (
    <div
      className={clsx(
        'mt-4 pt-4',
        border && 'border-t border-gray-200',
        className
      )}
    >
      {children}
    </div>
  );
}
