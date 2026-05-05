import { SelectHTMLAttributes, forwardRef, useId } from 'react';
import { UseFormRegisterReturn } from 'react-hook-form';
import clsx from 'clsx';
import type { SelectOption } from '../ui/Select';

export type { SelectOption };

export interface FormSelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'name' | 'children'> {
  label: string;
  name: string;
  id?: string;
  options: SelectOption[];
  error?: string;
  required?: boolean;
  register?: UseFormRegisterReturn;
  helperText?: string;
  placeholder?: string;
}

// React 18: forwardRef is required so refs spread via {...register()} reach
// the DOM. Remove when migrating to React 19.
export const FormSelect = forwardRef<HTMLSelectElement, FormSelectProps>(function FormSelect(
  {
    label,
    name,
    id,
    options,
    error,
    required = false,
    register,
    helperText,
    placeholder,
    className,
    disabled,
    ...props
  },
  ref,
) {
  const generatedId = useId();
  const selectId = id ?? generatedId;
  const hasError = Boolean(error);

  return (
    <div className="w-full">
      <label
        htmlFor={selectId}
        className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5 sm:mb-1"
      >
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </label>
      <select
        ref={ref}
        id={selectId}
        name={name}
        disabled={disabled}
        className={clsx(
          'block w-full rounded-md shadow-sm text-base sm:text-sm',
          'py-2.5 sm:py-2 px-3', // Better touch targets on mobile
          'focus-visible:outline-none focus-visible:ring-2 sm:focus-visible:ring-1',
          'disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-not-allowed dark:disabled:bg-gray-800 dark:disabled:text-gray-500',
          hasError
            ? 'border-red-300 dark:border-red-600 text-red-900 dark:text-red-300 focus-visible:border-red-500 focus-visible:ring-red-500'
            : 'border-gray-300 dark:border-gray-600 text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700 focus-visible:border-primary-500 focus-visible:ring-primary-500',
          className
        )}
        aria-invalid={hasError}
        aria-describedby={
          hasError ? `${selectId}-error` : helperText ? `${selectId}-helper` : undefined
        }
        {...register}
        {...props}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((option) => (
          <option
            key={option.value}
            value={option.value}
            disabled={option.disabled}
          >
            {option.label}
          </option>
        ))}
      </select>
      {error && (
        <p
          id={`${selectId}-error`}
          className="mt-1.5 sm:mt-1 text-sm text-red-600 font-medium"
          role="alert"
        >
          {error}
        </p>
      )}
      {!error && helperText && (
        <p id={`${selectId}-helper`} className="mt-1.5 sm:mt-1 text-sm text-gray-500 dark:text-gray-400">
          {helperText}
        </p>
      )}
    </div>
  );
});
