/**
 * Chat input with send button
 */

import { useState, useRef, useEffect } from 'react';
import clsx from 'clsx';
import { PaperAirplaneIcon } from '@heroicons/react/24/solid';
import { Spinner } from '../../../components/ui/Spinner';

interface ChatInputProps {
  onSend: (message: string) => void;
  isLoading?: boolean;
  placeholder?: string;
  disabled?: boolean;
}

export function ChatInput({
  onSend,
  isLoading = false,
  placeholder = 'Type a message...',
  disabled = false,
}: ChatInputProps) {
  const [message, setMessage] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [message]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (message.trim() && !isLoading && !disabled) {
      onSend(message.trim());
      setMessage('');
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const canSend = message.trim().length > 0 && !isLoading && !disabled;

  return (
    <form onSubmit={handleSubmit} className="flex items-end gap-2">
      <div className="flex-1 relative">
        <textarea
          ref={textareaRef}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          disabled={disabled || isLoading}
          rows={1}
          className={clsx(
            'w-full resize-none rounded-2xl border border-gray-200 px-4 py-3 pr-12',
            'text-sm text-gray-900 placeholder:text-gray-400',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:border-transparent',
            'dark:bg-gray-800 dark:border-gray-700 dark:text-gray-100 dark:placeholder:text-gray-500',
            'disabled:bg-gray-50 dark:disabled:bg-gray-900 disabled:cursor-not-allowed',
            'transition-colors duration-200'
          )}
          style={{ minHeight: '48px', maxHeight: '150px' }}
        />
        <div className="absolute right-2 bottom-2">
          <button
            type="submit"
            disabled={!canSend}
            aria-label="Send message"
            className={clsx(
              'p-2 rounded-full transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2',
              canSend
                ? 'bg-primary-500 text-white hover:bg-primary-600 shadow-sm'
                : 'bg-gray-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed'
            )}
          >
            {isLoading ? (
              <Spinner size="sm" className="h-4 w-4" />
            ) : (
              <PaperAirplaneIcon className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        </div>
      </div>
    </form>
  );
}

export default ChatInput;
