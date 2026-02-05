/**
 * Reusable Notes List component for any entity (contact, lead, opportunity, company).
 * Displays notes with add, edit, and delete functionality.
 */

import { useState } from 'react';
import { Button, Spinner, ConfirmDialog } from '../ui';
import { useEntityNotes, useCreateNote, useDeleteNote } from '../../hooks';
import { formatDate } from '../../utils/formatters';
import { useUIStore } from '../../store/uiStore';

interface NotesListProps {
  entityType: string;
  entityId: number;
}

export function NotesList({ entityType, entityId }: NotesListProps) {
  const [newNote, setNewNote] = useState('');
  const [noteToDelete, setNoteToDelete] = useState<{ id: number; content: string } | null>(null);
  const addToast = useUIStore((state) => state.addToast);

  // Fetch notes for the entity
  const { data: notesData, isLoading, error } = useEntityNotes(entityType, entityId);
  const notes = notesData?.items || [];

  // Mutations
  const createNoteMutation = useCreateNote();
  const deleteNoteMutation = useDeleteNote();

  const handleAddNote = async () => {
    if (!newNote.trim()) return;

    try {
      await createNoteMutation.mutateAsync({
        content: newNote.trim(),
        entity_type: entityType,
        entity_id: entityId,
      });
      setNewNote('');
      addToast({
        type: 'success',
        title: 'Note Added',
        message: 'Your note has been added successfully.',
      });
    } catch {
      addToast({
        type: 'error',
        title: 'Error',
        message: 'Failed to add note. Please try again.',
      });
    }
  };

  const handleDeleteConfirm = async () => {
    if (!noteToDelete) return;

    try {
      await deleteNoteMutation.mutateAsync({
        id: noteToDelete.id,
        entityType,
        entityId,
      });
      setNoteToDelete(null);
      addToast({
        type: 'success',
        title: 'Note Deleted',
        message: 'Your note has been deleted successfully.',
      });
    } catch {
      addToast({
        type: 'error',
        title: 'Error',
        message: 'Failed to delete note. Please try again.',
      });
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Submit on Ctrl/Cmd + Enter
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleAddNote();
    }
  };

  if (error) {
    return (
      <div className="bg-white shadow rounded-lg p-4">
        <p className="text-sm text-red-500 text-center py-4">
          Failed to load notes. Please try again.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Add Note Form */}
      <div className="bg-white shadow rounded-lg p-4">
        <label htmlFor="new-note" className="sr-only">
          Add a note
        </label>
        <textarea
          id="new-note"
          rows={3}
          value={newNote}
          onChange={(e) => setNewNote(e.target.value)}
          onKeyDown={handleKeyDown}
          className="block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
          placeholder="Add a note... (Ctrl+Enter to submit)"
        />
        <div className="mt-3 flex justify-end">
          <Button
            disabled={!newNote.trim() || createNoteMutation.isPending}
            onClick={handleAddNote}
            isLoading={createNoteMutation.isPending}
            className="w-full sm:w-auto"
          >
            Add Note
          </Button>
        </div>
      </div>

      {/* Notes List */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          {isLoading ? (
            <div className="flex items-center justify-center py-4">
              <Spinner />
            </div>
          ) : notes.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-4">
              No notes yet. Add your first note above.
            </p>
          ) : (
            <ul className="space-y-4">
              {notes.map((note) => (
                <li
                  key={note.id}
                  className="group relative pb-4 border-b border-gray-100 last:border-0 last:pb-0"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0 pr-4">
                      <p className="text-sm text-gray-900 whitespace-pre-wrap break-words">
                        {note.content}
                      </p>
                      <div className="mt-2 flex items-center gap-2 text-xs text-gray-500">
                        {note.author_name && (
                          <>
                            <span className="font-medium">{note.author_name}</span>
                            <span>-</span>
                          </>
                        )}
                        <span>{formatDate(note.created_at)}</span>
                        {note.updated_at !== note.created_at && (
                          <span className="italic">(edited)</span>
                        )}
                      </div>
                    </div>
                    <button
                      onClick={() => setNoteToDelete({ id: note.id, content: note.content })}
                      className="flex-shrink-0 p-1 text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                      title="Delete note"
                    >
                      <svg
                        className="h-4 w-4"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                        />
                      </svg>
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={!!noteToDelete}
        onClose={() => setNoteToDelete(null)}
        onConfirm={handleDeleteConfirm}
        title="Delete Note"
        message="Are you sure you want to delete this note? This action cannot be undone."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteNoteMutation.isPending}
      />
    </div>
  );
}

export default NotesList;
