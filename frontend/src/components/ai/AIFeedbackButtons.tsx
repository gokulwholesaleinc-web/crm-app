/**
 * Thumbs up/down feedback buttons for AI responses.
 */

import { useState } from 'react';
import { HandThumbUpIcon, HandThumbDownIcon } from '@heroicons/react/24/outline';
import {
  HandThumbUpIcon as HandThumbUpSolid,
  HandThumbDownIcon as HandThumbDownSolid,
} from '@heroicons/react/24/solid';
import clsx from 'clsx';
import { useFeedback } from '../../hooks/useAI';

interface AIFeedbackButtonsProps {
  query: string;
  response: string;
  sessionId?: string | null;
  size?: 'sm' | 'md';
}

export function AIFeedbackButtons({
  query,
  response,
  sessionId,
  size = 'sm',
}: AIFeedbackButtonsProps) {
  const [submitted, setSubmitted] = useState<'positive' | 'negative' | null>(null);
  const feedbackMutation = useFeedback();

  const handleFeedback = async (type: 'positive' | 'negative') => {
    if (submitted) return;
    setSubmitted(type);
    try {
      await feedbackMutation.mutateAsync({
        query,
        response,
        session_id: sessionId,
        feedback: type,
      });
    } catch {
      // Silently fail - feedback is non-critical
      setSubmitted(null);
    }
  };

  const iconClass = size === 'sm' ? 'h-3.5 w-3.5' : 'h-4 w-4';
  const buttonClass = size === 'sm' ? 'p-1' : 'p-1.5';

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => handleFeedback('positive')}
        disabled={submitted !== null}
        className={clsx(
          buttonClass,
          'rounded transition-colors',
          submitted === 'positive'
            ? 'text-green-600'
            : submitted === null
              ? 'text-gray-400 hover:text-green-600 hover:bg-green-50'
              : 'text-gray-300 cursor-default'
        )}
        aria-label="Helpful"
        title="Helpful"
      >
        {submitted === 'positive' ? (
          <HandThumbUpSolid className={iconClass} />
        ) : (
          <HandThumbUpIcon className={iconClass} />
        )}
      </button>
      <button
        onClick={() => handleFeedback('negative')}
        disabled={submitted !== null}
        className={clsx(
          buttonClass,
          'rounded transition-colors',
          submitted === 'negative'
            ? 'text-red-600'
            : submitted === null
              ? 'text-gray-400 hover:text-red-600 hover:bg-red-50'
              : 'text-gray-300 cursor-default'
        )}
        aria-label="Not helpful"
        title="Not helpful"
      >
        {submitted === 'negative' ? (
          <HandThumbDownSolid className={iconClass} />
        ) : (
          <HandThumbDownIcon className={iconClass} />
        )}
      </button>
    </div>
  );
}
