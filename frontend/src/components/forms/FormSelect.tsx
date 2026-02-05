import { SelectHTMLAttributes, forwardRef } from 'react';
import { UseFormRegisterReturn } from 'react-hook-form';
import clsx from 'clsx';

export interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
}

export interface FormSelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'name' | 'children'> {
  label: string;
  name: string;
  options: SelectOption[];
  error?: string;
  required?: boolean;
  register?: UseFormRegisterReturn;
  helperText?: string;
  placeholder?: string;
}

export const FormSelect = forwardRef<HTMLSelectElement, FormSelectProps>(
  (
    {
      label,
      name,
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
    ref
  ) => {
    const selectId = name;
    const hasError = Boolean(error);

    return (
      <div className="w-full">
        <label
          htmlFor={selectId}
          className="block text-sm font-medium text-gray-700 mb-1.5 sm:mb-1"
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
            'focus:outline-none focus:ring-2 sm:focus:ring-1',
            'disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-not-allowed',
            hasError
              ? 'border-red-300 text-red-900 focus:border-red-500 focus:ring-red-500'
              : 'border-gray-300 text-gray-900 focus:border-primary-500 focus:ring-primary-500',
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
          <p id={`${selectId}-helper`} className="mt-1.5 sm:mt-1 text-sm text-gray-500">
            {helperText}
          </p>
        )}
      </div>
    );
  }
);

FormSelect.displayName = 'FormSelect';
