/**
 * Reusable Notes List component for any entity (contact, lead, opportunity, company).
 * Displays notes with add, edit, and delete functionality.
 */

import { useState, useRef, useCallback } from 'react';
import { Button, Spinner, ConfirmDialog } from '../ui';
import { useEntityNotes, useCreateNote, useDeleteNote } from '../../hooks/useNotes';
import { useUsers } from '../../hooks/useAuth';
import { formatDate } from '../../utils/formatters';
import { useUIStore } from '../../store/uiStore';
import type { User } from '../../types';

interface NotesListProps {
  entityType: string;
  entityId: number;
}

export function NotesList({ entityType, entityId }: NotesListProps) {
  const [newNote, setNewNote] = useState('');
  const [noteToDelete, setNoteToDelete] = useState<{ id: number; content: string } | null>(null);
  const [showMentions, setShowMentions] = useState(false);
  const [mentionFilter, setMentionFilter] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const addToast = useUIStore((state) => state.addToast);

  // Fetch notes for the entity
  const { data: notesData, isLoading, error } = useEntityNotes(entityType, entityId);
  const notes = notesData?.items || [];

  // Fetch users for @mention autocomplete
  const { data: usersData } = useUsers();
  const users: User[] = usersData ?? [];

  const filteredUsers = users.filter((u) =>
    u.full_name.toLowerCase().includes(mentionFilter.toLowerCase())
  );

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

  const handleNoteChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setNewNote(value);

    const cursorPos = e.target.selectionStart;
    const textBeforeCursor = value.substring(0, cursorPos);
    const atMatch = textBeforeCursor.match(/@(\w*)$/);

    if (atMatch) {
      setShowMentions(true);
      setMentionFilter(atMatch[1] ?? '');
    } else {
      setShowMentions(false);
      setMentionFilter('');
    }
  };

  const insertMention = (user: User) => {
    if (!textareaRef.current) return;

    const cursorPos = textareaRef.current.selectionStart;
    const textBeforeCursor = newNote.substring(0, cursorPos);
    const textAfterCursor = newNote.substring(cursorPos);
    const atIndex = textBeforeCursor.lastIndexOf('@');

    if (atIndex >= 0) {
      const mentionName = user.full_name.replace(/\s+/g, '.');
      const updated =
        textBeforeCursor.substring(0, atIndex) +
        `@${mentionName} ` +
        textAfterCursor;
      setNewNote(updated);
    }

    setShowMentions(false);
    setMentionFilter('');
    textareaRef.current.focus();
  };

  const renderNoteContent = useCallback((text: string) => {
    const parts = text.split(/(@\w+(?:\.\w+)*)/g);
    return parts.map((part, i) => {
      if (part.startsWith('@')) {
        return (
          <span key={i} className="text-primary-600 dark:text-primary-400 font-medium">
            {part}
          </span>
        );
      }
      return part;
    });
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Submit on Ctrl/Cmd + Enter
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleAddNote();
    }
    if (e.key === 'Escape') {
      setShowMentions(false);
    }
  };

  if (error) {
    return (
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4">
        <p className="text-sm text-red-500 text-center py-4">
          Failed to load notes. Please try again.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Add Note Form */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4">
        <div className="relative">
          <label htmlFor="new-note" className="sr-only">
            Add a note
          </label>
          <textarea
            id="new-note"
            ref={textareaRef}
            rows={3}
            value={newNote}
            onChange={handleNoteChange}
            onKeyDown={handleKeyDown}
            className="block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm bg-white dark:bg-gray-700 dark:text-gray-100 dark:placeholder-gray-400"
            placeholder="Add a note... Use @name to mention someone (Ctrl+Enter to submit)"
          />

          {/* @mention dropdown */}
          {showMentions && filteredUsers.length > 0 && (
            <div className="absolute z-10 mt-1 w-64 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md shadow-lg max-h-40 overflow-y-auto">
              {filteredUsers.slice(0, 8).map((user) => (
                <button
                  key={user.id}
                  type="button"
                  onClick={() => insertMention(user)}
                  className="w-full text-left px-3 py-2 text-sm hover:bg-gray-100 dark:hover:bg-gray-700 focus-visible:bg-gray-100 dark:focus-visible:bg-gray-700 focus-visible:outline-none dark:text-gray-100"
                >
                  <span className="font-medium">{user.full_name}</span>
                  <span className="text-gray-400 ml-2">{user.email}</span>
                </button>
              ))}
            </div>
          )}
        </div>
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
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          {isLoading ? (
            <div className="flex items-center justify-center py-4">
              <Spinner />
            </div>
          ) : notes.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
              No notes yet.
            </p>
          ) : (
            <ul className="space-y-4">
              {notes.map((note) => (
                <li
                  key={note.id}
                  className="group relative pb-4 border-b border-gray-100 dark:border-gray-700 last:border-0 last:pb-0"
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0 pr-4">
                      <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap break-words">
                        {renderNoteContent(note.content)}
                      </p>
                      <div className="mt-2 flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
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
                      aria-label="Delete note"
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
