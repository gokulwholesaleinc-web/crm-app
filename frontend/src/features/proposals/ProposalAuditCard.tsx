import { useEffect, useState } from 'react';
import { ShieldCheckIcon, EyeIcon } from '@heroicons/react/24/outline';
import type { ApiError, Proposal } from '../../types';
import { downloadProposalSignatureImage } from '../../api/proposals';

/**
 * Detail-page sidebar card that surfaces the e-signature audit trail
 * + the public-link view log. Everything shown here is already
 * captured in the DB (Proposal.signer_* fields, the durable ESIGN
 * evidence snapshots, the drawn signature image, + ProposalView rows) —
 * this component just exposes it so the CRM user has a paper trail
 * for dispute resolution and legal discovery.
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

function humanizeAcceptanceMethod(method: string | null | undefined): string {
  if (!method) return '—';
  // Stored as a stable machine token (e.g. "drawn_signature"); render a
  // human-readable label without losing the underlying value.
  return method.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
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
  const proposalId = proposal.id;
  const [signatureUrl, setSignatureUrl] = useState<string | null>(null);
  const [signatureUnavailable, setSignatureUnavailable] = useState(false);

  // The drawn signature is stored as raw bytes, so it's served from its own
  // authed endpoint and rendered via an object URL (revoked on cleanup).
  // A 404 is the expected "no signature drawn" case (e.g. rep-side
  // admin-accept) — hide the image silently. Any other failure on a
  // legally-significant artifact must NOT masquerade as "no signature": flag
  // it so the operator knows the record is unreachable, not absent.
  useEffect(() => {
    if (!signed) {
      setSignatureUrl(null);
      setSignatureUnavailable(false);
      return;
    }
    let cancelled = false;
    let objectUrl: string | null = null;
    setSignatureUnavailable(false);
    downloadProposalSignatureImage(proposalId)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setSignatureUrl(objectUrl);
      })
      .catch((err: ApiError) => {
        if (cancelled) return;
        setSignatureUrl(null);
        if (err?.status_code !== 404) {
          console.error('[ProposalAuditCard] signature fetch failed', err);
          setSignatureUnavailable(true);
        }
      });
    return () => {
      cancelled = true;
      // Clear before revoking so a proposalId change doesn't briefly render
      // <img> against an already-revoked object URL.
      setSignatureUrl(null);
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [signed, proposalId]);

  const disclosure = proposal.esign_disclosure_snapshot?.trim();
  const termsSnapshot = proposal.terms_and_conditions_snapshot?.trim();

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
            {proposal.acceptance_method && (
              <div>
                <dt className="text-gray-500 dark:text-gray-400">Method</dt>
                <dd className="font-medium text-gray-900 dark:text-gray-100">
                  {humanizeAcceptanceMethod(proposal.acceptance_method)}
                </dd>
              </div>
            )}
            {proposal.agreed_to_terms_at && (
              <div>
                <dt className="text-gray-500 dark:text-gray-400">Consent given at</dt>
                <dd
                  className="font-medium text-gray-900 dark:text-gray-100"
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                >
                  {formatFullTimestamp(proposal.agreed_to_terms_at)}
                </dd>
              </div>
            )}
          </dl>

          {signatureUrl && (
            <div className="mt-3">
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Signature</p>
              <img
                src={signatureUrl}
                alt={`Signature drawn by ${proposal.signer_name || 'the signer'}`}
                width={280}
                height={120}
                className="w-full max-w-[280px] h-auto rounded border border-gray-200 dark:border-gray-600 bg-white"
              />
            </div>
          )}

          {signatureUnavailable && (
            <p
              className="mt-3 text-xs text-amber-700 dark:text-amber-400"
              aria-live="polite"
            >
              The signature image couldn’t be loaded right now. The signature
              was captured — reload to try again.
            </p>
          )}

          {(disclosure || termsSnapshot) && (
            <details className="mt-3 group">
              <summary className="cursor-pointer text-xs font-medium text-green-800 dark:text-green-300 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green-600">
                View consent record
                {proposal.esign_disclosure_version
                  ? ` (v${proposal.esign_disclosure_version})`
                  : ''}
              </summary>
              <div className="mt-2 space-y-3 text-xs text-gray-700 dark:text-gray-300">
                {disclosure && (
                  <div>
                    <p className="font-semibold text-gray-600 dark:text-gray-400 mb-1">
                      Disclosure the signer agreed to
                    </p>
                    <p className="whitespace-pre-wrap break-words">{disclosure}</p>
                  </div>
                )}
                {termsSnapshot && (
                  <div>
                    <p className="font-semibold text-gray-600 dark:text-gray-400 mb-1">
                      Terms &amp; conditions at acceptance
                    </p>
                    <p className="whitespace-pre-wrap break-words">{termsSnapshot}</p>
                  </div>
                )}
              </div>
            </details>
          )}
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
