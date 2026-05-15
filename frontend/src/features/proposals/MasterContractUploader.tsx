import { useRef, useState } from 'react';
import { ArrowUpTrayIcon, DocumentTextIcon } from '@heroicons/react/24/outline';
import { apiClient } from '../../api/client';

interface MasterContractUploaderProps {
  proposalId: number;
  /** Existing master-contract R2 key, or null when no master is on file. */
  currentPath: string | null;
  onUploaded?: () => void;
}

const MAX_BYTES = 25 * 1024 * 1024;

/**
 * Admin-side widget for attaching the master service agreement PDF to
 * a proposal. On signing the customer's drawn signature is stamped
 * onto a copy of this PDF + an audit page is appended.
 */
export function MasterContractUploader({
  proposalId,
  currentPath,
  onUploaded,
}: MasterContractUploaderProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploadedPath, setUploadedPath] = useState<string | null>(currentPath);

  const handleFile = async (file: File) => {
    if (file.type && file.type !== 'application/pdf') {
      setError('Master contract must be a PDF file.');
      return;
    }
    if (file.size > MAX_BYTES) {
      setError('Master contract exceeds the 25 MB limit.');
      return;
    }
    setUploading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('file', file);
      const response = await apiClient.post<{ master_contract_pdf_path: string | null }>(
        `/api/proposals/${proposalId}/master-contract`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      );
      setUploadedPath(response.data.master_contract_pdf_path ?? null);
      onUploaded?.();
    } catch (err) {
      setError(
        (typeof err === 'object' && err !== null && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null) ?? 'Master contract upload failed. Please try again.',
      );
    } finally {
      setUploading(false);
    }
  };

  const hasMaster = !!uploadedPath;
  const buttonLabel = hasMaster ? 'Replace master contract PDF' : 'Upload master contract PDF';

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-800/40 space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Master service agreement
        </h3>
        <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
          Optional. When set, the customer's drawn signature is stamped onto this PDF
          and a countersigned copy is emailed to both parties.
        </p>
      </div>
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
          className="inline-flex items-center justify-center gap-2 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 shadow-sm hover:bg-gray-100 dark:hover:bg-gray-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50"
        >
          <ArrowUpTrayIcon className="h-4 w-4" aria-hidden="true" />
          {uploading ? 'Uploading…' : buttonLabel}
        </button>
        {hasMaster && (
          <span className="inline-flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-300">
            <DocumentTextIcon className="h-4 w-4" aria-hidden="true" />
            <span className="font-mono">{uploadedPath}</span>
          </span>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          // Reset so re-uploading the same filename still re-fires onChange.
          e.target.value = '';
          if (file) {
            void handleFile(file);
          }
        }}
      />
      {error && (
        <p
          role="alert"
          aria-live="polite"
          className="text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded px-3 py-2"
        >
          {error}
        </p>
      )}
    </div>
  );
}
