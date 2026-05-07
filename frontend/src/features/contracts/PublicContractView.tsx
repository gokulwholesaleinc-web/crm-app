/**
 * Public, no-auth contract sign view — Phase 1 shell.
 *
 * The E-sign worker (Phase 2a) replaces this with the full signer flow:
 * tenant-branded header, contract details, attachments list, signature
 * canvas, and Sign / Decline actions. Mirrors PublicProposalView.tsx.
 */

import { useParams } from 'react-router-dom';

export default function PublicContractView() {
  const { token } = useParams<{ token: string }>();
  return (
    <div className="mx-auto max-w-2xl p-8">
      <h1 className="text-2xl font-semibold text-gray-900">Contract for signature</h1>
      <p className="mt-3 text-sm text-gray-600">
        This signing page is being prepared. Token reference:{' '}
        <code className="rounded bg-gray-100 px-1 py-0.5 text-xs">{token?.slice(0, 8)}…</code>
      </p>
    </div>
  );
}
