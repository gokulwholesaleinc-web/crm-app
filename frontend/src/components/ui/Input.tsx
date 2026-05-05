import { InputHTMLAttributes, forwardRef, useId } from 'react';
import clsx from 'clsx';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

// `forwardRef` is required on React 18: a ref spread via
// `{...register('field')}` from react-hook-form is intercepted by React
// at the JSX level and never reaches a function component's props. Older
// versions of this file destructured `ref` from props, which silently
// dropped the ref — react-hook-form then couldn't read the field's value
// and every <Input> + register pair reported "field is required" no
// matter what the user typed. Keep this as forwardRef until the codebase
// migrates to React 19 (where ref-as-prop becomes the supported path).
export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  {
    label,
    error,
    helperText,
    leftIcon,
    rightIcon,
    className,
    id,
    disabled,
    ...props
  },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const hasError = Boolean(error);

  return (
    <div className="w-full">
      {label && (
        <label
          htmlFor={inputId}
          className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
        >
          {label}
        </label>
      )}
      <div className="relative">
        {leftIcon && (
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <span className="h-5 w-5 text-gray-400">{leftIcon}</span>
          </div>
        )}
        <input
          ref={ref}
          id={inputId}
          disabled={disabled}
          className={clsx(
            'block w-full rounded-lg border shadow-sm transition-colors duration-200',
            'placeholder:text-gray-400 dark:placeholder:text-gray-500',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-0',
            'disabled:bg-gray-50 disabled:text-gray-500 disabled:cursor-not-allowed dark:disabled:bg-gray-800',
            leftIcon ? 'pl-10' : 'pl-3',
            rightIcon ? 'pr-10' : 'pr-3',
            'py-2 text-sm',
            hasError
              ? 'border-red-300 text-red-900 focus-visible:border-red-500 focus-visible:ring-red-500 dark:border-red-600 dark:text-red-400'
              : 'border-gray-300 text-gray-900 focus-visible:border-primary-500 focus-visible:ring-primary-500 dark:border-gray-600 dark:bg-gray-700 dark:text-gray-100',
            className
          )}
          aria-invalid={hasError}
          aria-describedby={
            hasError ? `${inputId}-error` : helperText ? `${inputId}-helper` : undefined
          }
          {...props}
        />
        {rightIcon && (
          <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
            <span className="h-5 w-5 text-gray-400">{rightIcon}</span>
          </div>
        )}
      </div>
      {error && (
        <p
          id={`${inputId}-error`}
          className="mt-1 text-sm text-red-600 dark:text-red-400"
          role="alert"
        >
          {error}
        </p>
      )}
      {!error && helperText && (
        <p id={`${inputId}-helper`} className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {helperText}
        </p>
      )}
    </div>
  );
});
