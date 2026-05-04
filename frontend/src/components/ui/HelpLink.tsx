/**
 * Inline help link to a /help anchor. Drop next to a feature's primary action
 * so the relevant tutorial is one click away. Opens in a new tab.
 */

import clsx from 'clsx';
import { QuestionMarkCircleIcon } from '@heroicons/react/24/outline';

interface HelpLinkProps {
  anchor: string;
  label?: string;
  text?: string;
  className?: string;
}

export function HelpLink({ anchor, label = 'How does this work?', text, className }: HelpLinkProps) {
  // Always announce the new-tab behavior to screen readers (WCAG G201). The
  // hover tooltip stays as the bare label so it's not noisy for sighted users.
  const accessibleName = `${label} (opens in new tab)`;
  return (
    <a
      href={`/help#${anchor}`}
      target="_blank"
      rel="noopener noreferrer"
      title={label}
      aria-label={accessibleName}
      className={clsx(
        'inline-flex items-center gap-1 text-xs text-gray-500 hover:text-primary-600 dark:text-gray-400 dark:hover:text-primary-300',
        className,
      )}
    >
      <QuestionMarkCircleIcon className="h-4 w-4" aria-hidden="true" />
      {text && <span>{text}</span>}
    </a>
  );
}
