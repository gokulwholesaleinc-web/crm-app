import { useState, useEffect, useMemo } from 'react';
import { useParams } from 'react-router-dom';
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

// Cadence labels shared with BillingTermsField / ProposalBillingCard so
// the public page speaks the same language as the CRM admin form.
const CADENCE_LABEL: Record<string, string> = {
  'month-1': 'Monthly',
  'month-3': 'Quarterly',
  'month-6': 'Bi-yearly',
  'year-1': 'Yearly',
};

function cadenceOf(interval: string | null | undefined, count: number | null | undefined): string {
  if (!interval) return '';
  const key = `${interval}-${count ?? 1}`;
  return CADENCE_LABEL[key] || `Every ${count ?? 1} ${interval}${(count ?? 1) > 1 ? 's' : ''}`;
}

function formatMoney(amount: string | number | null | undefined, currency: string): string | null {
  if (amount == null || amount === '') return null;
  const num = typeof amount === 'string' ? Number(amount) : amount;
  if (!Number.isFinite(num)) return null;
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency, minimumFractionDigits: 2 }).format(num);
  } catch {
    // Falls through for non-ISO currency strings (shouldn't happen in
    // practice, but defensive against stale data).
    return `${currency} ${num.toFixed(2)}`;
  }
}

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

  // Hook must run unconditionally (React rules-of-hooks) so it sits
  // here — before the loading/error early returns below — and guards
  // against a null proposal inside the callback.
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
      <div className="min-h-screen bg-neutral-950 flex items-center justify-center">
        <div className="flex items-center gap-3 text-neutral-500 text-xs uppercase tracking-[0.3em]">
          <span className="inline-block h-px w-8 bg-neutral-700" aria-hidden="true" />
          Loading
          <span className="inline-block h-px w-8 bg-neutral-700" aria-hidden="true" />
        </div>
      </div>
    );
  }

  if (error || !proposal) {
    return (
      <div className="min-h-screen bg-neutral-950 flex items-center justify-center px-6">
        <div className="text-center max-w-md">
          <p className="text-[10px] uppercase tracking-[0.3em] text-neutral-500 mb-4">Error</p>
          <h1 className="font-serif text-3xl text-neutral-100 mb-3 text-balance">
            Proposal not found
          </h1>
          <p className="text-sm text-neutral-400 leading-relaxed text-pretty">
            {error || 'This proposal may have been withdrawn or the link is no longer valid. Please contact your account manager.'}
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

  const validUntilDate = proposal.valid_until
    ? new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
        .format(new Date(proposal.valid_until))
    : null;

  const displayedStatus = actionDone ?? (
    proposal.status === 'accepted' ? 'accepted'
    : proposal.status === 'rejected' ? 'rejected'
    : proposal.status === 'paid' ? 'paid'
    : null
  );

  const formattedAmount = formatMoney(proposal.amount, proposal.currency);
  const cadence = proposal.payment_type === 'subscription'
    ? cadenceOf(proposal.recurring_interval, proposal.recurring_interval_count)
    : null;
  const hasPricingBlock = Boolean(formattedAmount || proposal.pricing_section);

  // Section numbering: title block is implicit; we start counting at 01
  // for the first rendered section and advance through content +
  // pricing + payment + signatory.
  let sectionCounter = 0;
  const nextSectionNumber = () => {
    sectionCounter += 1;
    return String(sectionCounter).padStart(2, '0');
  };

  const accent = branding.primary_color;

  return (
    <div
      className="min-h-screen bg-neutral-950 text-neutral-200 antialiased"
      style={{
        // Subtle radial vignette keeps the page from feeling flat
        // without drawing attention. Layered behind all content.
        backgroundImage:
          'radial-gradient(ellipse 120% 60% at 50% 0%, rgba(255,255,255,0.03), transparent 60%)',
      }}
    >
      {/* Letterhead — quiet, left-aligned, with a single accent rule */}
      <header className="border-b border-neutral-800/60">
        <div className="mx-auto max-w-[880px] px-6 sm:px-10 py-5 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3 min-w-0">
            {branding.logo_url && !logoError ? (
              <img
                src={branding.logo_url}
                alt={companyDisplayName}
                height={28}
                className="object-contain"
                style={{ height: 28, width: 'auto', maxWidth: 140 }}
                onError={() => setLogoError(true)}
              />
            ) : (
              <div
                className="h-7 w-7 flex items-center justify-center flex-shrink-0 border"
                style={{ borderColor: accent, color: accent }}
              >
                <span className="font-serif text-sm leading-none">
                  {companyDisplayName[0]?.toUpperCase() || 'P'}
                </span>
              </div>
            )}
            <span className="font-serif text-[15px] text-neutral-100 tracking-wide truncate">
              {companyDisplayName}
            </span>
          </div>
          <div className="flex items-center gap-4 text-[11px] font-mono uppercase tracking-[0.18em] text-neutral-400">
            <span className="tabular-nums">{proposal.proposal_number}</span>
            {displayedStatus && (
              <span
                className="inline-flex items-center gap-1.5"
                style={{ color: displayedStatus === 'rejected' ? '#ef4444' : accent }}
              >
                <span
                  className="inline-block h-1.5 w-1.5 rounded-full"
                  style={{ backgroundColor: displayedStatus === 'rejected' ? '#ef4444' : accent }}
                  aria-hidden="true"
                />
                {displayedStatus === 'paid' ? 'Paid' : displayedStatus}
              </span>
            )}
          </div>
        </div>
        {/* Hairline accent rule — the only full-width color moment on the page */}
        <div className="h-px w-full" style={{ backgroundColor: accent, opacity: 0.35 }} />
      </header>

      <main className="mx-auto max-w-[720px] px-6 sm:px-10 py-20 sm:py-28">
        {/* Cover title block — centered, generous whitespace, framed by
            hairline rules top and bottom to feel like a title page. */}
        <section className="text-center pb-16 sm:pb-20 border-b border-neutral-800/80">
          <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-neutral-500 mb-6">
            Proposal &middot; <span className="tabular-nums">{proposal.proposal_number}</span>
          </p>
          <h1
            className="font-serif text-[38px] sm:text-[52px] md:text-[60px] leading-[1.05] text-neutral-50 text-balance"
            style={{ letterSpacing: '-0.02em' }}
          >
            {proposal.title}
          </h1>
          {proposal.contact && (
            <p className="mt-8 font-serif italic text-lg sm:text-xl text-neutral-300">
              Prepared for {proposal.contact.full_name}
            </p>
          )}
          {proposal.company && proposal.company.name !== companyDisplayName && (
            <p className="mt-1 text-sm text-neutral-500 tracking-wide">
              {proposal.company.name}
            </p>
          )}
          {validUntilDate && (
            <div className="mt-10 inline-flex items-center gap-3 text-[10px] font-mono uppercase tracking-[0.25em] text-neutral-500">
              <span className="inline-block h-px w-8 bg-neutral-700" aria-hidden="true" />
              <span className={isExpired ? 'text-red-400' : undefined}>
                {isExpired ? 'Expired' : 'Valid until'} <span className="tabular-nums">{validUntilDate}</span>
              </span>
              <span className="inline-block h-px w-8 bg-neutral-700" aria-hidden="true" />
            </div>
          )}
        </section>

        {/* Cover letter — no card, just flowing prose under the title */}
        {proposal.cover_letter && (
          <section className="mt-16 sm:mt-20">
            <p className="font-serif text-[17px] sm:text-[18px] leading-[1.7] text-neutral-200 whitespace-pre-wrap text-pretty break-words">
              {proposal.cover_letter}
            </p>
          </section>
        )}

        {/* Numbered content sections */}
        {contentSections.map((section) => {
          const num = nextSectionNumber();
          return (
            <section key={section.title} className="mt-20 sm:mt-24 scroll-mt-24">
              <SectionHeader num={num} title={section.title} accent={accent} />
              <div className="prose-document">
                <p className="whitespace-pre-wrap text-pretty break-words">
                  {section.body}
                </p>
              </div>
            </section>
          );
        })}

        {/* Pricing — quote-block treatment with a pull-figure */}
        {hasPricingBlock && (
          <section className="mt-20 sm:mt-24">
            <SectionHeader
              num={nextSectionNumber()}
              title={proposal.payment_type === 'subscription' ? 'Engagement & Fees' : 'Fees'}
              accent={accent}
            />

            {formattedAmount && (
              <figure className="my-10 sm:my-12 text-center">
                <div
                  className="text-[10px] font-mono uppercase tracking-[0.3em] mb-4"
                  style={{ color: accent }}
                >
                  {proposal.payment_type === 'subscription' ? 'Recurring fee' : 'Total investment'}
                </div>
                <div
                  className="font-serif text-[44px] sm:text-[56px] leading-none text-neutral-50 tabular-nums"
                  style={{ letterSpacing: '-0.02em' }}
                >
                  {formattedAmount}
                </div>
                {cadence && (
                  <div className="mt-4 font-serif italic text-neutral-400 text-base">
                    billed {cadence.toLowerCase()}
                  </div>
                )}
                <div
                  className="mx-auto mt-8 h-px w-24"
                  style={{ backgroundColor: accent, opacity: 0.5 }}
                  aria-hidden="true"
                />
              </figure>
            )}

            {proposal.pricing_section && (
              <div className="prose-document">
                <p className="whitespace-pre-wrap text-pretty break-words">
                  {proposal.pricing_section}
                </p>
              </div>
            )}
          </section>
        )}

        {/* Content (fallback) — only when no structured sections present */}
        {proposal.content &&
          contentSections.length === 0 &&
          !hasPricingBlock && (
            <section className="mt-20 sm:mt-24">
              <SectionHeader num={nextSectionNumber()} title="Proposal" accent={accent} />
              <div className="prose-document">
                <p className="whitespace-pre-wrap text-pretty break-words">
                  {proposal.content}
                </p>
              </div>
            </section>
          )}

        {/* Payment CTA — styled as its own section. Rendered whenever the
            backend has spawned a Stripe Invoice or Checkout Session. */}
        {proposal.stripe_payment_url && proposal.status !== 'paid' && (
          <section className="mt-20 sm:mt-24">
            <SectionHeader num={nextSectionNumber()} title="Payment" accent={accent} />
            <p className="prose-document-p mb-8">
              {proposal.payment_type === 'subscription'
                ? `Set up your payment method with ${companyDisplayName} via Stripe to activate your subscription. Your first billing period will be charged upon completion of checkout.`
                : `An invoice has been issued for this engagement. Complete payment securely via Stripe to confirm and proceed.`}
            </p>
            <a
              href={proposal.stripe_payment_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-3 border px-8 py-3.5 font-serif text-[15px] text-neutral-50 hover:bg-neutral-900/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 transition-colors"
              style={{ borderColor: accent, outlineColor: accent }}
            >
              {proposal.payment_type === 'subscription'
                ? 'Complete payment setup'
                : 'Proceed to payment'}
              <span aria-hidden="true" className="inline-block" style={{ color: accent }}>
                →
              </span>
            </a>
          </section>
        )}

        {proposal.status === 'paid' && (
          <section className="mt-20 sm:mt-24">
            <SectionHeader num={nextSectionNumber()} title="Payment Received" accent={accent} />
            <p className="prose-document-p">
              Your payment has been confirmed. A receipt has been sent to your email. We will
              follow up shortly with next steps for this engagement.
            </p>
          </section>
        )}

        {/* Signatory block — structured like the execution section of a
            legal document. Underlined inputs evoke a physical form. */}
        {canRespond && (
          <section className="mt-24 sm:mt-28">
            <SectionHeader num={nextSectionNumber()} title="Signatory" accent={accent} />

            <p className="prose-document-p mb-10">
              By signing below, you accept this proposal and its terms on behalf of the
              receiving organization. Your signature is legally binding under the US ESIGN
              Act and applicable state UETA statutes; the full disclosure is at the bottom
              of this page.
            </p>

            <div className="grid gap-8 sm:grid-cols-2 mb-8">
              <SignatureField
                id="signer-name"
                label="Full Name"
                type="text"
                autoComplete="name"
                value={signerName}
                onChange={setSignerName}
                disabled={actionPending}
                accent={accent}
              />
              <SignatureField
                id="signer-email"
                label="Email Address"
                type="email"
                autoComplete="email"
                inputMode="email"
                spellCheck={false}
                value={signerEmail}
                onChange={setSignerEmail}
                disabled={actionPending}
                accent={accent}
              />
            </div>

            <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-neutral-500 mb-10">
              Signed electronically &middot; <span className="tabular-nums">
                {new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
                  .format(new Date())}
              </span>
            </p>

            {signError && (
              <p
                role="alert"
                aria-live="polite"
                className="mb-8 text-sm text-red-400 border-l-2 border-red-500/60 pl-4 py-1"
              >
                {signError}
              </p>
            )}

            <div className="flex flex-col sm:flex-row gap-4 items-stretch sm:items-center">
              <button
                type="button"
                aria-label="Accept this proposal"
                onClick={handleAccept}
                disabled={actionPending}
                className="inline-flex items-center justify-center gap-3 px-8 py-3.5 font-serif text-[15px] text-neutral-950 hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 disabled:opacity-50 transition-opacity"
                style={{ backgroundColor: accent, outlineColor: accent }}
              >
                {actionPending ? 'Recording…' : 'Accept & Sign'}
                {!actionPending && (
                  <span aria-hidden="true" className="inline-block">→</span>
                )}
              </button>
              <button
                type="button"
                aria-label="Decline this proposal"
                onClick={handleReject}
                disabled={actionPending}
                className="inline-flex items-center justify-center px-6 py-3.5 font-serif text-[15px] text-neutral-400 hover:text-neutral-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-neutral-500 disabled:opacity-50 transition-colors"
              >
                Decline proposal
              </button>
            </div>
          </section>
        )}

        {/* Post-action confirmation — kept minimal, styled as a closing note */}
        {actionDone && (
          <section className="mt-24 pt-12 border-t border-neutral-800/80 text-center">
            <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-neutral-500 mb-4">
              {actionDone === 'accepted' ? 'Signature recorded' : 'Response recorded'}
            </p>
            <p className="font-serif text-2xl sm:text-3xl text-neutral-100 mb-3 text-balance">
              {actionDone === 'accepted'
                ? 'Thank you — your signature has been captured.'
                : 'Thank you for your response.'}
            </p>
            <p className="font-serif italic text-neutral-400 text-pretty max-w-lg mx-auto leading-relaxed">
              {actionDone === 'accepted'
                ? proposal.stripe_payment_url
                  ? 'Please complete payment above to finalize this engagement.'
                  : `${companyDisplayName} will be in touch shortly with next steps.`
                : 'We appreciate your consideration and hope to work with you in the future.'}
            </p>
          </section>
        )}
      </main>

      {/* Fine-print legal footer — every public view sees the same
          ESIGN disclosure, tenant legal links (when configured), and
          Stripe disclosure (when a payment surface is active). */}
      <footer className="mt-24 border-t border-neutral-800/60">
        <div className="mx-auto max-w-[720px] px-6 sm:px-10 py-12 space-y-6">
          <details className="group border-l-2 border-neutral-800 pl-4 transition-colors open:border-neutral-700">
            <summary className="cursor-pointer text-[10px] font-mono uppercase tracking-[0.25em] text-neutral-500 hover:text-neutral-300 list-none flex items-center gap-3 select-none">
              <span aria-hidden="true" className="inline-block transition-transform group-open:rotate-90">
                ▸
              </span>
              Electronic signature disclosure &amp; consent
            </summary>
            <div className="mt-4 space-y-3 text-[12px] leading-relaxed text-neutral-400 text-pretty">
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
                timestamp at the moment you submit. This audit trail is retained alongside
                the proposal for dispute resolution.
              </p>
              <p>
                To sign, you need a modern web browser with JavaScript enabled and the
                ability to receive email at the address you provide. If any of these are
                unavailable, contact {companyDisplayName} to arrange an alternative
                signing method.
              </p>
            </div>
          </details>

          <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-6 pt-4 border-t border-neutral-800/60">
            <div className="space-y-1">
              <p className="font-serif text-sm text-neutral-300">{companyDisplayName}</p>
              {branding.footer_text && (
                <p className="text-[11px] text-neutral-500 leading-relaxed max-w-sm text-pretty">
                  {branding.footer_text}
                </p>
              )}
              <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-neutral-600 pt-2">
                <span className="tabular-nums">{proposal.proposal_number}</span>
              </p>
            </div>

            <div className="flex flex-wrap gap-x-5 gap-y-2 text-[10px] font-mono uppercase tracking-[0.2em] text-neutral-500">
              {branding.terms_of_service_url && (
                <a
                  href={branding.terms_of_service_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-neutral-300 transition-colors"
                >
                  Terms
                </a>
              )}
              {branding.privacy_policy_url && (
                <a
                  href={branding.privacy_policy_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-neutral-300 transition-colors"
                >
                  Privacy
                </a>
              )}
            </div>
          </div>

          {proposal.stripe_payment_url && (
            <div className="pt-4 border-t border-neutral-800/60 text-[11px] text-neutral-500 leading-relaxed text-pretty">
              <p>
                Payments are processed securely by{' '}
                <a href="https://stripe.com" target="_blank" rel="noopener noreferrer"
                  className="underline decoration-neutral-700 hover:decoration-neutral-400">
                  Stripe
                </a>
                . {companyDisplayName} never sees or stores your card details.{' '}
                <a href="https://stripe.com/legal/consumer" target="_blank" rel="noopener noreferrer"
                  className="underline decoration-neutral-700 hover:decoration-neutral-400">
                  Stripe Terms
                </a>
                {' · '}
                <a href="https://stripe.com/privacy" target="_blank" rel="noopener noreferrer"
                  className="underline decoration-neutral-700 hover:decoration-neutral-400">
                  Stripe Privacy
                </a>
              </p>
            </div>
          )}
        </div>
      </footer>

      {/* Scoped utilities used throughout the document. Kept inline so
          the component is self-contained and the Tailwind
          arbitrary-value noise stays out of the JSX. */}
      <style>{`
        .prose-document {
          font-size: 15.5px;
          line-height: 1.75;
          color: rgb(212 212 212);
        }
        .prose-document p { margin: 0; }
        .prose-document-p {
          font-size: 15.5px;
          line-height: 1.75;
          color: rgb(212 212 212);
          max-width: 62ch;
        }
        details > summary::-webkit-details-marker { display: none; }
      `}</style>
    </div>
  );
}

// -----------------------------------------------------------------
// Local components
// -----------------------------------------------------------------

interface SectionHeaderProps {
  num: string;
  title: string;
  accent: string;
}

function SectionHeader({ num, title, accent }: SectionHeaderProps) {
  return (
    <header className="mb-8 sm:mb-10">
      <div className="flex items-baseline gap-4 mb-3">
        <span
          className="font-mono text-[11px] tracking-[0.25em] tabular-nums"
          style={{ color: accent }}
        >
          § {num}
        </span>
        <span
          className="flex-1 h-px"
          style={{ backgroundColor: accent, opacity: 0.25 }}
          aria-hidden="true"
        />
      </div>
      <h2
        className="font-serif text-[26px] sm:text-[30px] leading-tight text-neutral-50 text-balance"
        style={{ letterSpacing: '-0.015em' }}
      >
        {title}
      </h2>
    </header>
  );
}

interface SignatureFieldProps {
  id: string;
  label: string;
  type: string;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  accent: string;
  autoComplete?: string;
  inputMode?: 'text' | 'email' | 'numeric' | 'tel' | 'search' | 'url' | 'none' | 'decimal';
  spellCheck?: boolean;
}

function SignatureField({
  id,
  label,
  type,
  value,
  onChange,
  disabled,
  accent,
  autoComplete,
  inputMode,
  spellCheck,
}: SignatureFieldProps) {
  return (
    <div className="relative pt-5">
      <label
        htmlFor={id}
        className="block text-[10px] font-mono uppercase tracking-[0.25em] text-neutral-500 mb-3"
      >
        {label}
      </label>
      <input
        id={id}
        type={type}
        autoComplete={autoComplete}
        inputMode={inputMode}
        spellCheck={spellCheck}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="w-full bg-transparent border-0 border-b px-0 pb-2 font-serif text-xl text-neutral-50 placeholder-neutral-700 focus:outline-none focus:ring-0 disabled:opacity-50 transition-colors"
        style={{ borderColor: value ? accent : 'rgb(64 64 64)' }}
      />
    </div>
  );
}

export default PublicProposalView;
