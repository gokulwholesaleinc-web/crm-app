/**
 * Contract detail page — Phase 1 shell.
 *
 * The Surface+Reports worker (Phase 2c) replaces this with the full
 * detail view: header card, e-sign actions (Send/Resend/Cancel/Download
 * signed PDF), attachments section, and the existing field surface.
 */

import { useParams } from 'react-router-dom';

export default function ContractDetailPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <div className="p-6">
      <h1 className="text-2xl font-semibold text-gray-900">Contract #{id}</h1>
      <p className="mt-2 text-sm text-gray-600">
        Contract detail page is being built.
      </p>
    </div>
  );
}
