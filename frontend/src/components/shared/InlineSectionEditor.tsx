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
  // Snapshot the value at the moment the user enters edit mode so we
  // can detect remote updates landing mid-edit (parent query refetch,
  // teammate save, etc.) and warn before the user clobbers them.
  const valueAtEditStartRef = useRef<string | null>(value);

  useEffect(() => {
    if (isEditing && textareaRef.current) {
      const el = textareaRef.current;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    }
  }, [isEditing]);

  // External update detection: when isEditing is true and the current
  // value prop differs from the snapshot taken at edit-start, the
  // field changed under the user. Toggled into a warning banner; the
  // user can dismiss by overwriting or accept the remote value.
  const hasRemoteChange =
    isEditing && (value ?? '') !== (valueAtEditStartRef.current ?? '');

  function enterEdit() {
    valueAtEditStartRef.current = value;
    setDraft(value ?? '');
    setError(null);
    setIsEditing(true);
  }

  function acceptRemote() {
    valueAtEditStartRef.current = value;
    setDraft(value ?? '');
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
      {hasRemoteChange && (
        <div
          role="status"
          aria-live="polite"
          className="mb-2 rounded-md border border-amber-200 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30 px-3 py-2 text-xs text-amber-900 dark:text-amber-100 flex items-start justify-between gap-2"
        >
          <span>
            This field was updated elsewhere while you were editing. Saving now will overwrite the new value.
          </span>
          <button
            type="button"
            onClick={acceptRemote}
            className="shrink-0 font-medium underline hover:no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 rounded"
          >
            Use latest
          </button>
        </div>
      )}
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
