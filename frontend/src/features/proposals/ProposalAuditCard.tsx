import { ShieldCheckIcon, EyeIcon } from '@heroicons/react/24/outline';
import type { Proposal } from '../../types';

/**
 * Detail-page sidebar card that surfaces the e-signature audit trail
 * + the public-link view log. Everything shown here is already
 * captured in the DB (Proposal.signer_* fields + ProposalView rows) —
 * this component just exposes it so the CRM user has a paper trail
 * for billing disputes, dispute resolution, and legal discovery.
 */

interface ProposalAuditCardProps {
  proposal: Proposal;
}

function formatFullTimestamp(value: string | null | undefined): string {
  if (!value) return '—';
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: 'numeric',
    second: 'numeric',
    timeZoneName: 'short',
  }).format(new Date(value));
}

function shortUserAgent(ua: string | null | undefined): string {
  if (!ua) return '—';
  // Keep the audit-grade detail accessible (hover title), but render a
  // human-parseable summary inline: browser + OS stripped out of the
  // verbose UA string.
  const browser = ua.match(/(Firefox|Chrome|Safari|Edg|Opera)\/[\d.]+/)?.[0] ?? 'Browser';
  const os = ua.match(/\((?:Windows|Macintosh|Linux|iPhone|iPad|Android)[^)]*\)/)?.[0]?.replace(/[()]/g, '') ?? '';
  return os ? `${browser} · ${os}` : browser;
}

export function ProposalAuditCard({ proposal }: ProposalAuditCardProps) {
  const signed = Boolean(proposal.signed_at);
  const views = proposal.views ?? [];
  // Newest-first; the backend lists them by id ASC by default.
  const sortedViews = [...views].sort(
    (a, b) => new Date(b.viewed_at).getTime() - new Date(a.viewed_at).getTime(),
  );
  const uniqueIps = new Set(
    sortedViews.map((v) => v.ip_address).filter((ip): ip is string => Boolean(ip)),
  );

  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
      <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-4">Audit trail</h2>

      {signed && (
        <div className="mb-5 rounded-md border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 p-3">
          <div className="flex items-center gap-2 mb-2">
            <ShieldCheckIcon className="h-4 w-4 text-green-700 dark:text-green-400" aria-hidden="true" />
            <h3 className="text-xs font-semibold text-green-800 dark:text-green-300 uppercase tracking-wide">
              E-signature captured
            </h3>
          </div>
          <dl className="space-y-1.5 text-xs">
            <div>
              <dt className="text-gray-500 dark:text-gray-400">Name</dt>
              <dd className="font-medium text-gray-900 dark:text-gray-100 break-words">
                {proposal.signer_name || '—'}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500 dark:text-gray-400">Email</dt>
              <dd className="font-medium text-gray-900 dark:text-gray-100 break-all">
                {proposal.signer_email || '—'}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500 dark:text-gray-400">Signed at</dt>
              <dd className="font-medium text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
                {formatFullTimestamp(proposal.signed_at)}
              </dd>
            </div>
            <div>
              <dt className="text-gray-500 dark:text-gray-400">IP address</dt>
              <dd className="font-mono text-gray-900 dark:text-gray-100">
                {proposal.signer_ip || '—'}
              </dd>
            </div>
            {proposal.signer_user_agent && (
              <div>
                <dt className="text-gray-500 dark:text-gray-400">Browser</dt>
                <dd
                  className="text-gray-700 dark:text-gray-300 break-words"
                  title={proposal.signer_user_agent}
                >
                  {shortUserAgent(proposal.signer_user_agent)}
                </dd>
              </div>
            )}
          </dl>
        </div>
      )}

      <div>
        <div className="flex items-center justify-between mb-3">
          <h3 className="flex items-center gap-2 text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide">
            <EyeIcon className="h-4 w-4" aria-hidden="true" />
            View history
          </h3>
          <span className="text-xs text-gray-500 dark:text-gray-400" style={{ fontVariantNumeric: 'tabular-nums' }}>
            {sortedViews.length} view{sortedViews.length === 1 ? '' : 's'}
            {uniqueIps.size > 1 ? ` · ${uniqueIps.size} IPs` : ''}
          </span>
        </div>

        {sortedViews.length === 0 ? (
          <p className="text-xs text-gray-500 dark:text-gray-400">
            No public views yet.
          </p>
        ) : (
          <ul className="space-y-2 max-h-64 overflow-y-auto text-xs">
            {sortedViews.map((view) => (
              <li key={view.id} className="border-l-2 border-gray-200 dark:border-gray-700 pl-3 py-1">
                <div className="font-medium text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {formatFullTimestamp(view.viewed_at)}
                </div>
                <div className="text-gray-500 dark:text-gray-400 flex flex-wrap gap-x-2">
                  <span className="font-mono">{view.ip_address || 'unknown IP'}</span>
                  {view.user_agent && (
                    <span title={view.user_agent}>· {shortUserAgent(view.user_agent)}</span>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
