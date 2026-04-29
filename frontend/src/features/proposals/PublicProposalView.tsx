import { useState, useEffect, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import axios from 'axios';
import { sanitizeHexColor } from '../../utils/colorValidation';
import { cadenceLabel, formatProposalMoney } from './billing';

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

  // Hook must run unconditionally (rules-of-hooks) so it sits before
  // the loading/error early returns below and guards against a null
  // proposal inside the callback.
  const contentSections = useMemo(() => {
    if (!proposal) return [];
    const raw: Array<{ title: string; body: string } | null> = [
      proposal.executive_summary ? { title: 'Executive Summary', body: proposal.executive_summary } : null,
      proposal.scope_of_work ? { title: 'Scope of Work', body: proposal.scope_of_work } : null,
      proposal.timeline ? { title: 'Timeline', body: proposal.timeline } : null,
      proposal.terms ? { title: 'Terms & Conditions', body: proposal.terms } : null,
    ];
    return raw.filter((s): s is { title: string; body: string } => s !== null);
  }, [proposal]);

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
      // Replace the whole object — accept response carries the
      // freshly-spawned payment_url + status.
      setProposal(response.data);
      setActionDone('accepted');
    } catch (err) {
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
      // Same signer-email gate as accept so a forwarded link can't be
      // used by a third party to permanently reject.
      setSignError('Please enter your email address to decline this proposal.');
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
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div className="animate-pulse text-center">
          <div className="h-7 w-40 bg-gray-200 rounded mx-auto mb-3" />
          <div className="h-3 w-24 bg-gray-200 rounded mx-auto" />
        </div>
      </div>
    );
  }

  if (error || !proposal) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center px-6">
        <div className="text-center max-w-md">
          <h1 className="text-2xl font-semibold text-gray-900 mb-2">Proposal not found</h1>
          <p className="text-sm text-gray-500 leading-relaxed">
            {error || 'This proposal may have been withdrawn or the link is no longer valid. Please contact your account manager.'}
          </p>
        </div>
      </div>
    );
  }

  const rawBranding = proposal.branding ?? DEFAULT_BRANDING;
  const branding = {
    ...rawBranding,
    primary_color: sanitizeHexColor(rawBranding.primary_color, DEFAULT_BRANDING.primary_color),
    secondary_color: sanitizeHexColor(rawBranding.secondary_color, DEFAULT_BRANDING.secondary_color),
    accent_color: sanitizeHexColor(rawBranding.accent_color, DEFAULT_BRANDING.accent_color),
  };
  const companyDisplayName = branding.company_name || proposal.company?.name || 'Proposal';
  const accent = branding.primary_color;

  const isExpired =
    proposal.valid_until &&
    new Date(proposal.valid_until) < new Date();

  const canRespond =
    (proposal.status === 'sent' || proposal.status === 'viewed') &&
    !isExpired &&
    !actionDone;

  const validUntilDate = proposal.valid_until
    ? new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
        .format(new Date(proposal.valid_until))
    : null;

  const formattedAmount = formatProposalMoney(proposal.amount, proposal.currency);
  const cadence = proposal.payment_type === 'subscription'
    ? cadenceLabel(proposal.recurring_interval, proposal.recurring_interval_count)
    : null;
  const hasPricingBlock = Boolean(formattedAmount || proposal.pricing_section);

  const statusPill = actionDone ?? (
    proposal.status === 'accepted' ? 'accepted'
    : proposal.status === 'rejected' ? 'rejected'
    : proposal.status === 'paid' ? 'paid'
    : null
  );

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 antialiased">
      {/* Letterhead — plain, light, business-document feel. Text label
          is dropped when a logo image is present to avoid the "logo
          wordmark + typed company name" duplication. */}
      <header className="bg-white border-b border-gray-200">
        <div className="mx-auto max-w-3xl px-6 sm:px-10 py-4 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            {branding.logo_url && !logoError ? (
              <img
                src={branding.logo_url}
                alt={companyDisplayName}
                height={30}
                className="object-contain"
                style={{ height: 30, width: 'auto', maxWidth: 180 }}
                onError={() => setLogoError(true)}
              />
            ) : (
              <>
                <div
                  className="h-8 w-8 rounded flex items-center justify-center flex-shrink-0 text-white text-sm font-semibold"
                  style={{ backgroundColor: accent }}
                >
                  {companyDisplayName[0]?.toUpperCase() || 'P'}
                </div>
                <span className="text-[15px] font-semibold text-gray-900 truncate">
                  {companyDisplayName}
                </span>
              </>
            )}
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-500">
            <span className="tabular-nums">{proposal.proposal_number}</span>
            {statusPill && (
              <span
                className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium border"
                style={
                  statusPill === 'rejected'
                    ? { color: '#b91c1c', backgroundColor: '#fef2f2', borderColor: '#fecaca' }
                    : { color: accent, backgroundColor: `${accent}0f`, borderColor: `${accent}40` }
                }
              >
                {statusPill === 'paid' ? 'Paid' : statusPill === 'accepted' ? 'Accepted' : 'Declined'}
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 sm:px-10 py-10 sm:py-14">
        {/* Cover — standard business document style, left-aligned,
            restrained. */}
        <section className="pb-8 border-b border-gray-200">
          <p className="text-xs uppercase tracking-wider text-gray-500 mb-3">
            Proposal <span className="text-gray-300 mx-1">·</span>
            <span className="tabular-nums">{proposal.proposal_number}</span>
          </p>
          <h1 className="text-3xl sm:text-4xl font-semibold text-gray-900 leading-tight tracking-tight text-balance">
            {proposal.title}
          </h1>
          {proposal.contact && (
            <p className="mt-3 text-[15px] text-gray-600">
              Prepared for <span className="font-medium text-gray-900">{proposal.contact.full_name}</span>
              {proposal.company && proposal.company.name !== companyDisplayName && (
                <span className="text-gray-500"> · {proposal.company.name}</span>
              )}
            </p>
          )}
          {validUntilDate && (
            <p className={`mt-2 text-sm ${isExpired ? 'text-red-600 font-medium' : 'text-gray-500'}`}>
              {isExpired ? 'Expired ' : 'Valid until '}
              <span className="tabular-nums">{validUntilDate}</span>
            </p>
          )}
        </section>

        {/* Cover letter — flowing prose, no box */}
        {proposal.cover_letter && (
          <section className="mt-8">
            <p className="text-[15px] leading-[1.7] text-gray-700 whitespace-pre-wrap text-pretty break-words">
              {proposal.cover_letter}
            </p>
          </section>
        )}

        {contentSections.map((section) => (
          <section key={section.title} className="mt-10 sm:mt-12">
            <PlainSectionHeader title={section.title} accent={accent} />
            <div className="prose-body">
              <p className="whitespace-pre-wrap text-pretty break-words">
                {section.body}
              </p>
            </div>
          </section>
        ))}

        {/* Pricing — highlighted block, business-standard */}
        {hasPricingBlock && (
          <section className="mt-10 sm:mt-12">
            <PlainSectionHeader
              title={proposal.payment_type === 'subscription' ? 'Engagement & Fees' : 'Fees'}
              accent={accent}
            />

            {formattedAmount && (
              <div
                className="rounded border px-6 py-5 mb-4 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3"
                style={{ borderColor: `${accent}40`, backgroundColor: `${accent}0a` }}
              >
                <div>
                  <div className="text-xs uppercase tracking-wider text-gray-500 mb-1">
                    {proposal.payment_type === 'subscription' ? 'Recurring fee' : 'Total'}
                  </div>
                  <div
                    className="text-3xl sm:text-4xl font-semibold text-gray-900 tabular-nums"
                    style={{ letterSpacing: '-0.01em' }}
                  >
                    {formattedAmount}
                  </div>
                </div>
                {cadence && (
                  <div className="text-sm text-gray-600">
                    billed <span className="font-medium text-gray-900">{cadence.toLowerCase()}</span>
                  </div>
                )}
              </div>
            )}

            {proposal.pricing_section && (
              <div className="prose-body">
                <p className="whitespace-pre-wrap text-pretty break-words">
                  {proposal.pricing_section}
                </p>
              </div>
            )}
          </section>
        )}

        {/* Content fallback */}
        {proposal.content &&
          contentSections.length === 0 &&
          !hasPricingBlock && (
            <section className="mt-10 sm:mt-12">
              <PlainSectionHeader title="Proposal" accent={accent} />
              <div className="prose-body">
                <p className="whitespace-pre-wrap text-pretty break-words">
                  {proposal.content}
                </p>
              </div>
            </section>
          )}

        {/* Payment CTA */}
        {proposal.stripe_payment_url && proposal.status !== 'paid' && (
          <section className="mt-10 sm:mt-12">
            <PlainSectionHeader title="Payment" accent={accent} />
            <p className="prose-body mb-5">
              {proposal.payment_type === 'subscription'
                ? `Set up your payment method with ${companyDisplayName} via Stripe to activate your subscription. The first billing period will be charged upon checkout completion.`
                : `An invoice has been issued. Complete payment securely via Stripe to confirm this engagement.`}
            </p>
            <a
              href={proposal.stripe_payment_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 transition-opacity"
              style={{ backgroundColor: accent, outlineColor: accent }}
            >
              {proposal.payment_type === 'subscription'
                ? 'Complete payment setup'
                : 'Pay invoice on Stripe'}
              <span aria-hidden="true">→</span>
            </a>
          </section>
        )}

        {proposal.status === 'paid' && (
          <section className="mt-10 sm:mt-12 rounded border border-green-200 bg-green-50 px-5 py-4">
            <div className="flex items-center gap-2.5">
              <CheckIcon className="h-5 w-5 text-green-700" aria-hidden="true" />
              <div>
                <p className="font-semibold text-green-900">Payment received</p>
                <p className="text-sm text-green-800 mt-0.5">
                  Your payment is confirmed. A receipt has been sent to your email.
                </p>
              </div>
            </div>
          </section>
        )}

        {/* Accept / Decline form — standard business form layout */}
        {canRespond && (
          <section className="mt-10 sm:mt-12">
            <PlainSectionHeader title="Your Response" accent={accent} />
            <p className="prose-body mb-5">
              Please review the proposal above and accept or decline. Your typed name and
              email below constitute your legally binding electronic signature (full
              disclosure at the bottom of this page).
            </p>

            <div className="grid gap-4 sm:grid-cols-2 mb-4">
              <div>
                <label
                  htmlFor="signer-name"
                  className="block text-sm font-medium text-gray-700 mb-1"
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
                  className="w-full rounded border border-gray-300 bg-white text-sm px-3 py-2 shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 disabled:opacity-50"
                  style={{ outlineColor: accent }}
                />
              </div>
              <div>
                <label
                  htmlFor="signer-email"
                  className="block text-sm font-medium text-gray-700 mb-1"
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
                  className="w-full rounded border border-gray-300 bg-white text-sm px-3 py-2 shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 disabled:opacity-50"
                  style={{ outlineColor: accent }}
                />
              </div>
            </div>

            {signError && (
              <p
                role="alert"
                aria-live="polite"
                className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2"
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
                className="inline-flex items-center justify-center gap-2 rounded px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50 transition-opacity"
                style={{ backgroundColor: accent, outlineColor: accent }}
              >
                <CheckIcon className="h-4 w-4" aria-hidden="true" />
                {actionPending ? 'Recording…' : 'Accept & Sign'}
              </button>
              <button
                type="button"
                aria-label="Decline this proposal"
                onClick={handleReject}
                disabled={actionPending}
                className="inline-flex items-center justify-center gap-2 rounded px-5 py-2.5 text-sm font-medium text-gray-700 bg-white border border-gray-300 shadow-sm hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gray-400 disabled:opacity-50"
              >
                <XMarkIcon className="h-4 w-4" aria-hidden="true" />
                Decline
              </button>
            </div>
          </section>
        )}

        {/* Post-action confirmation */}
        {actionDone && (
          <section
            className={`mt-10 rounded border px-5 py-4 ${
              actionDone === 'accepted'
                ? 'border-green-200 bg-green-50'
                : 'border-gray-200 bg-gray-50'
            }`}
          >
            <div className="flex items-center gap-2.5">
              {actionDone === 'accepted' ? (
                <CheckIcon className="h-5 w-5 text-green-700" aria-hidden="true" />
              ) : (
                <XMarkIcon className="h-5 w-5 text-gray-600" aria-hidden="true" />
              )}
              <div>
                <p className={`font-semibold ${actionDone === 'accepted' ? 'text-green-900' : 'text-gray-900'}`}>
                  {actionDone === 'accepted' ? 'Proposal accepted' : 'Proposal declined'}
                </p>
                <p className={`text-sm mt-0.5 ${actionDone === 'accepted' ? 'text-green-800' : 'text-gray-600'}`}>
                  {actionDone === 'accepted'
                    ? proposal.stripe_payment_url
                      ? 'Thanks — please complete payment above to finalize this engagement.'
                      : `Thank you. ${companyDisplayName} will be in touch shortly with next steps.`
                    : 'Thank you for your response. We appreciate your consideration.'}
                </p>
              </div>
            </div>
          </section>
        )}
      </main>

      {/* Fine-print legal footer — ESIGN disclosure always visible */}
      <footer className="mt-16 bg-white border-t border-gray-200">
        <div className="mx-auto max-w-3xl px-6 sm:px-10 py-8 space-y-5">
          <details className="text-sm">
            <summary className="cursor-pointer text-sm font-medium text-gray-700 hover:text-gray-900 list-none flex items-center gap-2 select-none">
              <span aria-hidden="true" className="inline-block transition-transform group-open:rotate-90">
                ▸
              </span>
              Electronic signature disclosure &amp; consent
            </summary>
            <div className="mt-3 space-y-2 text-[13px] leading-relaxed text-gray-600 text-pretty">
              <p>
                By typing your name and email and selecting <em>Accept &amp; Sign</em>, you agree
                that this constitutes your legally binding electronic signature under the
                US ESIGN Act (15 USC §7001) and applicable state UETA statutes, with the
                same legal effect as a handwritten signature.
              </p>
              <p>
                You consent to receive this proposal and the countersigned PDF copy
                electronically. A signed copy is emailed to the address you provide at
                acceptance. You may withdraw consent by contacting {companyDisplayName}
                directly — this does not retroactively invalidate signatures already captured.
              </p>
              <p>
                We record your name, email address, IP address, browser user-agent, and
                timestamp at submission. This audit trail is retained alongside the
                proposal for dispute resolution.
              </p>
            </div>
          </details>

          <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 pt-4 border-t border-gray-200">
            <div>
              <p className="text-sm font-semibold text-gray-900">{companyDisplayName}</p>
              {branding.footer_text && (
                <p className="text-xs text-gray-500 leading-relaxed max-w-sm">
                  {branding.footer_text}
                </p>
              )}
              <p className="text-xs text-gray-400 tabular-nums mt-1">
                {proposal.proposal_number}
              </p>
            </div>

            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
              {branding.terms_of_service_url && (
                <a
                  href={branding.terms_of_service_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-gray-700"
                >
                  Terms of Service
                </a>
              )}
              {branding.privacy_policy_url && (
                <a
                  href={branding.privacy_policy_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-gray-700"
                >
                  Privacy Policy
                </a>
              )}
            </div>
          </div>

          {proposal.stripe_payment_url && (
            <div className="pt-4 border-t border-gray-200 text-xs text-gray-500 leading-relaxed">
              <p>
                Payments processed securely by{' '}
                <a href="https://stripe.com" target="_blank" rel="noopener noreferrer" className="underline hover:text-gray-700">
                  Stripe
                </a>
                . {companyDisplayName} never sees or stores your card details.{' '}
                <a href="https://stripe.com/legal/consumer" target="_blank" rel="noopener noreferrer" className="underline hover:text-gray-700">
                  Stripe Terms
                </a>
                {' · '}
                <a href="https://stripe.com/privacy" target="_blank" rel="noopener noreferrer" className="underline hover:text-gray-700">
                  Stripe Privacy
                </a>
              </p>
            </div>
          )}
        </div>
      </footer>

      <style>{`
        .prose-body {
          font-size: 15px;
          line-height: 1.7;
          color: rgb(55 65 81);
          max-width: 62ch;
        }
        .prose-body p { margin: 0; }
        details > summary::-webkit-details-marker { display: none; }
      `}</style>
    </div>
  );
}

// -----------------------------------------------------------------
// Local components
// -----------------------------------------------------------------

interface PlainSectionHeaderProps {
  title: string;
  accent: string;
}

function PlainSectionHeader({ title, accent }: PlainSectionHeaderProps) {
  return (
    <div className="mb-4">
      <div
        className="h-0.5 w-8 mb-3"
        style={{ backgroundColor: accent }}
        aria-hidden="true"
      />
      <h2 className="text-xl font-semibold text-gray-900 tracking-tight">
        {title}
      </h2>
    </div>
  );
}

export default PublicProposalView;
