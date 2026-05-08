import { useState, useCallback, useRef } from 'react';
import { Spinner, ConfirmDialog } from '../../components/ui';
import { useAttachments, useUploadAttachment, useDeleteAttachment } from '../../hooks/useAttachments';
import { getDownloadUrl } from '../../api/attachments';
import { getToken } from '../../api/client';
import { useUIStore } from '../../store/uiStore';

interface ContractAttachmentsSectionProps {
  contractId: number;
  canEdit: boolean;
}

const MAX_TOTAL_BYTES = 25 * 1024 * 1024;

const ACCEPTED_MIME = new Set([
  'application/pdf',
  'image/png',
  'image/jpg',
  'image/jpeg',
  'image/webp',
  'image/gif',
]);

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

export function ContractAttachmentsSection({ contractId, canEdit }: ContractAttachmentsSectionProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [attachmentToDelete, setAttachmentToDelete] = useState<{ id: number; name: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const addToast = useUIStore((state) => state.addToast);

  const { data: attachmentData, isLoading, error } = useAttachments('contracts', contractId);
  const allAttachments = attachmentData?.items || [];

  const uploadMutation = useUploadAttachment();
  const deleteMutation = useDeleteAttachment();

  const handleUpload = useCallback(
    async (files: FileList | File[]) => {
      const fileArray = Array.from(files);
      const totalSize = fileArray.reduce((sum, f) => sum + f.size, 0);
      if (totalSize > MAX_TOTAL_BYTES) {
        addToast({
          type: 'error',
          title: 'Upload Failed',
          message: `Total file size exceeds 25 MB limit.`,
        });
        return;
      }
      for (const file of fileArray) {
        const ext = file.name.split('.').pop()?.toLowerCase() ?? '';
        const validExts = new Set(['pdf', 'png', 'jpg', 'jpeg', 'webp', 'gif']);
        if (!ACCEPTED_MIME.has(file.type) && !validExts.has(ext)) {
          addToast({
            type: 'error',
            title: 'Invalid File Type',
            message: `${file.name}: only PDF and images (PNG, JPG, WebP, GIF) are allowed.`,
          });
          continue;
        }
        try {
          await uploadMutation.mutateAsync({
            file,
            entityType: 'contracts',
            entityId: contractId,
            category: 'contract',
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
    [contractId, uploadMutation, addToast],
  );

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleUpload(e.target.files);
      e.target.value = '';
    }
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0) {
      handleUpload(e.dataTransfer.files);
    }
  };

  const handleDeleteConfirm = async () => {
    if (!attachmentToDelete) return;
    try {
      await deleteMutation.mutateAsync({
        id: attachmentToDelete.id,
        entityType: 'contracts',
        entityId: contractId,
      });
      setAttachmentToDelete(null);
      addToast({ type: 'success', title: 'File Deleted', message: 'Attachment deleted successfully.' });
    } catch {
      addToast({ type: 'error', title: 'Error', message: 'Failed to delete attachment.' });
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
      addToast({ type: 'error', title: 'Download Failed', message: 'Failed to download the file.' });
    }
  };

  if (error) {
    return (
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4">
        <p className="text-sm text-red-500 text-center py-4">Failed to load attachments.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {canEdit && (
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`rounded-lg border-2 border-dashed px-6 py-8 text-center transition-colors ${
            isDragging
              ? 'border-primary-400 bg-primary-50 dark:bg-primary-900/20'
              : 'border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800'
          }`}
        >
          <svg
            className="mx-auto h-10 w-10 text-gray-400 dark:text-gray-500 mb-3"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
            />
          </svg>
          <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">
            Drag and drop files here, or{' '}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="font-medium text-primary-600 dark:text-primary-400 hover:underline focus-visible:outline-none"
            >
              browse
            </button>
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-500">
            PDF, PNG, JPG, WebP, GIF — max 25 MB total
          </p>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadMutation.isPending}
            className="mt-4 inline-flex items-center gap-1.5 rounded-md bg-primary-600 px-3 py-1.5 text-sm font-medium text-white shadow-sm hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-600 disabled:opacity-50"
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
            accept=".pdf,.png,.jpg,.jpeg,.webp,.gif"
            onChange={handleFileSelect}
          />
        </div>
      )}

      <div className="bg-white dark:bg-gray-800 shadow rounded-lg">
        <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100">
            Attachments
            {allAttachments.length > 0 && (
              <span className="ml-2 rounded-full bg-gray-100 dark:bg-gray-700 px-2 py-0.5 text-xs text-gray-600 dark:text-gray-300">
                {allAttachments.length}
              </span>
            )}
          </h3>
        </div>

        <div className="px-4 py-4">
          {isLoading ? (
            <div className="flex items-center justify-center py-6">
              <Spinner />
            </div>
          ) : allAttachments.length === 0 ? (
            <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
              No attachments yet.
            </p>
          ) : (
            <ul className="divide-y divide-gray-100 dark:divide-gray-700">
              {allAttachments.map((attachment) => (
                <li key={attachment.id} className="flex items-center justify-between py-3">
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
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0 ml-4">
                    <button
                      onClick={() => handleDownload(attachment.id, attachment.original_filename)}
                      className="p-1.5 text-gray-400 hover:text-primary-600 transition-colors"
                      aria-label={`Download ${attachment.original_filename}`}
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                        />
                      </svg>
                    </button>
                    {canEdit && (
                      <button
                        onClick={() => setAttachmentToDelete({ id: attachment.id, name: attachment.original_filename })}
                        className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
                        aria-label={`Delete ${attachment.original_filename}`}
                      >
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                          />
                        </svg>
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

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
