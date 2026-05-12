import { ShieldCheckIcon } from '@heroicons/react/24/outline';
import type { Contract } from '../../types';

interface ContractAuditCardProps {
  contract: Contract;
}

const FULL_TIMESTAMP_FMT = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: 'numeric',
  second: 'numeric',
  timeZoneName: 'short',
});

function formatFullTimestamp(value: string | null | undefined): string {
  if (!value) return '—';
  const d = new Date(value);
  return isNaN(d.getTime()) ? value : FULL_TIMESTAMP_FMT.format(d);
}

export function ContractAuditCard({ contract }: ContractAuditCardProps) {
  const signed = Boolean(contract.signed_at);

  // signer_ip/signer_email/signer_user_agent are not yet in the Contract type;
  // read them defensively so the card forwards-compatibly shows them when the
  // backend starts returning them without requiring a type change first.
  const extra = contract as unknown as Record<string, unknown>;
  const signerName = (extra.signer_name as string | null | undefined) ?? contract.signed_by_name;
  const signerEmail = extra.signer_email as string | null | undefined;
  const signerIp = extra.signer_ip as string | null | undefined;
  const signerUserAgent = extra.signer_user_agent as string | null | undefined;

  if (!signed) {
    return (
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
        <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Audit trail</h2>
        <p className="text-xs text-gray-500 dark:text-gray-400">Not yet signed.</p>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
      <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-4">Audit trail</h2>

      <div className="rounded-md border border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 p-3">
        <div className="flex items-center gap-2 mb-2">
          <ShieldCheckIcon className="h-4 w-4 text-green-700 dark:text-green-400" aria-hidden="true" />
          <h3 className="text-xs font-semibold text-green-800 dark:text-green-300 uppercase tracking-wide">
            E-signature captured
          </h3>
        </div>
        <dl className="space-y-1.5 text-xs">
          {signerName && (
            <div>
              <dt className="text-gray-500 dark:text-gray-400">Name</dt>
              <dd className="font-medium text-gray-900 dark:text-gray-100 break-words">{signerName}</dd>
            </div>
          )}
          {signerEmail && (
            <div>
              <dt className="text-gray-500 dark:text-gray-400">Email</dt>
              <dd className="font-medium text-gray-900 dark:text-gray-100 break-all">{signerEmail}</dd>
            </div>
          )}
          <div>
            <dt className="text-gray-500 dark:text-gray-400">Signed at</dt>
            <dd className="font-medium text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
              {formatFullTimestamp(contract.signed_at)}
            </dd>
          </div>
          {signerIp && (
            <div>
              <dt className="text-gray-500 dark:text-gray-400">IP address</dt>
              <dd className="font-mono text-gray-900 dark:text-gray-100">{signerIp}</dd>
            </div>
          )}
          {signerUserAgent && (
            <div>
              <dt className="text-gray-500 dark:text-gray-400">Browser</dt>
              <dd className="text-gray-700 dark:text-gray-300 break-words" title={signerUserAgent}>
                {signerUserAgent}
              </dd>
            </div>
          )}
        </dl>
      </div>
    </div>
  );
}
