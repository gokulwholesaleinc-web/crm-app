/**
 * Chat message bubble component
 */

import { format } from 'date-fns';
import clsx from 'clsx';
import { UserIcon, SparklesIcon } from '@heroicons/react/24/outline';
import type { ChatMessage as ChatMessageType } from '../../../types';

interface ChatMessageProps {
  message: ChatMessageType & { id?: string; timestamp?: string };
  showTimestamp?: boolean;
}

export function ChatMessage({ message, showTimestamp = true }: ChatMessageProps) {
  const isUser = message.role === 'user';

  const formatTime = (timestamp: string | undefined) => {
    if (!timestamp) return '';
    try {
      return format(new Date(timestamp), 'h:mm a');
    } catch {
      return '';
    }
  };

  return (
    <div
      className={clsx(
        'flex gap-3 w-full',
        isUser ? 'flex-row-reverse' : 'flex-row'
      )}
    >
      {/* Avatar */}
      <div
        className={clsx(
          'flex-shrink-0 h-8 w-8 rounded-full flex items-center justify-center',
          isUser ? 'bg-primary-100' : 'bg-purple-100'
        )}
      >
        {isUser ? (
          <UserIcon className="h-5 w-5 text-primary-600" />
        ) : (
          <SparklesIcon className="h-5 w-5 text-purple-600" />
        )}
      </div>

      {/* Message Content */}
      <div
        className={clsx('flex flex-col max-w-[80%]', isUser ? 'items-end' : 'items-start')}
      >
        <div
          className={clsx(
            'rounded-2xl px-4 py-2',
            isUser
              ? 'bg-primary-500 text-white rounded-br-sm'
              : 'bg-gray-100 text-gray-900 rounded-bl-sm'
          )}
        >
          <p className="text-sm whitespace-pre-wrap break-words">{message.content}</p>
        </div>

        {showTimestamp && message.timestamp && (
          <span className="text-xs text-gray-400 mt-1 px-1">
            {formatTime(message.timestamp)}
          </span>
        )}
      </div>
    </div>
  );
}

export default ChatMessage;
