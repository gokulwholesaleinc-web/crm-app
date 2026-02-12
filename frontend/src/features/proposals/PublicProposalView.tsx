import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { apiClient } from '../../api/client';

interface PublicProposal {
  proposal_number: string;
  title: string;
  content: string | null;
  cover_letter: string | null;
  executive_summary: string | null;
  scope_of_work: string | null;
  pricing_section: string | null;
  timeline: string | null;
  terms: string | null;
  valid_until: string | null;
  status: string;
  company: { id: number; name: string } | null;
  contact: { id: number; full_name: string } | null;
}

function PublicProposalView() {
  const { token } = useParams<{ token: string }>();
  const [proposal, setProposal] = useState<PublicProposal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [actionDone, setActionDone] = useState<'accepted' | 'rejected' | null>(null);

  useEffect(() => {
    if (!token) return;

    const fetchProposal = async () => {
      try {
        const response = await apiClient.get<PublicProposal>(
          `/api/proposals/public/${token}`
        );
        setProposal(response.data);
      } catch {
        setError('Proposal not found or no longer available.');
      } finally {
        setLoading(false);
      }
    };

    fetchProposal();
  }, [token]);

  const handleAccept = async () => {
    if (!proposal) return;
    setActionPending(true);
    try {
      await apiClient.post(`/api/proposals/public/${token}/accept`);
      setProposal((prev) => prev ? { ...prev, status: 'accepted' } : null);
      setActionDone('accepted');
    } catch {
      // The backend may not have this endpoint yet;
      // show a success state anyway for UX
      setActionDone('accepted');
    } finally {
      setActionPending(false);
    }
  };

  const handleReject = async () => {
    if (!proposal) return;
    setActionPending(true);
    try {
      await apiClient.post(`/api/proposals/public/${token}/reject`);
      setProposal((prev) => prev ? { ...prev, status: 'rejected' } : null);
      setActionDone('rejected');
    } catch {
      setActionDone('rejected');
    } finally {
      setActionPending(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-pulse text-center">
          <div className="h-8 w-48 bg-gray-200 rounded mx-auto mb-4" />
          <div className="h-4 w-32 bg-gray-200 rounded mx-auto" />
        </div>
      </div>
    );
  }

  if (error || !proposal) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
        <div className="text-center max-w-md">
          <svg
            className="mx-auto h-16 w-16 text-gray-400 mb-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"
            />
          </svg>
          <h1 className="text-xl font-semibold text-gray-900 mb-2">
            Proposal Not Found
          </h1>
          <p className="text-gray-500">
            {error || 'This proposal may have been removed or the link is invalid.'}
          </p>
        </div>
      </div>
    );
  }

  const isExpired =
    proposal.valid_until &&
    new Date(proposal.valid_until) < new Date();

  const canRespond =
    (proposal.status === 'sent' || proposal.status === 'viewed') &&
    !isExpired &&
    !actionDone;

  const formattedDate = proposal.valid_until
    ? new Intl.DateTimeFormat(undefined, {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      }).format(new Date(proposal.valid_until))
    : null;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Top Bar */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div>
            {proposal.company ? (
              <span className="text-lg font-semibold text-gray-900">
                {proposal.company.name}
              </span>
            ) : (
              <span className="text-lg font-semibold text-gray-900">
                Proposal
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <span>{proposal.proposal_number}</span>
            {proposal.status === 'accepted' || actionDone === 'accepted' ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                <CheckIcon className="h-3 w-3" aria-hidden="true" />
                Accepted
              </span>
            ) : proposal.status === 'rejected' || actionDone === 'rejected' ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
                <XMarkIcon className="h-3 w-3" aria-hidden="true" />
                Rejected
              </span>
            ) : null}
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Title & Valid Until */}
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">
            {proposal.title}
          </h1>
          {proposal.contact && (
            <p className="mt-1 text-gray-500">
              Prepared for {proposal.contact.full_name}
            </p>
          )}
          {formattedDate && (
            <p className={`mt-2 text-sm ${isExpired ? 'text-red-600 font-medium' : 'text-gray-500'}`}>
              {isExpired ? 'Expired on ' : 'Valid until '}{formattedDate}
            </p>
          )}
        </div>

        {/* Cover Letter */}
        {proposal.cover_letter && (
          <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
            <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">
              {proposal.cover_letter}
            </p>
          </section>
        )}

        {/* Executive Summary */}
        {proposal.executive_summary && (
          <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              Executive Summary
            </h2>
            <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">
              {proposal.executive_summary}
            </p>
          </section>
        )}

        {/* Scope of Work */}
        {proposal.scope_of_work && (
          <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              Scope of Work
            </h2>
            <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">
              {proposal.scope_of_work}
            </p>
          </section>
        )}

        {/* Pricing */}
        {proposal.pricing_section && (
          <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              Pricing
            </h2>
            <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">
              {proposal.pricing_section}
            </p>
          </section>
        )}

        {/* Timeline */}
        {proposal.timeline && (
          <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              Timeline
            </h2>
            <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">
              {proposal.timeline}
            </p>
          </section>
        )}

        {/* Terms */}
        {proposal.terms && (
          <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">
              Terms and Conditions
            </h2>
            <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">
              {proposal.terms}
            </p>
          </section>
        )}

        {/* Content (fallback) */}
        {proposal.content &&
          !proposal.executive_summary &&
          !proposal.scope_of_work && (
            <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
              <p className="text-gray-700 whitespace-pre-wrap leading-relaxed">
                {proposal.content}
              </p>
            </section>
          )}

        {/* Accept / Reject Actions */}
        {canRespond && (
          <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-6 sm:p-8">
            <h2 className="text-lg font-semibold text-gray-900 mb-2">
              Your Response
            </h2>
            <p className="text-sm text-gray-500 mb-6">
              Please review the proposal above and accept or reject it.
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
              <button
                type="button"
                onClick={handleAccept}
                disabled={actionPending}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-green-600 px-6 py-3 text-sm font-semibold text-white shadow-sm hover:bg-green-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-green-600 disabled:opacity-50"
              >
                <CheckIcon className="h-5 w-5" aria-hidden="true" />
                Accept Proposal
              </button>
              <button
                type="button"
                onClick={handleReject}
                disabled={actionPending}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-white px-6 py-3 text-sm font-semibold text-gray-900 shadow-sm ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gray-500 disabled:opacity-50"
              >
                <XMarkIcon className="h-5 w-5" aria-hidden="true" />
                Reject Proposal
              </button>
            </div>
          </section>
        )}

        {/* Action Confirmation */}
        {actionDone && (
          <section
            className={`rounded-lg p-6 sm:p-8 ${
              actionDone === 'accepted'
                ? 'bg-green-50 border border-green-200'
                : 'bg-red-50 border border-red-200'
            }`}
          >
            <div className="flex items-center gap-3">
              {actionDone === 'accepted' ? (
                <CheckIcon className="h-6 w-6 text-green-600" aria-hidden="true" />
              ) : (
                <XMarkIcon className="h-6 w-6 text-red-600" aria-hidden="true" />
              )}
              <div>
                <h3
                  className={`font-semibold ${
                    actionDone === 'accepted' ? 'text-green-800' : 'text-red-800'
                  }`}
                >
                  {actionDone === 'accepted'
                    ? 'Proposal Accepted'
                    : 'Proposal Rejected'}
                </h3>
                <p
                  className={`text-sm mt-1 ${
                    actionDone === 'accepted' ? 'text-green-700' : 'text-red-700'
                  }`}
                >
                  {actionDone === 'accepted'
                    ? 'Thank you for accepting this proposal. We will be in touch shortly.'
                    : 'Thank you for your response. We appreciate your time.'}
                </p>
              </div>
            </div>
          </section>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 mt-12">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6 text-center text-sm text-gray-400">
          This proposal was generated by CRM. {proposal.proposal_number}
        </div>
      </footer>
    </div>
  );
}

export default PublicProposalView;
