import { InputHTMLAttributes, forwardRef } from 'react';
import { UseFormRegisterReturn } from 'react-hook-form';
import clsx from 'clsx';

export interface FormInputProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'name'> {
  label: string;
  name: string;
  error?: string;
  required?: boolean;
  register?: UseFormRegisterReturn;
  helperText?: string;
}

export const FormInput = forwardRef<HTMLInputElement, FormInputProps>(
  (
    {
      label,
      name,
      type = 'text',
      placeholder,
      error,
      required = false,
      register,
      helperText,
      className,
      disabled,
      ...props
    },
    ref
  ) => {
    const inputId = name;
    const hasError = Boolean(error);

    return (
      <div className="w-full">
        <label
          htmlFor={inputId}
          className="block text-sm font-medium text-gray-700"
        >
          {label}
          {required && ' *'}
        </label>
        <input
          ref={ref}
          type={type}
          id={inputId}
          name={name}
          placeholder={placeholder}
          disabled={disabled}
          className={clsx(
            'mt-1 block w-full rounded-md shadow-sm sm:text-sm',
            'focus:outline-none focus:ring-1',
            'disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-not-allowed',
            hasError
              ? 'border-red-300 text-red-900 focus:border-red-500 focus:ring-red-500'
              : 'border-gray-300 text-gray-900 focus:border-primary-500 focus:ring-primary-500',
            className
          )}
          aria-invalid={hasError}
          aria-describedby={
            hasError ? `${inputId}-error` : helperText ? `${inputId}-helper` : undefined
          }
          {...register}
          {...props}
        />
        {error && (
          <p
            id={`${inputId}-error`}
            className="mt-1 text-sm text-red-600"
            role="alert"
          >
            {error}
          </p>
        )}
        {!error && helperText && (
          <p id={`${inputId}-helper`} className="mt-1 text-sm text-gray-500">
            {helperText}
          </p>
        )}
      </div>
    );
  }
);

FormInput.displayName = 'FormInput';
