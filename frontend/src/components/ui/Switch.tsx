import { useId } from 'react';
import clsx from 'clsx';

export type SwitchSize = 'sm' | 'md';

export interface SwitchProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  /** Visible, clickable label rendered beside the switch. */
  label?: React.ReactNode;
  /** Secondary helper text rendered under the label. */
  description?: React.ReactNode;
  disabled?: boolean;
  id?: string;
  size?: SwitchSize;
  className?: string;
  /** Used when there is no visible `label` (icon-only / standalone switch). */
  'aria-label'?: string;
}

// Track/thumb geometry per size, with a 2px inset on both ends so the thumb
// never touches the track edge. The "on" translate = track − thumb − 2×inset.
const sizeStyles: Record<SwitchSize, { track: string; thumb: string; on: string }> = {
  sm: { track: 'h-4 w-7', thumb: 'h-3 w-3', on: 'translate-x-[0.875rem]' },
  md: { track: 'h-5 w-9', thumb: 'h-4 w-4', on: 'translate-x-[1.125rem]' },
};

/**
 * Accessible on/off switch — a native `<button role="switch">` so keyboard
 * (Enter/Space) and focus work for free. Brand-coloured when on, animated thumb,
 * and reduced-motion safe (only `transform`/`background-color` transition).
 *
 * Replaces raw `<input type="checkbox">`, which renders as an unstyled browser
 * box here because the project doesn't load `@tailwindcss/forms`.
 */
export function Switch({
  checked,
  onChange,
  label,
  description,
  disabled = false,
  id,
  size = 'md',
  className,
  'aria-label': ariaLabel,
}: SwitchProps) {
  const s = sizeStyles[size];
  const labelId = useId();
  const toggle = () => {
    if (!disabled) onChange(!checked);
  };

  const control = (
    <button
      type="button"
      role="switch"
      id={id}
      aria-checked={checked}
      // Associate the visible label so the switch has an accessible name;
      // fall back to aria-label only when there is no visible label.
      aria-labelledby={label ? labelId : undefined}
      aria-label={label ? undefined : ariaLabel}
      disabled={disabled}
      onClick={toggle}
      className={clsx(
        'relative inline-flex flex-shrink-0 cursor-pointer items-center rounded-full',
        'transition-colors duration-200 ease-in-out motion-reduce:transition-none',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2',
        'focus-visible:ring-offset-white dark:focus-visible:ring-offset-gray-900',
        'disabled:cursor-not-allowed disabled:opacity-50',
        s.track,
        checked ? 'bg-primary-600' : 'bg-gray-300 dark:bg-gray-600',
      )}
    >
      <span
        aria-hidden="true"
        className={clsx(
          'pointer-events-none inline-block transform rounded-full bg-white shadow-sm ring-0',
          'transition-transform duration-200 ease-in-out motion-reduce:transition-none',
          s.thumb,
          checked ? s.on : 'translate-x-0.5',
        )}
      />
    </button>
  );

  if (!label && !description) {
    return <span className={className}>{control}</span>;
  }

  return (
    <span className={clsx('inline-flex items-center gap-2.5', className)}>
      {control}
      <span className="flex flex-col">
        {label && (
          <span
            id={labelId}
            onClick={toggle}
            className={clsx(
              'select-none text-sm font-medium text-gray-700 dark:text-gray-300',
              disabled ? 'cursor-not-allowed' : 'cursor-pointer',
            )}
          >
            {label}
          </span>
        )}
        {description && (
          <span className="text-xs text-gray-500 dark:text-gray-400">{description}</span>
        )}
      </span>
    </span>
  );
}
