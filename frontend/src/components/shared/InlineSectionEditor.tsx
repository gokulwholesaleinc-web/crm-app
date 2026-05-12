/**
 * InlineSectionEditor — two-mode card for inline text editing.
 *
 * Read mode: shows title + value text. If canEdit is true, a pencil button
 * appears in the top-right corner. Empty value + canEdit shows an "Add…"
 * affordance instead of an empty card.
 *
 * Edit mode: replaces value with a controlled textarea that autofocuses.
 * Keyboard shortcuts: Cmd/Ctrl+Enter → Save, Esc → Cancel.
 */

import { useState, useRef, useEffect, KeyboardEvent } from 'react';
import { PencilIcon } from '@heroicons/react/24/outline';
import { Button } from '../ui/Button';
import clsx from 'clsx';

export interface InlineSectionEditorProps {
  /** Visible heading for the section. */
  title: string;
  /** Current value. */
  value: string | null;
  /** Called when user clicks Save. Receives trimmed value (null if empty). */
  onSave: (next: string | null) => Promise<void> | void;
  /** Caller controls when edits are allowed. */
  canEdit: boolean;
  /** Optional rows for the textarea (default 4). */
  rows?: number;
  /** Optional placeholder when in edit mode. */
  placeholder?: string;
  /** If true, render with whitespace-pre-wrap. Defaults to true. */
  preWrap?: boolean;
  /** Optional className for outer card. */
  className?: string;
}

export function InlineSectionEditor({
  title,
  value,
  onSave,
  canEdit,
  rows = 4,
  placeholder,
  preWrap = true,
  className,
}: InlineSectionEditorProps): JSX.Element {
  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? '');
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (isEditing && textareaRef.current) {
      const el = textareaRef.current;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    }
  }, [isEditing]);

  function enterEdit() {
    setDraft(value ?? '');
    setError(null);
    setIsEditing(true);
  }

  function cancelEdit() {
    setIsEditing(false);
    setError(null);
  }

  async function handleSave() {
    const trimmed = draft.trim();
    const next = trimmed === '' ? null : trimmed;
    if (next === (value ?? null) || (next === null && value === null)) {
      setIsEditing(false);
      return;
    }
    setIsPending(true);
    setError(null);
    try {
      await onSave(next);
      setIsEditing(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed. Please try again.');
    } finally {
      setIsPending(false);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Escape') {
      e.preventDefault();
      cancelEdit();
    } else if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      void handleSave();
    }
  }

  const cardBase =
    'bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700';

  if (!isEditing) {
    const isEmpty = !value;

    if (isEmpty && canEdit) {
      return (
        <button
          type="button"
          onClick={enterEdit}
          className={clsx(
            cardBase,
            'w-full text-left text-sm text-gray-400 dark:text-gray-500',
            'hover:border-primary-300 dark:hover:border-primary-600 transition-colors',
            className,
          )}
          aria-label={`Add ${title}`}
        >
          <span className="font-medium text-gray-500 dark:text-gray-400 block mb-2">{title}</span>
          <span className="italic">Add {title}...</span>
        </button>
      );
    }

    return (
      <div className={clsx(cardBase, 'relative', className)}>
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">{title}</h2>
          {canEdit && (
            <button
              type="button"
              aria-label={`Edit ${title}`}
              onClick={enterEdit}
              className={clsx(
                'flex-shrink-0 rounded p-1 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200',
                'hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500',
              )}
            >
              <PencilIcon className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>
        {value && (
          <p
            className={clsx(
              'text-sm text-gray-900 dark:text-gray-100',
              preWrap && 'whitespace-pre-wrap',
            )}
          >
            {value}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className={clsx(cardBase, className)}>
      <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">{title}</h2>
      <textarea
        ref={textareaRef}
        rows={rows}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={isPending}
        className={clsx(
          'w-full rounded-md border border-gray-300 dark:border-gray-600',
          'bg-white dark:bg-gray-700 text-sm text-gray-900 dark:text-gray-100',
          'px-3 py-2 resize-y placeholder-gray-400 dark:placeholder-gray-500',
          'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent',
          'disabled:opacity-50',
        )}
      />
      {error && (
        <p className="mt-1 text-sm text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      )}
      <div className="mt-3 flex gap-2">
        <Button
          size="sm"
          onClick={() => void handleSave()}
          disabled={isPending}
          isLoading={isPending}
          aria-disabled={isPending}
        >
          Save
        </Button>
        <Button
          size="sm"
          variant="secondary"
          onClick={cancelEdit}
          disabled={isPending}
          aria-disabled={isPending}
        >
          Cancel
        </Button>
      </div>
    </div>
  );
}
