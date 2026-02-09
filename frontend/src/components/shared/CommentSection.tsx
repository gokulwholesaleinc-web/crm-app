import { useState } from 'react';
import {
  useEntityComments,
  useCreateComment,
  useDeleteComment,
} from '../../hooks/useComments';
import { Spinner, Button } from '../ui';
import { formatDate } from '../../utils/formatters';
import type { Comment as CommentType } from '../../types';

interface CommentSectionProps {
  entityType: string;
  entityId: number;
}

function CommentItem({
  comment,
  entityType,
  entityId,
  depth,
}: {
  comment: CommentType;
  entityType: string;
  entityId: number;
  depth: number;
}) {
  const [showReplyForm, setShowReplyForm] = useState(false);
  const [replyContent, setReplyContent] = useState('');
  const createMutation = useCreateComment();
  const deleteMutation = useDeleteComment();

  const handleReply = async () => {
    if (!replyContent.trim()) return;
    await createMutation.mutateAsync({
      content: replyContent,
      entity_type: entityType,
      entity_id: entityId,
      parent_id: comment.id,
    });
    setReplyContent('');
    setShowReplyForm(false);
  };

  const handleDelete = async () => {
    await deleteMutation.mutateAsync({
      commentId: comment.id,
      entityType,
      entityId,
    });
  };

  return (
    <div className={depth > 0 ? 'ml-6 sm:ml-8 border-l-2 border-gray-100 pl-4' : ''}>
      <div className="py-3">
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0">
            <div className="h-8 w-8 rounded-full bg-primary-100 flex items-center justify-center text-xs font-medium text-primary-700">
              {(comment.user_name || 'U').charAt(0).toUpperCase()}
            </div>
          </div>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium text-gray-900">
                {comment.user_name || 'Unknown'}
              </span>
              {comment.is_internal && (
                <span className="inline-flex items-center rounded-full bg-yellow-100 px-2 py-0.5 text-xs font-medium text-yellow-800">
                  Internal
                </span>
              )}
              <span className="text-xs text-gray-500">
                {formatDate(comment.created_at)}
              </span>
            </div>
            <div className="mt-1 text-sm text-gray-700 whitespace-pre-wrap break-words">
              {comment.content}
            </div>
            {comment.mentioned_users && comment.mentioned_users.length > 0 && (
              <div className="mt-1 flex flex-wrap gap-1">
                {comment.mentioned_users.map((user) => (
                  <span
                    key={user}
                    className="text-xs text-primary-600 bg-primary-50 rounded px-1"
                  >
                    @{user}
                  </span>
                ))}
              </div>
            )}
            <div className="mt-2 flex gap-3">
              {depth < 2 && (
                <button
                  onClick={() => setShowReplyForm(!showReplyForm)}
                  className="text-xs text-gray-500 hover:text-primary-600"
                >
                  Reply
                </button>
              )}
              <button
                onClick={handleDelete}
                className="text-xs text-gray-500 hover:text-red-600"
              >
                Delete
              </button>
            </div>

            {showReplyForm && (
              <div className="mt-3">
                <textarea
                  value={replyContent}
                  onChange={(e) => setReplyContent(e.target.value)}
                  placeholder="Write a reply... Use @name to mention someone"
                  className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
                  rows={2}
                />
                <div className="mt-2 flex gap-2">
                  <Button
                    size="sm"
                    onClick={handleReply}
                    isLoading={createMutation.isPending}
                  >
                    Reply
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => {
                      setShowReplyForm(false);
                      setReplyContent('');
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {comment.replies && comment.replies.length > 0 && (
        <div>
          {comment.replies.map((reply) => (
            <CommentItem
              key={reply.id}
              comment={reply}
              entityType={entityType}
              entityId={entityId}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export function CommentSection({ entityType, entityId }: CommentSectionProps) {
  const [page, setPage] = useState(1);
  const [newComment, setNewComment] = useState('');
  const [isInternal, setIsInternal] = useState(false);
  const { data, isLoading } = useEntityComments(entityType, entityId, page);
  const createMutation = useCreateComment();

  const handleSubmit = async () => {
    if (!newComment.trim()) return;
    await createMutation.mutateAsync({
      content: newComment,
      entity_type: entityType,
      entity_id: entityId,
      is_internal: isInternal,
    });
    setNewComment('');
  };

  const comments = data?.items || [];
  const totalPages = data?.pages || 1;

  return (
    <div className="bg-white shadow rounded-lg p-4 sm:p-6">
      {/* New comment form */}
      <div className="mb-6">
        <textarea
          value={newComment}
          onChange={(e) => setNewComment(e.target.value)}
          placeholder="Add a comment... Use @name to mention someone"
          className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:ring-1 focus:ring-primary-500"
          rows={3}
        />
        <div className="mt-2 flex items-center justify-between flex-wrap gap-2">
          <label className="flex items-center gap-2 text-sm text-gray-600">
            <input
              type="checkbox"
              checked={isInternal}
              onChange={(e) => setIsInternal(e.target.checked)}
              className="rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            />
            Internal only
          </label>
          <Button
            onClick={handleSubmit}
            isLoading={createMutation.isPending}
            disabled={!newComment.trim()}
          >
            Comment
          </Button>
        </div>
      </div>

      {/* Comments list */}
      {isLoading ? (
        <div className="flex items-center justify-center py-4">
          <Spinner />
        </div>
      ) : comments.length === 0 ? (
        <p className="text-sm text-gray-500 text-center py-4">
          No comments yet. Be the first to comment.
        </p>
      ) : (
        <div className="divide-y divide-gray-100">
          {comments.map((comment) => (
            <CommentItem
              key={comment.id}
              comment={comment}
              entityType={entityType}
              entityId={entityId}
              depth={0}
            />
          ))}
        </div>
      )}

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between border-t border-gray-200 pt-4">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="text-sm text-primary-600 hover:text-primary-500 disabled:text-gray-400 disabled:cursor-not-allowed"
          >
            Previous
          </button>
          <span className="text-sm text-gray-500">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="text-sm text-primary-600 hover:text-primary-500 disabled:text-gray-400 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
