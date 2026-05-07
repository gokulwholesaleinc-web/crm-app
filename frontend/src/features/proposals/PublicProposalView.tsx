import { useState, useEffect, useMemo, useRef, useCallback, startTransition } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { CheckIcon, XMarkIcon } from '@heroicons/react/24/outline';
import axios from 'axios';
import { sanitizeHexColor } from '../../utils/colorValidation';
import { formatDate } from '../../utils/formatters';
import { cadenceLabel, formatProposalMoney } from './billing';
import { setPublicPageMeta } from '../quotes/publicMeta';
import { ProposalAttachmentsSection } from './ProposalAttachmentsSection';
import type { ProposalAttachmentPublic } from '../../types';

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
  attachments?: ProposalAttachmentPublic[];
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

// Poll cadence for the post-Stripe `?paid=1` return state. Stripe's
// webhook normally arrives within a few seconds of checkout success;
// we cap polling at ~30s and fall back to a "processing" message if the
// webhook is slow.
const PAID_POLL_INTERVAL_MS = 3000;
const PAID_POLL_TIMEOUT_MS = 30000;

function PublicProposalView() {
  const { token } = useParams<{ token: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const paidFlag = searchParams.get('paid') === '1';
  const [proposal, setProposal] = useState<PublicProposal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [actionDone, setActionDone] = useState<'accepted' | 'rejected' | null>(null);
  const [logoError, setLogoError] = useState(false);
  const [signerName, setSignerName] = useState('');
  const [signerEmail, setSignerEmail] = useState('');
  const [signError, setSignError] = useState<string | null>(null);
  const [confirmingPayment, setConfirmingPayment] = useState(false);
  const [paymentTimedOut, setPaymentTimedOut] = useState(false);
  // Tracks which attachment IDs the customer has opened on this device.
  // Seeded from the public response (server-side `viewed` flag) the first
  // time we see the proposal so a returning customer doesn't have to
  // re-open every PDF. Subsequent opens are added optimistically inside
  // a transition — the next polled refetch may also flip `viewed`, but
  // local state is the source of truth for the gate.
  const [viewedIds, setViewedIds] = useState<Set<number>>(() => new Set());
  const seededViewedIdsRef = useRef(false);
  const paySectionRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    setLogoError(false);
  }, [proposal?.branding?.logo_url]);

  const proposalTitle = proposal?.title;
  const proposalBrandingCompanyName = proposal?.branding?.company_name;
  useEffect(() => {
    if (!proposalTitle) return;
    const company = proposalBrandingCompanyName ?? 'Proposal';
    const title = `${proposalTitle} — ${company}`;
    const previous = document.title;
    document.title = title;
    const restoreMeta = setPublicPageMeta({
      title,
      description: `Proposal from ${company}.`,
      type: 'article',
      canonicalUrl: window.location.href,
    });
    return () => {
      document.title = previous;
      restoreMeta();
    };
  }, [proposalTitle, proposalBrandingCompanyName]);

  const fetchProposal = useCallback(async () => {
    if (!token) return;
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
  }, [token]);

  useEffect(() => {
    fetchProposal();
  }, [fetchProposal]);

  // One-shot seed of viewedIds from the server-side `viewed` flag the
  // first time the proposal lands. Guarded by a ref so the periodic poll
  // (which replaces `proposal` with a fresh response) never overwrites
  // the customer's locally-clicked attachments.
  useEffect(() => {
    if (!proposal || seededViewedIdsRef.current) return;
    seededViewedIdsRef.current = true;
    const initial = (proposal.attachments ?? [])
      .filter((a) => a.viewed)
      .map((a) => a.id);
    if (initial.length > 0) {
      setViewedIds(new Set(initial));
    }
  }, [proposal]);

  // After acceptance lands, scroll the Pay block into view so the customer
  // doesn't have to hunt for the next step.
  useEffect(() => {
    if (actionDone === 'accepted' && proposal?.stripe_payment_url && paySectionRef.current) {
      paySectionRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [actionDone, proposal?.stripe_payment_url]);

  // Stripe Checkout success_url returns the customer here with `?paid=1`.
  // The webhook usually flips status → 'paid' within a few seconds, but
  // there's a race window. While the proposal is still pre-paid, show a
  // "confirming…" state and poll the public endpoint until either the
  // status flips or we time out (then we fall back to a generic
  // "processing" notice). The query param is stripped from the URL after
  // handling so a refresh doesn't restart the poll.
  useEffect(() => {
    if (!proposal || !paidFlag || !token) return;

    const stripPaidParam = () => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.delete('paid');
          return next;
        },
        { replace: true },
      );
    };

    if (proposal.status === 'paid') {
      stripPaidParam();
      return;
    }

    setConfirmingPayment(true);
    setPaymentTimedOut(false);

    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    const startedAt = Date.now();

    const tick = async () => {
      try {
        const response = await publicClient.get<PublicProposal>(
          `/api/proposals/public/${token}`,
        );
        if (cancelled) return;
        if (response.data.status === 'paid') {
          setProposal(response.data);
          setConfirmingPayment(false);
          stripPaidParam();
          return;
        }
      } catch {
        // Transient network error — retry on next tick.
      }
      if (cancelled) return;
      if (Date.now() - startedAt >= PAID_POLL_TIMEOUT_MS) {
        setConfirmingPayment(false);
        setPaymentTimedOut(true);
        stripPaidParam();
        return;
      }
      timeoutId = setTimeout(tick, PAID_POLL_INTERVAL_MS);
    };

    timeoutId = setTimeout(tick, PAID_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (timeoutId !== null) clearTimeout(timeoutId);
    };
    // setSearchParams is stable from react-router; intentionally excluded
    // to keep the poll from restarting when its identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proposal, paidFlag, token]);

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
        <div role="status" aria-label="Loading proposal…" className="animate-pulse text-center">
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
  const primary = branding.primary_color;
  const secondary = branding.secondary_color;
  const accent = branding.accent_color;

  const isExpired =
    proposal.valid_until &&
    new Date(proposal.valid_until) < new Date();

  const attachments = proposal.attachments ?? [];
  const allAttachmentsViewed =
    attachments.length === 0 || attachments.every((a) => viewedIds.has(a.id));

  const handleAttachmentViewed = (id: number) => {
    // startTransition so flipping the gate doesn't block the click
    // handler, and so the larger Sign-form re-render is treated as
    // non-urgent (the new tab opening is the urgent feedback).
    startTransition(() => {
      setViewedIds((curr) => {
        if (curr.has(id)) return curr;
        const next = new Set(curr);
        next.add(id);
        return next;
      });
    });
  };

  const canRespond =
    (proposal.status === 'sent' || proposal.status === 'viewed') &&
    !isExpired &&
    !actionDone &&
    allAttachmentsViewed;

  // Polite notice the customer sees while the gate is still closed —
  // only meaningful in sent/viewed status (anything else hides the
  // sign form anyway, so the message would be misleading).
  const showAttachmentGateNotice =
    !allAttachmentsViewed &&
    !actionDone &&
    (proposal.status === 'sent' || proposal.status === 'viewed') &&
    !isExpired;

  const validUntilDate = proposal.valid_until
    ? formatDate(proposal.valid_until, 'long')
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
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 text-gray-900 dark:text-gray-100 antialiased">
      <div
        aria-hidden="true"
        style={{
          height: 4,
          backgroundImage: `linear-gradient(90deg, ${primary}, ${secondary}, ${accent})`,
        }}
      />
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
                width={180}
                height={30}
                className="object-contain"
                style={{ height: 30, width: 'auto', maxWidth: 180 }}
                onError={() => setLogoError(true)}
              />
            ) : (
              <>
                <div
                  className="h-8 w-8 rounded flex items-center justify-center flex-shrink-0 text-white text-sm font-semibold"
                  style={{ backgroundColor: primary }}
                >
                  {companyDisplayName[0]?.toUpperCase() || 'P'}
                </div>
                <span className="text-[15px] font-semibold text-gray-900 dark:text-gray-100 truncate">
                  {companyDisplayName}
                </span>
              </>
            )}
          </div>
          <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
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
        <section className="pb-8 border-b border-gray-200 dark:border-gray-700">
          <p className="text-xs uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-3">
            Proposal <span className="text-gray-300 dark:text-gray-600 mx-1">·</span>
            <span className="tabular-nums">{proposal.proposal_number}</span>
          </p>
          <h1 className="text-3xl sm:text-4xl font-semibold text-gray-900 dark:text-gray-100 leading-tight tracking-tight text-balance">
            {proposal.title}
          </h1>
          {proposal.contact && (
            <p className="mt-3 text-[15px] text-gray-600 dark:text-gray-300">
              Prepared for <span className="font-medium text-gray-900 dark:text-gray-100">{proposal.contact.full_name}</span>
              {proposal.company && proposal.company.name !== companyDisplayName && (
                <span className="text-gray-500 dark:text-gray-400"> · {proposal.company.name}</span>
              )}
            </p>
          )}
          {validUntilDate && (
            <p className={`mt-2 text-sm ${isExpired ? 'text-red-600 dark:text-red-400 font-medium' : 'text-gray-500 dark:text-gray-400'}`}>
              {isExpired ? 'Expired ' : 'Valid until '}
              <span className="tabular-nums">{validUntilDate}</span>
            </p>
          )}
        </section>

        {/* Cover letter — flowing prose, no box */}
        {proposal.cover_letter && (
          <section className="mt-8">
            <p className="text-[15px] leading-[1.7] text-gray-700 dark:text-gray-300 whitespace-pre-wrap text-pretty break-words">
              {proposal.cover_letter}
            </p>
          </section>
        )}

        {contentSections.map((section) => (
          <section key={section.title} className="mt-10 sm:mt-12">
            <PlainSectionHeader title={section.title} accent={primary} />
            <div className="prose-body">
              <p className="whitespace-pre-wrap text-pretty break-words">
                {section.body}
              </p>
            </div>
          </section>
        ))}

        {token && (
          <ProposalAttachmentsSection
            attachments={attachments}
            token={token}
            accent={primary}
            viewedIds={viewedIds}
            onViewed={handleAttachmentViewed}
            onReconcile={fetchProposal}
          />
        )}

        {/* Pricing — highlighted block, business-standard */}
        {hasPricingBlock && (
          <section className="mt-10 sm:mt-12">
            <PlainSectionHeader
              title={proposal.payment_type === 'subscription' ? 'Engagement & Fees' : 'Fees'}
              accent={primary}
            />

            {formattedAmount && (
              <div
                className="rounded-lg border p-5 mb-4 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3"
                style={{ borderColor: `${secondary}40`, backgroundColor: `${secondary}14` }}
              >
                <div>
                  <div className="text-xs uppercase tracking-wider text-gray-500 dark:text-gray-400 mb-1">
                    {proposal.payment_type === 'subscription' ? 'Recurring fee' : 'Total'}
                  </div>
                  <div
                    className="text-3xl sm:text-4xl font-semibold text-gray-900 dark:text-gray-100 tabular-nums"
                    style={{ letterSpacing: '-0.01em' }}
                  >
                    {formattedAmount}
                  </div>
                </div>
                {cadence && (
                  <div className="text-sm text-gray-600 dark:text-gray-300">
                    billed <span className="font-medium text-gray-900 dark:text-gray-100">{cadence.toLowerCase()}</span>
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
              <PlainSectionHeader title="Proposal" accent={primary} />
              <div className="prose-body">
                <p className="whitespace-pre-wrap text-pretty break-words">
                  {proposal.content}
                </p>
              </div>
            </section>
          )}

        {/* Confirming payment — shown after Stripe Checkout success_url
            redirect while we wait for the webhook to flip status → paid */}
        {confirmingPayment && proposal.status !== 'paid' && (
          <section
            className="mt-10 sm:mt-12 rounded border px-5 py-4"
            style={{ borderColor: `${primary}40`, backgroundColor: `${primary}0a` }}
            role="status"
            aria-live="polite"
          >
            <div className="flex items-center gap-3">
              <span
                className="inline-block h-4 w-4 rounded-full border-2 border-t-transparent animate-spin"
                style={{ borderColor: primary, borderTopColor: 'transparent' }}
                aria-hidden="true"
              />
              <div>
                <p className="font-semibold text-gray-900 dark:text-gray-100">Confirming your payment…</p>
                <p className="text-sm text-gray-700 dark:text-gray-300 mt-0.5">
                  Stripe is finalizing the transaction. This usually takes a few
                  seconds.
                </p>
              </div>
            </div>
          </section>
        )}

        {/* Timed-out — webhook didn't arrive within the poll window. Tell
            the customer their payment is still being processed and
            they'll get an email when it lands. */}
        {paymentTimedOut && proposal.status !== 'paid' && (
          <section
            className="mt-10 sm:mt-12 rounded border border-amber-200 bg-amber-50 px-5 py-4"
            role="status"
            aria-live="polite"
          >
            <div className="flex items-start gap-2.5">
              <CheckIcon className="h-5 w-5 text-amber-700 flex-shrink-0 mt-0.5" aria-hidden="true" />
              <div>
                <p className="font-semibold text-amber-900">Payment is processing</p>
                <p className="text-sm text-amber-800 mt-0.5">
                  Thanks — Stripe has received your payment. We'll email a
                  receipt to {proposal.contact?.full_name ? 'you' : 'the address you used at checkout'} once
                  it's finalized. You can safely close this page.
                </p>
              </div>
            </div>
          </section>
        )}

        {/* Payment CTA — hidden while we're confirming a fresh return so
            the customer can't accidentally click pay twice. */}
        {proposal.stripe_payment_url &&
          proposal.status !== 'paid' &&
          !confirmingPayment &&
          !paymentTimedOut && (
            <section className="mt-10 sm:mt-12" ref={paySectionRef}>
              <PlainSectionHeader title="Payment" accent={primary} />
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

        {/* Sign gate notice — visible while attachments still need to be
            opened. The Accept/Decline form below is fully suppressed
            until the gate clears (canRespond folds in
            allAttachmentsViewed). */}
        {showAttachmentGateNotice && (
          <section
            className="mt-10 sm:mt-12 rounded border border-amber-200 bg-amber-50 px-5 py-4"
            role="status"
            aria-live="polite"
          >
            <p className="text-sm text-amber-900">
              You must open and read all attached documents before you can sign this proposal.
            </p>
          </section>
        )}

        {/* Accept / Decline form — standard business form layout */}
        {canRespond && (
          <section className="mt-10 sm:mt-12">
            <PlainSectionHeader title="Your Response" accent={primary} />
            <p className="prose-body mb-5">
              Please review the proposal above and accept or decline. Your typed name and
              email below constitute your legally binding electronic signature (full
              disclosure at the bottom of this page).
            </p>

            <div className="grid gap-4 sm:grid-cols-2 mb-4">
              <div>
                <label
                  htmlFor="signer-name"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
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
                  className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-gray-100 px-3 py-2 shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 disabled:opacity-50"
                  style={{ outlineColor: primary }}
                />
              </div>
              <div>
                <label
                  htmlFor="signer-email"
                  className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
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
                  className="w-full rounded border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-gray-100 px-3 py-2 shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 disabled:opacity-50"
                  style={{ outlineColor: primary }}
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
                className="inline-flex items-center justify-center gap-2 rounded px-5 py-2.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 shadow-sm hover:bg-gray-50 dark:hover:bg-gray-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-gray-400 disabled:opacity-50"
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
            role="status"
            aria-live="polite"
            className={`mt-10 rounded border px-5 py-4 ${
              actionDone === 'accepted'
                ? 'border-green-200 bg-green-50'
                : 'border-red-200 bg-red-50'
            }`}
          >
            <div className="flex items-center gap-2.5">
              {actionDone === 'accepted' ? (
                <CheckIcon className="h-5 w-5 text-green-700" aria-hidden="true" />
              ) : (
                <XMarkIcon className="h-5 w-5 text-red-600 dark:text-red-400" aria-hidden="true" />
              )}
              <div>
                <p className={`font-semibold ${actionDone === 'accepted' ? 'text-green-900 dark:text-green-300' : 'text-red-900 dark:text-red-300'}`}>
                  {actionDone === 'accepted' ? 'Proposal accepted' : 'Proposal declined'}
                </p>
                <p className={`text-sm mt-0.5 ${actionDone === 'accepted' ? 'text-green-800 dark:text-green-400' : 'text-red-700 dark:text-red-400'}`}>
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

      {/* Fine-print legal footer — ESIGN disclosure always visible. Pads
          with safe-area-inset-bottom so iPhone home indicator doesn't overlap
          the disclosure text (requires viewport-fit=cover in index.html). */}
      <footer
        className="mt-16 bg-white dark:bg-gray-900 border-t border-gray-200 dark:border-gray-700"
        style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        <div className="mx-auto max-w-3xl px-6 sm:px-10 py-8 space-y-5">
          <details className="group text-sm">
            <summary className="cursor-pointer text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 list-none flex items-center gap-2 select-none">
              <span aria-hidden="true" className="inline-block transition-transform group-open:rotate-90">
                ▸
              </span>
              Electronic signature disclosure &amp; consent
            </summary>
            <div className="mt-3 space-y-2 text-[13px] leading-relaxed text-gray-600 dark:text-gray-400 text-pretty">
              <p>
                By typing your name and email and selecting <em>Accept &amp; Sign</em>, you confirm
                that you have read all attached documents and the proposal above, and you
                agree that this constitutes your legally binding electronic signature under the
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

          <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4 pt-4 border-t border-gray-200 dark:border-gray-700">
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">{companyDisplayName}</p>
              {branding.footer_text && (
                <p className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed max-w-sm">
                  {branding.footer_text}
                </p>
              )}
              <p className="text-xs text-gray-400 dark:text-gray-500 tabular-nums mt-1">
                {proposal.proposal_number}
              </p>
            </div>

            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
              {branding.terms_of_service_url && (
                <a
                  href={branding.terms_of_service_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-gray-700 dark:hover:text-gray-200"
                >
                  Terms of Service
                </a>
              )}
              {branding.privacy_policy_url && (
                <a
                  href={branding.privacy_policy_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-gray-700 dark:hover:text-gray-200"
                >
                  Privacy Policy
                </a>
              )}
            </div>
          </div>

          {proposal.stripe_payment_url && (
            <div className="pt-4 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400 leading-relaxed">
              <p>
                Payments processed securely by{' '}
                <a href="https://stripe.com" target="_blank" rel="noopener noreferrer" className="underline hover:text-gray-700 dark:hover:text-gray-200">
                  Stripe
                </a>
                . {companyDisplayName} never sees or stores your card details.{' '}
                <a href="https://stripe.com/legal/consumer" target="_blank" rel="noopener noreferrer" className="underline hover:text-gray-700 dark:hover:text-gray-200">
                  Stripe Terms
                </a>
                {' · '}
                <a href="https://stripe.com/privacy" target="_blank" rel="noopener noreferrer" className="underline hover:text-gray-700 dark:hover:text-gray-200">
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
        .dark .prose-body {
          color: rgb(209 213 219);
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
      <h2 className="text-xl font-semibold text-gray-900 dark:text-gray-100 tracking-tight">
        {title}
      </h2>
    </div>
  );
}

export default PublicProposalView;
