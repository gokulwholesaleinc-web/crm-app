import { DocumentTextIcon, CheckCircleIcon } from '@heroicons/react/24/outline';
import type { ProposalAttachmentPublic } from '../../types';

// URL is built inline (rather than importing the helper from api/proposals)
// so this component doesn't pull the authenticated axios instance into the
// public proposal bundle — the public page deliberately uses a bare axios
// to avoid evicting a staff Bearer session.
function buildDownloadUrl(token: string, attachmentId: number): string {
  const baseUrl = import.meta.env.VITE_API_URL || '';
  return `${baseUrl}/api/proposals/public/${token}/attachments/${attachmentId}/download`;
}

interface ProposalAttachmentsSectionProps {
  attachments: ProposalAttachmentPublic[];
  token: string;
  accent: string;
  viewedIds: Set<number>;
  onViewed: (id: number) => void;
  /** Re-fetch the proposal so the server's authoritative `viewed` flags
   * reconcile any optimistic flips that didn't actually record. */
  onReconcile?: () => void;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function ProposalAttachmentsSection({
  attachments,
  token,
  accent,
  viewedIds,
  onViewed,
  onReconcile,
}: ProposalAttachmentsSectionProps) {
  if (attachments.length === 0) return null;

  const handleOpen = (id: number) => {
    const url = buildDownloadUrl(token, id);
    window.open(url, '_blank', 'noopener,noreferrer');
    // Optimistically mark viewed for instant UX feedback; the server
    // records the view as a side effect of the download endpoint hit.
    // If the download actually 5xx'd / rate-limited / failed, the
    // server's `viewed` flag stays false — schedule a reconcile so the
    // gate doesn't claim "all viewed" while the server still sees an
    // unread doc and rejects sign with a confusing 400.
    onViewed(id);
    if (onReconcile) {
      setTimeout(onReconcile, 3000);
    }
  };

  return (
    <section className="mt-10 sm:mt-12">
      <div className="mb-4">
        <div
          className="h-0.5 w-8 mb-3"
          style={{ backgroundColor: accent }}
          aria-hidden="true"
        />
        <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 tracking-tight">
          Attached Documents
        </h2>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
          Please open and read each attached document before signing.
        </p>
      </div>

      <ul className="rounded border border-gray-200 dark:border-gray-700 divide-y divide-gray-200 dark:divide-gray-700 overflow-hidden">
        {attachments.map((attachment) => {
          const viewed = viewedIds.has(attachment.id);
          return (
            <li
              key={attachment.id}
              className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between bg-white dark:bg-gray-900"
            >
              <div className="flex min-w-0 items-start gap-3">
                <DocumentTextIcon
                  className="h-5 w-5 flex-shrink-0 text-gray-400 dark:text-gray-500 mt-0.5"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100 break-words">
                    {attachment.original_filename}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
                    {formatFileSize(attachment.file_size)}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3 flex-shrink-0">
                {viewed && (
                  <span
                    className="inline-flex items-center gap-1 text-xs font-medium text-green-700 dark:text-green-400"
                    aria-label="Document opened"
                  >
                    <CheckCircleIcon className="h-4 w-4" aria-hidden="true" />
                    Opened
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => handleOpen(attachment.id)}
                  aria-label={`Open ${attachment.original_filename} in a new tab`}
                  className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-sm font-medium border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-200 hover:bg-gray-50 dark:hover:bg-gray-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 transition-colors"
                  style={{ outlineColor: accent }}
                >
                  Open document
                  <span aria-hidden="true">↗</span>
                </button>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export default ProposalAttachmentsSection;
