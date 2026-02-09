/**
 * Reusable Attachment List component for any entity.
 * Displays uploaded files with download and delete actions.
 */

import { useState, useCallback, useRef } from 'react';
import { Button, Spinner, ConfirmDialog } from '../ui';
import { useAttachments, useUploadAttachment, useDeleteAttachment } from '../../hooks';
import { getDownloadUrl } from '../../api/attachments';
import { getToken } from '../../api/client';
import { useUIStore } from '../../store/uiStore';

interface AttachmentListProps {
  entityType: string;
  entityId: number;
}

const FILE_TYPE_ICONS: Record<string, string> = {
  'application/pdf': 'PDF',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'DOCX',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'XLSX',
  'text/csv': 'CSV',
  'text/plain': 'TXT',
  'image/png': 'PNG',
  'image/jpeg': 'JPG',
  'image/gif': 'GIF',
};

function getFileTypeLabel(mimeType: string): string {
  return FILE_TYPE_ICONS[mimeType] || 'FILE';
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function AttachmentList({ entityType, entityId }: AttachmentListProps) {
  const [attachmentToDelete, setAttachmentToDelete] = useState<{
    id: number;
    name: string;
  } | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const addToast = useUIStore((state) => state.addToast);

  const { data: attachmentData, isLoading, error } = useAttachments(entityType, entityId);
  const attachments = attachmentData?.items || [];

  const uploadMutation = useUploadAttachment();
  const deleteMutation = useDeleteAttachment();

  const handleUpload = useCallback(
    async (files: FileList | File[]) => {
      for (const file of Array.from(files)) {
        try {
          await uploadMutation.mutateAsync({
            file,
            entityType,
            entityId,
          });
          addToast({
            type: 'success',
            title: 'File Uploaded',
            message: `${file.name} uploaded successfully.`,
          });
        } catch {
          addToast({
            type: 'error',
            title: 'Upload Failed',
            message: `Failed to upload ${file.name}. Check file type and size.`,
          });
        }
      }
    },
    [entityType, entityId, uploadMutation, addToast],
  );

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleUpload(e.target.files);
      e.target.value = '';
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      handleUpload(e.dataTransfer.files);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDeleteConfirm = async () => {
    if (!attachmentToDelete) return;
    try {
      await deleteMutation.mutateAsync({
        id: attachmentToDelete.id,
        entityType,
        entityId,
      });
      setAttachmentToDelete(null);
      addToast({
        type: 'success',
        title: 'File Deleted',
        message: 'Attachment deleted successfully.',
      });
    } catch {
      addToast({
        type: 'error',
        title: 'Error',
        message: 'Failed to delete attachment.',
      });
    }
  };

  const handleDownload = async (attachmentId: number, filename: string) => {
    try {
      const url = getDownloadUrl(attachmentId);
      const token = getToken();
      const response = await fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) throw new Error('Download failed');
      const blob = await response.blob();
      const blobUrl = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = blobUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(blobUrl);
    } catch {
      addToast({
        type: 'error',
        title: 'Download Failed',
        message: 'Failed to download the file.',
      });
    }
  };

  if (error) {
    return (
      <div className="bg-white shadow rounded-lg p-4">
        <p className="text-sm text-red-500 text-center py-4">
          Failed to load attachments.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Upload Zone */}
      <div
        role="button"
        tabIndex={0}
        className={`bg-white shadow rounded-lg p-6 border-2 border-dashed transition-colors cursor-pointer ${
          isDragOver
            ? 'border-primary-400 bg-primary-50'
            : 'border-gray-300 hover:border-gray-400'
        }`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            fileInputRef.current?.click();
          }
        }}
      >
        <div className="text-center">
          <svg
            className="mx-auto h-10 w-10 text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
            />
          </svg>
          <p className="mt-2 text-sm text-gray-600">
            {uploadMutation.isPending
              ? 'Uploading...'
              : 'Drag and drop files here, or click to browse'}
          </p>
          <p className="mt-1 text-xs text-gray-400">
            PDF, DOCX, XLSX, CSV, PNG, JPG, GIF, TXT (max 10MB)
          </p>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          multiple
          accept=".pdf,.docx,.xlsx,.csv,.png,.jpg,.jpeg,.gif,.txt"
          onChange={handleFileSelect}
        />
      </div>

      {/* Attachment List */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          {isLoading ? (
            <div className="flex items-center justify-center py-4">
              <Spinner />
            </div>
          ) : attachments.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-4">
              No files attached yet.
            </p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {attachments.map((attachment) => (
                <li
                  key={attachment.id}
                  className="group flex items-center justify-between py-3"
                >
                  <div className="flex items-center min-w-0 gap-3">
                    <span className="flex-shrink-0 inline-flex items-center justify-center h-10 w-10 rounded-lg bg-gray-100 text-xs font-bold text-gray-600">
                      {getFileTypeLabel(attachment.mime_type)}
                    </span>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 truncate">
                        {attachment.original_filename}
                      </p>
                      <p className="text-xs text-gray-500">
                        {formatFileSize(attachment.file_size)} - {formatDate(attachment.created_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0 ml-4">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDownload(attachment.id, attachment.original_filename);
                      }}
                      className="p-1.5 text-gray-400 hover:text-primary-600 transition-colors"
                      title="Download"
                      aria-label={`Download ${attachment.original_filename}`}
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                      </svg>
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setAttachmentToDelete({
                          id: attachment.id,
                          name: attachment.original_filename,
                        });
                      }}
                      className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
                      title="Delete"
                      aria-label={`Delete ${attachment.original_filename}`}
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
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
        isOpen={!!attachmentToDelete}
        onClose={() => setAttachmentToDelete(null)}
        onConfirm={handleDeleteConfirm}
        title="Delete Attachment"
        message={`Are you sure you want to delete "${attachmentToDelete?.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}

export default AttachmentList;
