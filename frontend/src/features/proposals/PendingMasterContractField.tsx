import { useRef, useState } from 'react';
import { ArrowUpTrayIcon, DocumentTextIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { PROPOSAL_MASTER_CONTRACT_MAX_BYTES } from '../../api/proposals';

interface PendingMasterContractFieldProps {
  /** Current pending file (lifted state, owned by ProposalForm). */
  value: File | null;
  /** Emit on selection / clear. The parent handles uploading the stashed
   *  bytes via ``POST /api/proposals/{id}/master-contract`` after the
   *  create response returns the new proposal id. */
  onChange: (file: File | null) => void;
}

/**
 * Create-flow master-contract picker.
 *
 * The detail-page ``MasterContractCard`` POSTs to
 * ``/api/proposals/{id}/master-contract`` and needs an existing proposal
 * id. On create, the proposal doesn't exist yet, so this field stashes
 * the chosen ``File`` client-side; ``ProposalsPage.handleFormSubmit``
 * uploads it as a second step after ``createProposalMutation`` resolves
 * with the new id.
 */
export function PendingMasterContractField({
  value,
  onChange,
}: PendingMasterContractFieldProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleFile = (file: File | null) => {
    if (!file) {
      setError(null);
      onChange(null);
      return;
    }
    if (file.type && file.type !== 'application/pdf') {
      setError('Master contract must be a PDF file.');
      return;
    }
    if (file.size > PROPOSAL_MASTER_CONTRACT_MAX_BYTES) {
      setError('Master contract exceeds the 25 MB limit.');
      return;
    }
    setError(null);
    onChange(file);
  };

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-800/40 space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Master service agreement
        </h3>
        <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
          Optional. The customer&rsquo;s drawn signature is stamped onto this PDF
          when they sign. Uploaded after the proposal is saved.
        </p>
      </div>
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="inline-flex items-center justify-center gap-2 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 shadow-sm hover:bg-gray-100 dark:hover:bg-gray-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          <ArrowUpTrayIcon className="h-4 w-4" aria-hidden="true" />
          {value ? 'Replace master contract PDF' : 'Choose master contract PDF'}
        </button>
        {value && (
          <span className="inline-flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300 min-w-0">
            <DocumentTextIcon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
            <span className="truncate">{value.name}</span>
            <button
              type="button"
              onClick={() => handleFile(null)}
              aria-label="Remove pending master contract"
              className="p-0.5 text-gray-400 hover:text-red-600 dark:hover:text-red-400 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-red-500"
            >
              <XMarkIcon className="h-4 w-4" aria-hidden="true" />
            </button>
          </span>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0] ?? null;
          // Reset so re-uploading the same filename still re-fires onChange.
          e.target.value = '';
          handleFile(file);
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
