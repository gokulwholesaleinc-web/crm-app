import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { apiClient } from '../../api/client';

interface ProposalBranding {
  company_name: string | null;
  logo_url: string | null;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  footer_text: string | null;
}

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
  branding: ProposalBranding | null;
}

const DEFAULT_BRANDING: ProposalBranding = {
  company_name: null,
  logo_url: null,
  primary_color: '#6366f1',
  secondary_color: '#8b5cf6',
  accent_color: '#22c55e',
  footer_text: null,
};

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
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="animate-pulse text-center">
          <div className="h-8 w-48 bg-gray-200 dark:bg-gray-700 rounded mx-auto mb-4" />
          <div className="h-4 w-32 bg-gray-200 dark:bg-gray-700 rounded mx-auto" />
        </div>
      </div>
    );
  }

  if (error || !proposal) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center px-4">
        <div className="text-center max-w-md">
          <svg
            className="mx-auto h-16 w-16 text-gray-400 dark:text-gray-500 mb-4"
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
          <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Proposal Not Found
          </h1>
          <p className="text-gray-500 dark:text-gray-400">
            {error || 'This proposal may have been removed or the link is invalid.'}
          </p>
        </div>
      </div>
    );
  }

  const branding = proposal.branding ?? DEFAULT_BRANDING;
  const companyDisplayName = branding.company_name || proposal.company?.name || 'Proposal';

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
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Branded Top Bar */}
      <header
        className="sticky top-0 z-10 border-b border-gray-200 dark:border-gray-700"
        style={{ backgroundColor: branding.primary_color }}
      >
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3 min-w-0">
            {branding.logo_url ? (
              <img
                src={branding.logo_url}
                alt={companyDisplayName}
                width={36}
                height={36}
                className="rounded"
                style={{ maxHeight: 36 }}
              />
            ) : null}
            <span className="text-lg font-semibold text-white truncate">
              {companyDisplayName}
            </span>
          </div>
          <div className="flex items-center gap-2 text-sm text-white/80">
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
          <h1
            className="text-2xl sm:text-3xl font-bold text-wrap-balance"
            style={{ color: branding.primary_color }}
          >
            {proposal.title}
          </h1>
          {proposal.contact && (
            <p className="mt-1 text-gray-500 dark:text-gray-400">
              Prepared for {proposal.contact.full_name}
            </p>
          )}
          {formattedDate && (
            <p className={`mt-2 text-sm ${isExpired ? 'text-red-600 dark:text-red-400 font-medium' : 'text-gray-500 dark:text-gray-400'}`}>
              {isExpired ? 'Expired on ' : 'Valid until '}{formattedDate}
            </p>
          )}
        </div>

        {/* Cover Letter */}
        {proposal.cover_letter && (
          <section className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 sm:p-8">
            <p className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed break-words">
              {proposal.cover_letter}
            </p>
          </section>
        )}

        {/* Executive Summary */}
        {proposal.executive_summary && (
          <section
            className="rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 sm:p-8"
            style={{ backgroundColor: `${branding.secondary_color}10` }}
          >
            <h2
              className="text-lg font-semibold mb-4"
              style={{ color: branding.primary_color }}
            >
              Executive Summary
            </h2>
            <p className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed break-words">
              {proposal.executive_summary}
            </p>
          </section>
        )}

        {/* Scope of Work */}
        {proposal.scope_of_work && (
          <section
            className="rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 sm:p-8"
            style={{ backgroundColor: `${branding.secondary_color}10` }}
          >
            <h2
              className="text-lg font-semibold mb-4"
              style={{ color: branding.primary_color }}
            >
              Scope of Work
            </h2>
            <p className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed break-words">
              {proposal.scope_of_work}
            </p>
          </section>
        )}

        {/* Pricing */}
        {proposal.pricing_section && (
          <section
            className="rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 sm:p-8"
            style={{ backgroundColor: `${branding.secondary_color}10` }}
          >
            <h2
              className="text-lg font-semibold mb-4"
              style={{ color: branding.primary_color }}
            >
              Pricing
            </h2>
            <p className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed break-words">
              {proposal.pricing_section}
            </p>
          </section>
        )}

        {/* Timeline */}
        {proposal.timeline && (
          <section
            className="rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 sm:p-8"
            style={{ backgroundColor: `${branding.secondary_color}10` }}
          >
            <h2
              className="text-lg font-semibold mb-4"
              style={{ color: branding.primary_color }}
            >
              Timeline
            </h2>
            <p className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed break-words">
              {proposal.timeline}
            </p>
          </section>
        )}

        {/* Terms */}
        {proposal.terms && (
          <section
            className="rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 sm:p-8"
            style={{ backgroundColor: `${branding.secondary_color}10` }}
          >
            <h2
              className="text-lg font-semibold mb-4"
              style={{ color: branding.primary_color }}
            >
              Terms and Conditions
            </h2>
            <p className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed break-words">
              {proposal.terms}
            </p>
          </section>
        )}

        {/* Content (fallback) */}
        {proposal.content &&
          !proposal.executive_summary &&
          !proposal.scope_of_work && (
            <section className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 sm:p-8">
              <p className="text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed break-words">
                {proposal.content}
              </p>
            </section>
          )}

        {/* Accept / Reject Actions */}
        {canRespond && (
          <section className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6 sm:p-8">
            <h2
              className="text-lg font-semibold mb-2"
              style={{ color: branding.primary_color }}
            >
              Your Response
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mb-6">
              Please review the proposal above and accept or reject it.
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
              <button
                type="button"
                aria-label="Accept this proposal"
                onClick={handleAccept}
                disabled={actionPending}
                className="inline-flex items-center justify-center gap-2 rounded-lg px-6 py-3 text-sm font-semibold text-white shadow-sm hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50"
                style={{ backgroundColor: branding.accent_color, outlineColor: branding.accent_color }}
              >
                <CheckIcon className="h-5 w-5" aria-hidden="true" />
                Accept Proposal
              </button>
              <button
                type="button"
                aria-label="Reject this proposal"
                onClick={handleReject}
                disabled={actionPending}
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-white dark:bg-gray-700 px-6 py-3 text-sm font-semibold text-gray-900 dark:text-gray-100 shadow-sm ring-1 ring-inset ring-gray-300 dark:ring-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gray-500 disabled:opacity-50"
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
                ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
            }`}
          >
            <div className="flex items-center gap-3">
              {actionDone === 'accepted' ? (
                <CheckIcon className="h-6 w-6 text-green-600 dark:text-green-400" aria-hidden="true" />
              ) : (
                <XMarkIcon className="h-6 w-6 text-red-600 dark:text-red-400" aria-hidden="true" />
              )}
              <div>
                <h3
                  className={`font-semibold ${
                    actionDone === 'accepted' ? 'text-green-800 dark:text-green-300' : 'text-red-800 dark:text-red-300'
                  }`}
                >
                  {actionDone === 'accepted'
                    ? 'Proposal Accepted'
                    : 'Proposal Rejected'}
                </h3>
                <p
                  className={`text-sm mt-1 ${
                    actionDone === 'accepted' ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'
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

      {/* Branded Footer */}
      <footer className="border-t border-gray-200 dark:border-gray-700 mt-12">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6 text-center text-sm text-gray-400 dark:text-gray-500">
          {branding.footer_text ? (
            <p className="mb-1">{branding.footer_text}</p>
          ) : null}
          <p>
            {companyDisplayName} &middot; {proposal.proposal_number}
          </p>
        </div>
      </footer>
    </div>
  );
}

export default PublicProposalView;
