import clsx from 'clsx';
import { Button } from '../ui/Button';

export interface ChecklistItem {
  /** Stable key for React. */
  key: string;
  /** Short label, e.g., "Recipient set", "Contact has email". */
  label: string;
  /** true = pass (green check), false = fail (red x), 'optional' = info dot only. */
  state: boolean | 'optional';
  /** Optional helper text shown when failing. */
  hint?: string;
  /** Optional action to remediate (deep-link to the right edit field). */
  action?: { label: string; onClick: () => void };
}

export interface SendChecklistProps {
  /** Title above the list. Defaults to "Ready to send". */
  title?: string;
  items: ChecklistItem[];
  /**
   * When true, the entire checklist is hidden once every required item passes.
   * Prevents cluttering the page after all gates are cleared.
   */
  hideWhenAllGreen?: boolean;
  className?: string;
}

/** Returns true iff every non-optional item has state === true. */
export function isChecklistReady(items: ChecklistItem[]): boolean {
  return items.every((item) => item.state === true || item.state === 'optional');
}

function CheckIcon() {
  return (
    <svg
      aria-hidden="true"
      className="h-4 w-4 shrink-0 text-green-500 dark:text-green-400"
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function XIcon() {
  return (
    <svg
      aria-hidden="true"
      className="h-4 w-4 shrink-0 text-red-600 dark:text-red-400"
      viewBox="0 0 20 20"
      fill="currentColor"
    >
      <path
        fillRule="evenodd"
        d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function InfoDot() {
  return (
    <span
      aria-hidden="true"
      className="mt-0.5 h-4 w-4 shrink-0 flex items-center justify-center"
    >
      <span className="h-1.5 w-1.5 rounded-full bg-gray-400 dark:bg-gray-500" />
    </span>
  );
}

export function SendChecklist({
  title = 'Ready to send',
  items,
  hideWhenAllGreen = false,
  className,
}: SendChecklistProps): JSX.Element | null {
  if (hideWhenAllGreen && isChecklistReady(items)) {
    return null;
  }

  return (
    <div
      aria-live="polite"
      className={clsx(
        'rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-700 dark:bg-gray-800',
        className
      )}
    >
      <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{title}</p>
      <ul className="mt-3 space-y-2" role="list">
        {items.map((item) => {
          const isFailed = item.state === false;
          const isOptional = item.state === 'optional';

          let icon: JSX.Element;
          if (isOptional) {
            icon = <InfoDot />;
          } else if (isFailed) {
            icon = <XIcon />;
          } else {
            icon = <CheckIcon />;
          }

          let labelTone: string;
          if (isFailed) {
            labelTone = 'font-medium text-red-600 dark:text-red-400';
          } else if (isOptional) {
            labelTone = 'text-gray-500 dark:text-gray-400';
          } else {
            labelTone = 'text-gray-700 dark:text-gray-300';
          }

          return (
            <li key={item.key}>
              <div className="flex items-start gap-2">
                <span className="mt-0.5">{icon}</span>
                <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
                  <div className="min-w-0">
                    <span className={clsx('text-sm', labelTone)}>
                      {item.label}
                    </span>
                    {isFailed && item.hint && (
                      <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                        {item.hint}
                      </p>
                    )}
                  </div>
                  {item.action && (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={item.action.onClick}
                      className="shrink-0 px-2 py-0.5 text-xs"
                    >
                      {item.action.label}
                    </Button>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
