import { useState, useEffect, useRef } from 'react';
import clsx from 'clsx';
import { ClipboardIcon, CheckIcon } from '@heroicons/react/24/outline';
import { showError } from '../../utils/toast';

interface CopyButtonProps {
  value: string;
  label?: string;
  className?: string;
}

export function CopyButton({ value, label = 'Copy', className }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
  }, []);

  const handleClick = async () => {
    if (!navigator.clipboard?.writeText) {
      showError('Clipboard unavailable in this browser');
      return;
    }
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
      timeoutRef.current = setTimeout(() => setCopied(false), 1500);
    } catch {
      showError(`Could not copy ${label.toLowerCase()}`);
    }
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-label={`Copy ${label}`}
      className={clsx(
        'inline-flex items-center text-gray-400 hover:text-primary-600 dark:hover:text-primary-300 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500',
        className,
      )}
    >
      {copied ? (
        <CheckIcon className="h-4 w-4 text-green-500" aria-hidden="true" />
      ) : (
        <ClipboardIcon className="h-4 w-4" aria-hidden="true" />
      )}
    </button>
  );
}
