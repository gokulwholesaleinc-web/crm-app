/**
 * Reusable Comment Section component for any entity.
 * Supports threaded replies, @mentions, and internal comments.
 */

import { useState, useRef, useCallback } from 'react';
import { Button, Spinner, ConfirmDialog } from '../ui';
import {
  useEntityComments,
  useCreateComment,
  useDeleteComment,
  useUsers,
} from '../../hooks';
import { formatDate } from '../../utils/formatters';
import { useUIStore } from '../../store/uiStore';
import { useAuthStore } from '../../store/authStore';
import type { Comment as CommentType, User } from '../../types';
import clsx from 'clsx';

interface CommentSectionProps {
  entityType: string;
  entityId: number;
}

interface CommentInputProps {
  onSubmit: (content: string, isInternal: boolean) => Promise<void>;
  isLoading: boolean;
  placeholder?: string;
  users?: User[];
  showInternalToggle?: boolean;
}

function CommentInput({
  onSubmit,
  isLoading,
  placeholder = 'Add a comment... Use @name to mention someone',
  users = [],
  showInternalToggle = true,
}: CommentInputProps) {
  const [content, setContent] = useState('');
  const [isInternal, setIsInternal] = useState(false);
  const [showMentions, setShowMentions] = useState(false);
  const [mentionFilter, setMentionFilter] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const filteredUsers = users.filter((u) =>
    u.full_name.toLowerCase().includes(mentionFilter.toLowerCase())
  );

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    setContent(value);

    // Detect @mention trigger
    const cursorPos = e.target.selectionStart;
    const textBeforeCursor = value.substring(0, cursorPos);
    const atMatch = textBeforeCursor.match(/@(\w*)$/);

    if (atMatch) {
      setShowMentions(true);
      setMentionFilter(atMatch[1]);
    } else {
      setShowMentions(false);
      setMentionFilter('');
    }
  };

  const insertMention = (user: User) => {
    if (!textareaRef.current) return;

    const cursorPos = textareaRef.current.selectionStart;
    const textBeforeCursor = content.substring(0, cursorPos);
    const textAfterCursor = content.substring(cursorPos);
    const atIndex = textBeforeCursor.lastIndexOf('@');

    if (atIndex >= 0) {
      const mentionName = user.full_name.replace(/\s+/g, '.');
      const newContent =
        textBeforeCursor.substring(0, atIndex) +
        `@${mentionName} ` +
        textAfterCursor;
      setContent(newContent);
    }

    setShowMentions(false);
    setMentionFilter('');
    textareaRef.current.focus();
  };

  const handleSubmit = async () => {
    if (!content.trim()) return;
    await onSubmit(content.trim(), isInternal);
    setContent('');
    setIsInternal(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      handleSubmit();
    }
    if (e.key === 'Escape') {
      setShowMentions(false);
    }
  };

  return (
    <div className="relative">
      <label htmlFor="comment-input" className="sr-only">
        Add a comment
      </label>
      <textarea
        id="comment-input"
        ref={textareaRef}
        rows={3}
        value={content}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        className="block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 text-sm"
        placeholder={placeholder}
      />

      {/* @mention dropdown */}
      {showMentions && filteredUsers.length > 0 && (
        <div className="absolute z-10 mt-1 w-64 bg-white border border-gray-200 rounded-md shadow-lg max-h-40 overflow-y-auto">
          {filteredUsers.slice(0, 8).map((user) => (
            <button
              key={user.id}
              type="button"
              onClick={() => insertMention(user)}
              className="w-full text-left px-3 py-2 text-sm hover:bg-gray-100 focus-visible:bg-gray-100 focus-visible:outline-none"
            >
              <span className="font-medium">{user.full_name}</span>
              <span className="text-gray-400 ml-2">{user.email}</span>
            </button>
          ))}
        </div>
      )}

      <div className="mt-3 flex items-center justify-between">
        {showInternalToggle ? (
          <label className="flex items-center gap-2 text-xs text-gray-500 cursor-pointer">
            <input
              type="checkbox"
              checked={isInternal}
              onChange={(e) => setIsInternal(e.target.checked)}
              className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            />
            Internal only (hidden from external users)
          </label>
        ) : (
          <div />
        )}
        <Button
          disabled={!content.trim() || isLoading}
          onClick={handleSubmit}
          isLoading={isLoading}
          className="w-auto"
        >
          Comment
        </Button>
      </div>
    </div>
  );
}

interface CommentItemProps {
  comment: CommentType;
  currentUserId: number | undefined;
  entityType: string;
  entityId: number;
  onReply: (parentId: number) => void;
  onDelete: (id: number) => void;
  depth?: number;
}

function CommentItem({
  comment,
  currentUserId,
  entityType,
  entityId,
  onReply,
  onDelete,
  depth = 0,
}: CommentItemProps) {
  const isAuthor = currentUserId === comment.user_id;
  const maxDepth = 3;

  // Render content with @mention highlighting
  const renderContent = useCallback((text: string) => {
    const parts = text.split(/(@\w+(?:\.\w+)*)/g);
    return parts.map((part, i) => {
      if (part.startsWith('@')) {
        return (
          <span key={i} className="text-primary-600 font-medium">
            {part}
          </span>
        );
      }
      return part;
    });
  }, []);

  return (
    <div
      className={clsx(
        'relative',
        depth > 0 && 'ml-6 pl-4 border-l-2 border-gray-100'
      )}
    >
      <div className="group py-3">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-gray-900">
                {comment.author_name || 'Unknown User'}
              </span>
              {comment.is_internal && (
                <span className="inline-flex items-center rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800">
                  Internal
                </span>
              )}
              <time className="text-xs text-gray-400">
                {formatDate(comment.created_at)}
              </time>
            </div>
            <p className="mt-1 text-sm text-gray-700 whitespace-pre-wrap break-words">
              {renderContent(comment.content)}
            </p>
            <div className="mt-2 flex items-center gap-3">
              {depth < maxDepth && (
                <button
                  type="button"
                  onClick={() => onReply(comment.id)}
                  className="text-xs text-gray-400 hover:text-primary-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded"
                >
                  Reply
                </button>
              )}
              {isAuthor && (
                <button
                  type="button"
                  onClick={() => onDelete(comment.id)}
                  className="text-xs text-gray-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 rounded"
                >
                  Delete
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Nested replies */}
      {comment.replies && comment.replies.length > 0 && (
        <div>
          {comment.replies.map((reply) => (
            <CommentItem
              key={reply.id}
              comment={reply}
              currentUserId={currentUserId}
              entityType={entityType}
              entityId={entityId}
              onReply={onReply}
              onDelete={onDelete}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function CommentSection({ entityType, entityId }: CommentSectionProps) {
  const [replyingTo, setReplyingTo] = useState<number | null>(null);
  const [commentToDelete, setCommentToDelete] = useState<number | null>(null);
  const addToast = useUIStore((state) => state.addToast);
  const currentUser = useAuthStore((state) => state.user);

  const { data: commentsData, isLoading, error } = useEntityComments(
    entityType,
    entityId
  );
  const comments = commentsData?.items ?? [];

  const { data: usersData } = useUsers();
  const users = usersData ?? [];

  const createCommentMutation = useCreateComment();
  const deleteCommentMutation = useDeleteComment();

  const handleAddComment = async (content: string, isInternal: boolean) => {
    try {
      await createCommentMutation.mutateAsync({
        content,
        entity_type: entityType,
        entity_id: entityId,
        is_internal: isInternal,
      });
      addToast({
        type: 'success',
        title: 'Comment Added',
        message: 'Your comment has been posted.',
      });
    } catch {
      addToast({
        type: 'error',
        title: 'Error',
        message: 'Failed to add comment. Please try again.',
      });
    }
  };

  const handleReply = async (content: string, isInternal: boolean) => {
    if (!replyingTo) return;
    try {
      await createCommentMutation.mutateAsync({
        content,
        entity_type: entityType,
        entity_id: entityId,
        parent_id: replyingTo,
        is_internal: isInternal,
      });
      setReplyingTo(null);
      addToast({
        type: 'success',
        title: 'Reply Added',
        message: 'Your reply has been posted.',
      });
    } catch {
      addToast({
        type: 'error',
        title: 'Error',
        message: 'Failed to post reply. Please try again.',
      });
    }
  };

  const handleDeleteConfirm = async () => {
    if (commentToDelete === null) return;
    try {
      await deleteCommentMutation.mutateAsync({
        id: commentToDelete,
        entityType,
        entityId,
      });
      setCommentToDelete(null);
      addToast({
        type: 'success',
        title: 'Comment Deleted',
        message: 'The comment has been removed.',
      });
    } catch {
      addToast({
        type: 'error',
        title: 'Error',
        message: 'Failed to delete comment. Please try again.',
      });
    }
  };

  if (error) {
    return (
      <div className="bg-white shadow rounded-lg p-4">
        <p className="text-sm text-red-500 text-center py-4">
          Failed to load comments. Please try again.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Add Comment Form */}
      <div className="bg-white shadow rounded-lg p-4">
        <CommentInput
          onSubmit={handleAddComment}
          isLoading={createCommentMutation.isPending}
          users={users}
        />
      </div>

      {/* Comments List */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          {isLoading ? (
            <div className="flex items-center justify-center py-4">
              <Spinner />
            </div>
          ) : comments.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-4">
              No comments yet. Start the conversation above.
            </p>
          ) : (
            <div className="divide-y divide-gray-100">
              {comments.map((comment) => (
                <div key={comment.id}>
                  <CommentItem
                    comment={comment}
                    currentUserId={currentUser?.id}
                    entityType={entityType}
                    entityId={entityId}
                    onReply={(parentId) => setReplyingTo(parentId)}
                    onDelete={(id) => setCommentToDelete(id)}
                  />

                  {/* Inline reply form */}
                  {replyingTo === comment.id && (
                    <div className="ml-6 pl-4 border-l-2 border-primary-200 py-2">
                      <p className="text-xs text-gray-500 mb-2">
                        Replying to {comment.author_name || 'Unknown User'}
                        <button
                          type="button"
                          onClick={() => setReplyingTo(null)}
                          className="ml-2 text-gray-400 hover:text-gray-600 focus-visible:outline-none"
                        >
                          Cancel
                        </button>
                      </p>
                      <CommentInput
                        onSubmit={handleReply}
                        isLoading={createCommentMutation.isPending}
                        placeholder="Write a reply..."
                        users={users}
                        showInternalToggle={false}
                      />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={commentToDelete !== null}
        onClose={() => setCommentToDelete(null)}
        onConfirm={handleDeleteConfirm}
        title="Delete Comment"
        message="Are you sure you want to delete this comment? This action cannot be undone."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteCommentMutation.isPending}
      />
    </div>
  );
}

export default CommentSection;
