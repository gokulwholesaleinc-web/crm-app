/**
 * StatusTimeline renders a horizontal or vertical progress tracker for entities
 * that move through discrete states (e.g. Draft → Sent → Signed for proposals).
 *
 * Visual states:
 *   completed  – filled primary dot, solid connector to the next step
 *   current    – primary dot with an outer ring + pulse animation (respects prefers-reduced-motion)
 *   upcoming   – muted gray dot, no date
 *   skipped    – light gray dot with a slash overlay, faded label
 */

import type { CSSProperties, ReactNode } from 'react';
import clsx from 'clsx';

export interface TimelineStep {
  /** Stable key for React. */
  key: string;
  /** Short label shown under the dot (e.g., "Draft", "Sent", "Signed"). */
  label: string;
  /** ISO timestamp when this step happened. Null = upcoming step (faded). */
  at: string | null;
  /** "completed" past, "current" now-active, "upcoming" future, "skipped" not in this entity's flow. */
  state: 'completed' | 'current' | 'upcoming' | 'skipped';
  /** Optional tooltip body (rendered via aria-label + native title). */
  tooltip?: string;
}

export interface StatusTimelineProps {
  steps: TimelineStep[];
  /**
   * Visually condense for mobile — stack vertically with date inline.
   * Defaults to auto: horizontal on sm+, vertical below.
   */
  variant?: 'auto' | 'horizontal' | 'vertical';
  className?: string;
}

const fmt = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' });

function formatDate(iso: string): string {
  try {
    return fmt.format(new Date(iso));
  } catch {
    return iso;
  }
}

function StepDot({
  state,
  tooltip,
  describedById,
}: {
  state: TimelineStep['state'];
  tooltip?: string;
  describedById: string;
}) {
  const dotClass = clsx(
    'relative h-4 w-4 rounded-full flex-shrink-0 flex items-center justify-center',
    'focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500',
    'focus-visible:ring-offset-2 dark:focus-visible:ring-offset-gray-900',
    {
      'bg-primary-600': state === 'completed',
      'bg-primary-600 ring-4 ring-primary-200 dark:ring-primary-900': state === 'current',
      'bg-gray-200 dark:bg-gray-700': state === 'upcoming',
      'bg-gray-300 dark:bg-gray-600': state === 'skipped',
    }
  );

  return (
    <span
      tabIndex={tooltip ? 0 : undefined}
      title={tooltip}
      aria-describedby={tooltip ? describedById : undefined}
      className={dotClass}
      role={tooltip ? 'img' : undefined}
      aria-label={tooltip}
    >
      {state === 'current' && (
        <span
          className="absolute inset-0 rounded-full bg-primary-400 opacity-50 motion-safe:animate-ping"
          aria-hidden="true"
        />
      )}
      {state === 'skipped' && (
        <svg
          className="absolute inset-0 h-full w-full text-gray-500 dark:text-gray-400"
          viewBox="0 0 16 16"
          aria-hidden="true"
        >
          <line
            x1="3"
            y1="13"
            x2="13"
            y2="3"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
          />
        </svg>
      )}
    </span>
  );
}

function VisuallyHidden({ children }: { children: ReactNode }) {
  return <span className="sr-only">{children}</span>;
}

export function StatusTimeline({ steps, variant = 'auto', className }: StatusTimelineProps) {
  const isVertical = variant === 'vertical';
  const rowLayout = variant === 'horizontal' || variant === 'auto';

  return (
    <ol
      role="list"
      className={clsx(
        'flex gap-0',
        {
          'flex-col': isVertical,
          'flex-row': variant === 'horizontal',
          'flex-col sm:flex-row': variant === 'auto',
        },
        className
      )}
    >
      {steps.map((step, idx) => {
        const isLast = idx === steps.length - 1;
        const isCurrent = step.state === 'current';
        const describedById = `step-tooltip-${step.key}`;

        // Each step renders two half-connectors (left + right) around the
        // dot. Coloring rules:
        //   - LEFT half: gold once we've *arrived* at this step — i.e.
        //     this step is completed/current, OR the prior step was
        //     completed (the entity is past that segment).
        //   - RIGHT half: gold once we've *left* this step — i.e. this
        //     step is completed.
        // Treating `current` as "left half filled" is what makes the bar
        // run all the way to a terminal current dot (e.g. Signed/Rejected
        // on accepted/rejected proposals).
        const prior = idx > 0 ? steps[idx - 1] : null;
        const leftFilled =
          step.state === 'completed' ||
          step.state === 'current' ||
          prior?.state === 'completed';
        const rightFilled = step.state === 'completed';
        const filledClass = 'bg-primary-600';
        const emptyClass = 'bg-gray-200 dark:bg-gray-700';
        const leftConnectorClass = clsx(
          'flex-shrink-0',
          leftFilled ? filledClass : emptyClass,
        );
        const rightConnectorClass = clsx(
          'flex-shrink-0',
          rightFilled ? filledClass : emptyClass,
        );

        const labelClass = clsx('text-xs font-medium leading-tight block', {
          'text-primary-700 dark:text-primary-400':
            step.state === 'completed' || isCurrent,
          'text-gray-400 dark:text-gray-500': step.state === 'upcoming',
          'text-gray-400 dark:text-gray-500 line-through': step.state === 'skipped',
        });

        return (
          <li
            key={step.key}
            className={clsx('relative flex', {
              'flex-col items-center flex-1': rowLayout,
              'flex-row items-start': isVertical,
            })}
            aria-current={isCurrent ? 'step' : undefined}
          >
            {/* Dot row with connectors */}
            <div
              className={clsx('flex items-center', {
                'flex-row w-full': rowLayout,
                'flex-col w-auto mr-3': isVertical,
              })}
            >
              {idx > 0 && (
                <div
                  aria-hidden="true"
                  className={clsx(leftConnectorClass, {
                    'h-0.5 flex-1': rowLayout,
                    'w-0.5 flex-1 min-h-4': isVertical,
                  })}
                />
              )}

              <StepDot
                state={step.state}
                tooltip={step.tooltip}
                describedById={describedById}
              />

              {!isLast && (
                <div
                  aria-hidden="true"
                  className={clsx(rightConnectorClass, {
                    'h-0.5 flex-1': rowLayout,
                    'w-0.5 h-4': isVertical,
                  })}
                />
              )}
            </div>

            {/* Label + date */}
            <div
              className={clsx({
                'mt-2 text-center': rowLayout,
                'ml-2 mt-0 text-left': isVertical,
              })}
            >
              <span
                className={labelClass}
                style={{ textWrap: 'balance' } as CSSProperties}
              >
                {step.label}
              </span>

              {step.at && (
                <time
                  dateTime={step.at}
                  className="block text-xs text-gray-400 dark:text-gray-500 mt-0.5"
                >
                  <VisuallyHidden>on </VisuallyHidden>
                  {formatDate(step.at)}
                </time>
              )}
            </div>

            {step.tooltip && (
              <VisuallyHidden>
                <span id={describedById}>{step.tooltip}</span>
              </VisuallyHidden>
            )}
          </li>
        );
      })}
    </ol>
  );
}
