import { TextareaHTMLAttributes, useId } from 'react';
import { UseFormRegisterReturn } from 'react-hook-form';
import clsx from 'clsx';

export interface FormTextareaProps extends Omit<TextareaHTMLAttributes<HTMLTextAreaElement>, 'name'> {
  label: string;
  name: string;
  id?: string;
  rows?: number;
  error?: string;
  required?: boolean;
  register?: UseFormRegisterReturn;
  helperText?: string;
  ref?: React.Ref<HTMLTextAreaElement>;
}

export const FormTextarea = ({
  label,
  name,
  id,
  rows = 4,
  placeholder,
  error,
  required = false,
  register,
  helperText,
  className,
  disabled,
  ref,
  ...props
}: FormTextareaProps) => {
  const generatedId = useId();
  const textareaId = id ?? generatedId;
  const hasError = Boolean(error);

  return (
    <div className="w-full">
      <label
        htmlFor={textareaId}
        className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1.5 sm:mb-1"
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
          'focus-visible:outline-none focus-visible:ring-2 sm:focus-visible:ring-1',
          'disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-not-allowed dark:disabled:bg-gray-800 dark:disabled:text-gray-500',
          hasError
            ? 'border-red-300 dark:border-red-600 text-red-900 dark:text-red-300 focus-visible:border-red-500 focus-visible:ring-red-500'
            : 'border-gray-300 dark:border-gray-600 text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-700 focus-visible:border-primary-500 focus-visible:ring-primary-500',
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
          className="mt-1.5 sm:mt-1 text-sm text-red-600 dark:text-red-400 font-medium"
          role="alert"
        >
          {error}
        </p>
      )}
      {!error && helperText && (
        <p id={`${textareaId}-helper`} className="mt-1.5 sm:mt-1 text-sm text-gray-500 dark:text-gray-400">
          {helperText}
        </p>
      )}
    </div>
  );
};
