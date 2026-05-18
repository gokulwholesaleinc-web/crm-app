import { useRef, useState } from 'react';
import { ArrowUpTrayIcon, DocumentTextIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { PROPOSAL_MASTER_CONTRACT_MAX_BYTES } from '../../api/proposals';

interface PendingMasterContractFieldProps {
  /** Current pending files (lifted state, owned by ProposalForm). */
  value: File[];
  /** Emit on selection / clear. The parent handles uploading the stashed
   *  bytes via ``POST /api/proposals/{id}/master-contract`` after the
   *  create response returns the new proposal id. */
  onChange: (files: File[]) => void;
}

/**
 * Create-flow signing-documents picker.
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

  const handleFiles = (files: FileList | File[] | null) => {
    if (!files || files.length === 0) {
      setError(null);
      return;
    }
    const next = Array.from(files);
    const invalid = next.find((file) => file.type && file.type !== 'application/pdf');
    if (invalid) {
      setError(`${invalid.name} must be a PDF file.`);
      return;
    }
    const oversized = next.find((file) => file.size > PROPOSAL_MASTER_CONTRACT_MAX_BYTES);
    if (oversized) {
      setError(`${oversized.name} exceeds the 25 MB limit.`);
      return;
    }
    setError(null);
    onChange([...value, ...next]);
  };

  const removeAt = (index: number) => {
    onChange(value.filter((_, i) => i !== index));
  };

  return (
    <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-800/40 space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Signing documents
        </h3>
        <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
          Optional. Add every PDF that needs the client&rsquo;s signature. After
          creation, place a signing area on each document before sending.
        </p>
      </div>
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="inline-flex items-center justify-center gap-2 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 shadow-sm hover:bg-gray-100 dark:hover:bg-gray-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
        >
          <ArrowUpTrayIcon className="h-4 w-4" aria-hidden="true" />
          Choose signing PDFs
        </button>
        {value.length > 0 && (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {value.length} PDF{value.length === 1 ? '' : 's'} selected
          </span>
        )}
      </div>
      {value.length > 0 && (
        <ul className="space-y-2">
          {value.map((file, index) => (
            <li
              key={`${file.name}-${file.size}-${index}`}
              className="flex items-center justify-between gap-2 rounded border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-xs"
            >
              <span className="inline-flex min-w-0 items-center gap-2 text-gray-700 dark:text-gray-200">
                <DocumentTextIcon className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                <span className="truncate">{file.name}</span>
              </span>
              <button
                type="button"
                onClick={() => removeAt(index)}
                aria-label={`Remove ${file.name}`}
                className="p-0.5 text-gray-400 hover:text-red-600 dark:hover:text-red-400 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-red-500"
              >
                <XMarkIcon className="h-4 w-4" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        multiple
        className="hidden"
        onChange={(e) => {
          const files = e.target.files;
          // Reset so re-uploading the same filename still re-fires onChange.
          e.target.value = '';
          handleFiles(files);
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
