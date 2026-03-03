/**
 * Documents tab component that displays attachments grouped by category
 * with filter tabs and upload support.
 */

import { useState, useCallback, useRef } from 'react';
import { Spinner, ConfirmDialog } from '../ui';
import { useAttachments, useUploadAttachment, useDeleteAttachment } from '../../hooks/useAttachments';
import { getDownloadUrl } from '../../api/attachments';
import { getToken } from '../../api/client';
import { useUIStore } from '../../store/uiStore';

interface DocumentsTabProps {
  entityType: string;
  entityId: number;
}

type CategoryFilter = 'all' | 'document' | 'contract' | 'image' | 'report' | 'other';

const CATEGORY_TABS: { id: CategoryFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'document', label: 'Documents' },
  { id: 'contract', label: 'Contracts' },
  { id: 'image', label: 'Images' },
  { id: 'report', label: 'Reports' },
  { id: 'other', label: 'Other' },
];

const UPLOAD_CATEGORIES = [
  { value: 'document', label: 'Document' },
  { value: 'contract', label: 'Contract' },
  { value: 'image', label: 'Image' },
  { value: 'report', label: 'Report' },
  { value: 'other', label: 'Other' },
];

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

function getCategoryBadgeColor(category: string | null): string {
  switch (category) {
    case 'document': return 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300';
    case 'contract': return 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-300';
    case 'image': return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300';
    case 'report': return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-300';
    case 'other': return 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
    default: return 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400';
  }
}

export function DocumentsTab({ entityType, entityId }: DocumentsTabProps) {
  const [activeFilter, setActiveFilter] = useState<CategoryFilter>('all');
  const [uploadCategory, setUploadCategory] = useState('document');
  const [attachmentToDelete, setAttachmentToDelete] = useState<{
    id: number;
    name: string;
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const addToast = useUIStore((state) => state.addToast);

  const { data: attachmentData, isLoading, error } = useAttachments(entityType, entityId);
  const allAttachments = attachmentData?.items || [];

  const uploadMutation = useUploadAttachment();
  const deleteMutation = useDeleteAttachment();

  const filteredAttachments = activeFilter === 'all'
    ? allAttachments
    : allAttachments.filter((a) => a.category === activeFilter);

  const handleUpload = useCallback(
    async (files: FileList | File[]) => {
      for (const file of Array.from(files)) {
        try {
          await uploadMutation.mutateAsync({
            file,
            entityType,
            entityId,
            category: uploadCategory,
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
    [entityType, entityId, uploadCategory, uploadMutation, addToast],
  );

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleUpload(e.target.files);
      e.target.value = '';
    }
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
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4">
        <p className="text-sm text-red-500 text-center py-4">
          Failed to load documents.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Upload Bar */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg px-4 py-3 flex items-center gap-3 flex-wrap">
        <label htmlFor="upload-category" className="text-sm font-medium text-gray-700 dark:text-gray-300">
          Category:
        </label>
        <select
          id="upload-category"
          value={uploadCategory}
          onChange={(e) => setUploadCategory(e.target.value)}
          className="rounded-md border-gray-300 dark:border-gray-600 text-sm shadow-sm focus:border-primary-500 focus:ring-primary-500 bg-white dark:bg-gray-700 dark:text-gray-100"
        >
          {UPLOAD_CATEGORIES.map((cat) => (
            <option key={cat.value} value={cat.value}>
              {cat.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploadMutation.isPending}
          className="inline-flex items-center gap-1.5 rounded-md bg-primary-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:opacity-50"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          {uploadMutation.isPending ? 'Uploading...' : 'Upload File'}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          multiple
          accept=".pdf,.docx,.xlsx,.csv,.png,.jpg,.jpeg,.gif,.txt"
          onChange={handleFileSelect}
        />
      </div>

      {/* Category Filter Tabs */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg">
        <div className="border-b border-gray-200 dark:border-gray-700 px-4">
          <nav className="-mb-px flex space-x-6 overflow-x-auto" aria-label="Document categories">
            {CATEGORY_TABS.map((tab) => {
              const count = tab.id === 'all'
                ? allAttachments.length
                : allAttachments.filter((a) => a.category === tab.id).length;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveFilter(tab.id)}
                  className={`whitespace-nowrap py-3 px-1 border-b-2 text-sm font-medium ${
                    activeFilter === tab.id
                      ? 'border-primary-500 text-primary-600 dark:text-primary-400'
                      : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600'
                  }`}
                >
                  {tab.label}
                  {count > 0 && (
                    <span className="ml-1.5 rounded-full bg-gray-100 dark:bg-gray-700 px-2 py-0.5 text-xs text-gray-600 dark:text-gray-300">
                      {count}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        <div className="px-4 py-5 sm:p-6">
          {isLoading ? (
            <div className="flex items-center justify-center py-4">
              <Spinner />
            </div>
          ) : filteredAttachments.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
              {activeFilter === 'all'
                ? 'No documents attached yet.'
                : `No ${activeFilter} files found.`}
            </p>
          ) : (
            <ul className="divide-y divide-gray-100 dark:divide-gray-700">
              {filteredAttachments.map((attachment) => (
                <li
                  key={attachment.id}
                  className="flex items-center justify-between py-3"
                >
                  <div className="flex items-center min-w-0 gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                        {attachment.original_filename}
                      </p>
                      <div className="flex items-center gap-2 mt-0.5">
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          {formatFileSize(attachment.file_size)}
                        </span>
                        <span className="text-xs text-gray-400 dark:text-gray-500">-</span>
                        <span className="text-xs text-gray-500 dark:text-gray-400">
                          {formatDate(attachment.created_at)}
                        </span>
                        {attachment.category && (
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${getCategoryBadgeColor(attachment.category)}`}
                          >
                            {attachment.category}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0 ml-4">
                    <button
                      onClick={() =>
                        handleDownload(attachment.id, attachment.original_filename)
                      }
                      className="p-1.5 text-gray-400 hover:text-primary-600 transition-colors"
                      aria-label={`Download ${attachment.original_filename}`}
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
                          d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                        />
                      </svg>
                    </button>
                    <button
                      onClick={() =>
                        setAttachmentToDelete({
                          id: attachment.id,
                          name: attachment.original_filename,
                        })
                      }
                      className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
                      aria-label={`Delete ${attachment.original_filename}`}
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

export default DocumentsTab;
