import { useState, KeyboardEvent } from 'react';
import { Button } from '../ui/Button';
import { useCreateActivity } from '../../hooks/useActivities';
import { showError } from '../../utils/toast';

type EntityType = 'contact' | 'lead' | 'company' | 'opportunity' | 'proposal' | 'quote';

interface QuickAddNoteProps {
  entityType: EntityType;
  entityId: number;
  onCreated?: () => void;
}

export function QuickAddNote({ entityType, entityId, onCreated }: QuickAddNoteProps) {
  const [body, setBody] = useState('');
  const createActivity = useCreateActivity();

  const submit = async () => {
    const trimmed = body.trim();
    if (!trimmed || createActivity.isPending) return;
    try {
      await createActivity.mutateAsync({
        activity_type: 'note',
        subject: trimmed.slice(0, 80),
        description: trimmed,
        entity_type: entityType,
        entity_id: entityId,
        priority: 'normal',
      });
      setBody('');
      onCreated?.();
    } catch {
      showError('Failed to add note');
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      void submit();
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-3 sm:p-4 mb-4">
      <label htmlFor="quick-add-note" className="sr-only">
        Add a note
      </label>
      <textarea
        id="quick-add-note"
        value={body}
        onChange={(e) => setBody(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Add a note... (Ctrl+Enter to save)"
        rows={2}
        className="w-full resize-y rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
      />
      <div className="mt-2 flex justify-end">
        <Button
          size="sm"
          onClick={submit}
          disabled={!body.trim()}
          isLoading={createActivity.isPending}
        >
          Save Note
        </Button>
      </div>
    </div>
  );
}
