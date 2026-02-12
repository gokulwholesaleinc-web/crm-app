import { TextareaHTMLAttributes, forwardRef } from 'react';
import { UseFormRegisterReturn } from 'react-hook-form';
import clsx from 'clsx';

export interface FormTextareaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'name'> {
  label: string;
  name: string;
  rows?: number;
  error?: string;
  required?: boolean;
  register?: UseFormRegisterReturn;
  helperText?: string;
}

export const FormTextarea = forwardRef<HTMLTextAreaElement, FormTextareaProps>(
  (
    {
      label,
      name,
      rows = 4,
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
    const textareaId = name;
    const hasError = Boolean(error);

    return (
      <div className="w-full">
        <label
          htmlFor={textareaId}
          className="block text-sm font-medium text-gray-700 mb-1.5 sm:mb-1"
        >
          {label}
          {required && <span className="text-red-500 ml-0.5">*</span>}
        </label>
        <textarea
          ref={ref}
          id={textareaId}
          name={name}
          rows={rows}
          placeholder={placeholder}
          disabled={disabled}
          className={clsx(
            'block w-full rounded-md shadow-sm text-base sm:text-sm',
            'py-2.5 sm:py-2 px-3', // Better touch targets on mobile
            'focus-visible:outline-none focus:ring-2 sm:focus:ring-1',
            'disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-not-allowed',
            hasError
              ? 'border-red-300 text-red-900 focus:border-red-500 focus:ring-red-500'
              : 'border-gray-300 text-gray-900 focus:border-primary-500 focus:ring-primary-500',
            className
          )}
          aria-invalid={hasError}
          aria-describedby={
            hasError ? `${textareaId}-error` : helperText ? `${textareaId}-helper` : undefined
          }
          {...register}
          {...props}
        />
        {error && (
          <p
            id={`${textareaId}-error`}
            className="mt-1.5 sm:mt-1 text-sm text-red-600 font-medium"
            role="alert"
          >
            {error}
          </p>
        )}
        {!error && helperText && (
          <p id={`${textareaId}-helper`} className="mt-1.5 sm:mt-1 text-sm text-gray-500">
            {helperText}
          </p>
        )}
      </div>
    );
  }
);

FormTextarea.displayName = 'FormTextarea';
