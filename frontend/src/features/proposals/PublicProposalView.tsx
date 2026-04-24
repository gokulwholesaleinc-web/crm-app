import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import axios from 'axios';
import { sanitizeHexColor } from '../../utils/colorValidation';

// Bare axios instance for public (unauthenticated) proposal endpoints.
// Deliberately does NOT attach the CRM Bearer token or X-Tenant-Slug
// header — customers clicking a proposal link aren't logged in, and a
// 401 from this client should NOT wipe a CRM staff user's own session
// if they happen to preview their own link.
const publicClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '',
  headers: { 'Content-Type': 'application/json' },
  timeout: 30000,
});

interface ProposalBranding {
  company_name: string | null;
  logo_url: string | null;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  footer_text: string | null;
  privacy_policy_url: string | null;
  terms_of_service_url: string | null;
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
  payment_type: 'one_time' | 'subscription';
  recurring_interval: 'month' | 'year' | null;
  recurring_interval_count: number | null;
  amount: string | number | null;
  currency: string;
  stripe_payment_url: string | null;
  paid_at: string | null;
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
  privacy_policy_url: null,
  terms_of_service_url: null,
};

function PublicProposalView() {
  const { token } = useParams<{ token: string }>();
  const [proposal, setProposal] = useState<PublicProposal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [actionDone, setActionDone] = useState<'accepted' | 'rejected' | null>(null);
  const [logoError, setLogoError] = useState(false);
  const [signerName, setSignerName] = useState('');
  const [signerEmail, setSignerEmail] = useState('');
  const [signError, setSignError] = useState<string | null>(null);

  useEffect(() => {
    setLogoError(false);
  }, [proposal?.branding?.logo_url]);

  useEffect(() => {
    if (!token) return;

    const fetchProposal = async () => {
      try {
        const response = await publicClient.get<PublicProposal>(
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
    const name = signerName.trim();
    const email = signerEmail.trim();
    if (!name || !email) {
      setSignError('Please enter your full name and email address.');
      return;
    }
    setActionPending(true);
    setSignError(null);
    try {
      const response = await publicClient.post<PublicProposal>(
        `/api/proposals/public/${token}/accept`,
        { signer_name: name, signer_email: email },
      );
      // Replace the whole object — the accept response carries the
      // freshly-spawned payment_url + status (awaiting_payment) that
      // power the "Complete Payment" CTA below.
      setProposal(response.data);
      setActionDone('accepted');
    } catch (err) {
      // IMPORTANT: do NOT mark the proposal accepted on failure. Surface
      // the backend detail (e.g. "Signer email does not match...") so the
      // customer can correct it.
      const detail =
        (typeof err === 'object' && err !== null && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null) || 'Unable to record acceptance. Please contact your account manager.';
      setSignError(detail);
    } finally {
      setActionPending(false);
    }
  };

  const handleReject = async () => {
    if (!proposal) return;
    const email = signerEmail.trim();
    if (!email) {
      // Enforce the same signer-email gate accept has so a forwarded
      // link can't be used by a third party to permanently reject.
      setSignError('Please enter your email address to reject this proposal.');
      return;
    }
    setActionPending(true);
    setSignError(null);
    try {
      await publicClient.post(`/api/proposals/public/${token}/reject`, {
        signer_email: email,
      });
      setProposal((prev) => prev ? { ...prev, status: 'rejected' } : null);
      setActionDone('rejected');
    } catch (err) {
      const detail =
        (typeof err === 'object' && err !== null && 'response' in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null) || 'Unable to record rejection. Please contact your account manager.';
      setSignError(detail);
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

  const rawBranding = proposal.branding ?? DEFAULT_BRANDING;
  // Tenant branding colors come from the server as arbitrary strings. Strip
  // any value that isn't a strict hex color before it hits an inline
  // `style={{ backgroundColor: ... }}` — a malformed color otherwise gets
  // echoed into the DOM verbatim.
  const branding = {
    ...rawBranding,
    primary_color: sanitizeHexColor(rawBranding.primary_color, DEFAULT_BRANDING.primary_color),
    secondary_color: sanitizeHexColor(rawBranding.secondary_color, DEFAULT_BRANDING.secondary_color),
    accent_color: sanitizeHexColor(rawBranding.accent_color, DEFAULT_BRANDING.accent_color),
  };
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
            {branding.logo_url && !logoError ? (
              <img
                src={branding.logo_url}
                alt={companyDisplayName}
                width={36}
                height={36}
                className="rounded"
                style={{ maxHeight: 36 }}
                onError={() => setLogoError(true)}
              />
            ) : (
              <div
                className="h-9 w-9 rounded flex items-center justify-center flex-shrink-0"
                style={{ backgroundColor: branding.secondary_color }}
              >
                <span className="text-white font-bold text-lg">
                  {companyDisplayName[0]?.toUpperCase() || 'P'}
                </span>
              </div>
            )}
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
              Please review the proposal above and accept or reject it. Typing
              your name and email below and clicking Accept is your legally
              binding electronic signature (see the full e-signature disclosure
              at the bottom of this page).
            </p>
            <div className="grid gap-3 sm:grid-cols-2 mb-4">
              <div>
                <label
                  htmlFor="signer-name"
                  className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Full name
                </label>
                <input
                  id="signer-name"
                  type="text"
                  autoComplete="name"
                  value={signerName}
                  onChange={(e) => setSignerName(e.target.value)}
                  disabled={actionPending}
                  className="w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm px-3 py-2 shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                  style={{ outlineColor: branding.primary_color }}
                />
              </div>
              <div>
                <label
                  htmlFor="signer-email"
                  className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1"
                >
                  Email address
                </label>
                <input
                  id="signer-email"
                  type="email"
                  autoComplete="email"
                  inputMode="email"
                  spellCheck={false}
                  value={signerEmail}
                  onChange={(e) => setSignerEmail(e.target.value)}
                  disabled={actionPending}
                  className="w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm px-3 py-2 shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
                  style={{ outlineColor: branding.primary_color }}
                />
              </div>
            </div>
            {signError && (
              <p
                role="alert"
                aria-live="polite"
                className="mb-4 text-sm text-red-600 dark:text-red-400"
              >
                {signError}
              </p>
            )}
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

        {/* Payment CTA — rendered whenever the backend has spawned a
            Stripe Invoice or Checkout Session for this proposal. Uses a
            plain <a> so the browser follows the external Stripe URL
            without React Router intercepting it. */}
        {proposal.stripe_payment_url && proposal.status !== 'paid' && (
          <section
            className="rounded-lg p-6 sm:p-8 border"
            style={{
              backgroundColor: `${branding.accent_color}10`,
              borderColor: `${branding.accent_color}66`,
            }}
          >
            <h2
              className="text-lg font-semibold mb-2"
              style={{ color: branding.primary_color }}
            >
              {proposal.payment_type === 'subscription'
                ? 'Complete your subscription'
                : 'Complete payment'}
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-300 mb-4">
              {proposal.payment_type === 'subscription'
                ? 'Set up your payment method on Stripe to activate your subscription. You will be charged the first billing period when you finish checkout.'
                : 'An invoice has been issued. Pay securely on Stripe to finalize this engagement.'}
            </p>
            <a
              href={proposal.stripe_payment_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-lg px-6 py-3 text-sm font-semibold text-white shadow-sm hover:opacity-90"
              style={{ backgroundColor: branding.accent_color }}
            >
              {proposal.payment_type === 'subscription'
                ? 'Set up payment on Stripe'
                : 'Pay on Stripe'}
            </a>
          </section>
        )}

        {proposal.status === 'paid' && (
          <section className="rounded-lg p-6 sm:p-8 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800">
            <div className="flex items-center gap-3">
              <CheckIcon className="h-6 w-6 text-green-600 dark:text-green-400" aria-hidden="true" />
              <div>
                <h3 className="font-semibold text-green-800 dark:text-green-300">
                  Payment received
                </h3>
                <p className="text-sm mt-1 text-green-700 dark:text-green-400">
                  Thank you — your payment is confirmed. We will follow up shortly.
                </p>
              </div>
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
                    ? proposal.stripe_payment_url
                      ? 'Thanks! Use the payment button above to complete your transaction.'
                      : 'Thank you for accepting this proposal. We will be in touch shortly.'
                    : 'Thank you for your response. We appreciate your time.'}
                </p>
              </div>
            </div>
          </section>
        )}
      </main>

      {/* Branded Footer + Legal/Payment Disclosure
          Rendered at the bottom of every public proposal page. Shows:
          - ESIGN Act / UETA electronic signature disclosure (always,
            including for already-accepted proposals — acts as a
            signed-contract receipt for the record)
          - Tenant's footer text (optional)
          - Tenant's Terms of Service / Privacy Policy links when set
          - Stripe disclosure whenever a payment link is active (client
            is about to hand over payment info on Stripe's hosted page)
      */}
      <footer className="border-t border-gray-200 dark:border-gray-700 mt-12">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6 text-sm text-gray-500 dark:text-gray-400 space-y-4">
          <details className="rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/40 p-3 text-xs text-gray-600 dark:text-gray-400">
            <summary className="cursor-pointer font-medium text-gray-700 dark:text-gray-300">
              Electronic signature disclosure &amp; terms
            </summary>
            <div className="mt-2 space-y-2 leading-relaxed">
              <p>
                By typing your name and email and clicking <strong>Accept Proposal</strong>,
                you agree that this constitutes your legally binding electronic signature
                under the US ESIGN Act (15 USC §7001) and applicable state UETA statutes,
                with the same legal effect as a handwritten signature.
              </p>
              <p>
                You consent to receive this proposal and the countersigned PDF copy
                electronically. A signed copy is emailed to the address you provide at
                acceptance. You may withdraw consent by contacting {companyDisplayName}
                directly — this does not retroactively invalidate signatures already captured.
              </p>
              <p>
                We record your name, email address, IP address, browser user-agent, and
                timestamp at the moment you submit. This audit trail is retained alongside
                the proposal for dispute resolution.
              </p>
              <p>
                To sign, you need a modern web browser with JavaScript enabled and the ability
                to receive email at the address you provide. If any of these are unavailable,
                contact {companyDisplayName} to arrange an alternative signing method.
              </p>
            </div>
          </details>

          <div className="text-center">
            {branding.footer_text ? (
              <p className="mb-1">{branding.footer_text}</p>
            ) : null}
            <p>
              {companyDisplayName} &middot; {proposal.proposal_number}
            </p>
          </div>

          {(branding.terms_of_service_url || branding.privacy_policy_url) && (
            <nav
              aria-label="Legal"
              className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-xs"
            >
              {branding.terms_of_service_url && (
                <a
                  href={branding.terms_of_service_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-gray-700 dark:hover:text-gray-200"
                >
                  Terms of Service
                </a>
              )}
              {branding.privacy_policy_url && (
                <a
                  href={branding.privacy_policy_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-gray-700 dark:hover:text-gray-200"
                >
                  Privacy Policy
                </a>
              )}
            </nav>
          )}

          {proposal.stripe_payment_url && (
            <div className="text-center text-xs space-y-1">
              <p>
                Payments are processed securely by{' '}
                <a
                  href="https://stripe.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-gray-700 dark:hover:text-gray-200"
                >
                  Stripe
                </a>
                . {companyDisplayName} never sees or stores your card details.
              </p>
              <p className="space-x-3">
                <a
                  href="https://stripe.com/legal/consumer"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-gray-700 dark:hover:text-gray-200"
                >
                  Stripe Terms
                </a>
                <a
                  href="https://stripe.com/privacy"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline hover:text-gray-700 dark:hover:text-gray-200"
                >
                  Stripe Privacy
                </a>
              </p>
            </div>
          )}
        </div>
      </footer>
    </div>
  );
}

export default PublicProposalView;
