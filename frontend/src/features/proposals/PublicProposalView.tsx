import { useState, useEffect, useMemo, useRef, useCallback, startTransition } from 'react';
import { useParams } from 'react-router-dom';
import { ArrowTopRightOnSquareIcon, CheckIcon, PencilSquareIcon, XMarkIcon } from '@heroicons/react/24/outline';
import axios from 'axios';
import { sanitizeHexColor, withAlpha } from '../../utils/colorValidation';
import { useForceLightMode } from '../../hooks/useForceLightMode';
import { formatDate } from '../../utils/formatters';
import { setPublicPageMeta } from './publicMeta';
import { ProposalAttachmentsSection } from './ProposalAttachmentsSection';
import type { ProposalAttachmentPublic } from '../../types';
import { ScrollToSignIndicator } from '../../components/ui/ScrollToSignIndicator';
import { SignToConfirmModal } from '../../components/SignToConfirmModal';

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

// Translate a raw axios error from the public client into a customer-
// readable message. Status-branched so a transient 502 reads as
// "try again" rather than the same generic "contact your account
// manager" we surface when the server explicitly rejects. Uses duck
// typing instead of `axios.isAxiosError` so the helper works under
// Vitest module mocks that omit the static method.
function publicErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object') {
    const e = err as {
      response?: { status?: number; data?: { detail?: unknown } };
      code?: string;
      isAxiosError?: boolean;
    };
    const detail = e.response?.data?.detail;
    if (typeof detail === 'string' && detail.trim()) return detail.trim();
    // FastAPI 422 returns detail as an array of {loc, msg, type}. Surface
    // the messages so the signer sees the actual validation failure
    // ("signer_email: field required") instead of a generic fallback.
    if (Array.isArray(detail) && detail.length > 0) {
      const msgs = detail
        .map((d) => (d && typeof d === 'object' && 'msg' in d ? (d as { msg?: unknown }).msg : null))
        .filter((m): m is string => typeof m === 'string' && m.trim() !== '');
      if (msgs.length > 0) return msgs.join('; ');
    }
    // Timeouts arrive with `code === 'ECONNABORTED'` and no response.
    if (e.code === 'ECONNABORTED') {
      return 'The request timed out. Please check your connection and try again.';
    }
    if ('response' in e || e.isAxiosError) {
      const status = e.response?.status;
      if (!status) {
        return 'Network error — please check your connection and try again.';
      }
      if (status >= 500) {
        return 'Our server hit a temporary error. Please try again in a moment.';
      }
    }
  }
  // Surface unexpected client-side errors at least to the console so the
  // signer's browser devtools have a breadcrumb when reporting to support.
  console.error('public proposal action failed', err);
  return fallback;
}

interface ProposalBranding {
  company_name: string | null;
  logo_url: string | null;
  primary_color: string;
  secondary_color: string;
  accent_color: string;
  bg_color_light: string;
  surface_color_light: string;
  footer_text: string | null;
  privacy_policy_url: string | null;
  terms_of_service_url: string | null;
}

interface PublicProposal {
  id?: number | null;
  proposal_number: string;
  public_token?: string | null;
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
  payment_type?: 'one_time' | 'subscription' | null;
  recurring_interval?: 'month' | 'year' | null;
  recurring_interval_count?: number | null;
  amount?: string | number | null;
  currency?: string | null;
  stripe_payment_url?: string | null;
  paid_at?: string | null;
  proposal_bundle_id?: number | null;
  bundle_sort_order?: number;
  bundle_is_recommended?: boolean;
  bundle_id?: number | null;
  bundle_title?: string | null;
  bundle_description?: string | null;
  bundle_selected_proposal_id?: number | null;
  proposal_options?: PublicProposal[];
  company: { id: number; name: string } | null;
  contact: { id: number; full_name: string } | null;
  branding: ProposalBranding | null;
  attachments?: ProposalAttachmentPublic[];
  signing_documents?: ProposalAttachmentPublic[];
  // Sign-to-Confirm modal inputs — resolved server-side so the modal
  // doesn't have to chain another fetch on open.
  designated_signer_email: string | null;
  has_master_contract: boolean;
  signing_document_count?: number;
  // Full ESIGN disclosure, authored server-side so the on-screen text is
  // byte-identical to the snapshot persisted at accept. Paragraphs split
  // on blank lines.
  esign_disclosure?: string | null;
}

// Shown only if the API response predates the server-authored disclosure
// (e.g. a stale cache during the deploy window). The live disclosure always
// comes from the server so it stays byte-identical to the persisted snapshot.
const FALLBACK_ESIGN_DISCLOSURE =
  'By drawing and submitting your signature, you agree that it constitutes ' +
  'your legally binding electronic signature under the US ESIGN Act ' +
  '(15 USC §7001) and applicable state UETA statutes, with the same legal ' +
  'effect as a handwritten signature.\n\nWe record your name, email address, ' +
  'IP address, browser user-agent, and timestamp at submission. This audit ' +
  'trail is retained alongside the proposal for dispute resolution.';

const DEFAULT_BRANDING: ProposalBranding = {
  company_name: null,
  logo_url: null,
  primary_color: '#6366f1',
  secondary_color: '#8b5cf6',
  accent_color: '#22c55e',
  bg_color_light: '#f9fafb',
  surface_color_light: '#ffffff',
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
  const [signModalOpen, setSignModalOpen] = useState(false);
  const [signError, setSignError] = useState<string | null>(null);
  // Tracks which attachment IDs the customer has opened on this device.
  // Seeded from the public response (server-side `viewed` flag) the first
  // time we see the proposal so a returning customer doesn't have to
  // re-open every PDF. Subsequent opens are added optimistically inside
  // a transition — the next polled refetch may also flip `viewed`, but
  // local state is the source of truth for the gate.
  const [viewedIds, setViewedIds] = useState<Set<number>>(() => new Set());
  const [viewedSigningDocumentIds, setViewedSigningDocumentIds] = useState<Set<number>>(() => new Set());
  const signSectionElRef = useRef<HTMLElement | null>(null);
  const signObserverRef = useRef<IntersectionObserver | null>(null);
  const esignConsentRef = useRef<HTMLDetailsElement | null>(null);
  const esignAutoOpenedRef = useRef(false);
  const [showScrollIndicator, setShowScrollIndicator] = useState(false);

  // Callback ref so the IntersectionObserver attaches the moment the element
  // mounts (useEffect([ref.current]) doesn't re-run on ref assignment).
  const signSectionRef = useCallback((el: HTMLElement | null) => {
    signSectionElRef.current = el;
    signObserverRef.current?.disconnect();
    if (!el) { setShowScrollIndicator(false); return; }
    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry) setShowScrollIndicator(!entry.isIntersecting);
      },
      { threshold: 0.1 },
    );
    observer.observe(el);
    signObserverRef.current = observer;
    setShowScrollIndicator(el.getBoundingClientRect().top > window.innerHeight * 0.9);
  }, []);

  useForceLightMode();

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

  // Reconcile local "opened" state from the server-side view ledger each
  // time the public proposal is fetched. Opens are still marked
  // optimistically for instant feedback, but this authoritative pass
  // clears a blocked-popup or failed-download false positive before sign.
  useEffect(() => {
    if (!proposal) return;
    const initial = (proposal.attachments ?? [])
      .filter((a) => a.viewed)
      .map((a) => a.id);
    const initialSigningDocuments = (proposal.signing_documents ?? [])
      .filter((d) => d.viewed)
      .map((d) => d.id);
    setViewedIds(new Set(initial));
    setViewedSigningDocumentIds(new Set(initialSigningDocuments));
  }, [proposal]);

  // The signing modal links to #esign-consent in a new tab; the footer
  // disclosure lives inside a collapsed <details>, so on landing we
  // open it and scroll it into view so the signer doesn't have to hunt.
  useEffect(() => {
    if (esignAutoOpenedRef.current) return;
    if (typeof window === 'undefined') return;
    if (window.location.hash !== '#esign-consent') return;
    const el = esignConsentRef.current;
    if (!el) return;
    esignAutoOpenedRef.current = true;
    el.open = true;
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [proposal?.proposal_number]);

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

  const submitSignature = useCallback(
    async ({
      signatureDataUrl,
      email,
    }: {
      signatureDataUrl: string;
      email: string;
    }): Promise<string | null> => {
      if (!proposal) return 'Proposal is no longer available.';
      const recipient = proposal.contact?.full_name ?? email;
      try {
        const response = await publicClient.post<PublicProposal>(
          `/api/proposals/public/${token}/accept`,
          {
            signer_name: recipient,
            signer_email: email,
            signature_image: signatureDataUrl,
            // Consent to use an electronic signature is now implied by
            // drawing + submitting the signature (the ESIGN disclosure is
            // shown in the page footer); there is no separate T&C checkbox.
            // Sent as true to satisfy the accept endpoint's required field.
            agreed_to_terms: true,
            signer_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
            selected_proposal_id: proposal.id ?? undefined,
          },
        );
        setProposal(response.data);
        setActionDone('accepted');
        setSignModalOpen(false);
        setSignError(null);
        return null;
      } catch (err) {
        return publicErrorMessage(
          err,
          'Unable to record acceptance. Please contact your account manager.',
        );
      }
    },
    [proposal, token],
  );

  const handleReject = async () => {
    if (!proposal) return;
    const email = proposal.designated_signer_email?.trim() ?? '';
    if (!email) {
      setSignError(
        'This proposal has no recipient on file. Please contact your account manager.',
      );
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
      const detail = publicErrorMessage(
        err,
        'Unable to record rejection. Please contact your account manager.',
      );
      setSignError(detail);
    } finally {
      setActionPending(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center">
        <div role="status" aria-label="Loading proposal…" className="animate-pulse motion-reduce:animate-none text-center">
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
    bg_color_light: sanitizeHexColor(rawBranding.bg_color_light, DEFAULT_BRANDING.bg_color_light),
    surface_color_light: sanitizeHexColor(rawBranding.surface_color_light, DEFAULT_BRANDING.surface_color_light),
  };
  const companyDisplayName = branding.company_name || proposal.company?.name || 'Proposal';
  const primary = branding.primary_color;
  const secondary = branding.secondary_color;
  const accent = branding.accent_color;

  const isExpired =
    proposal.valid_until &&
    new Date(proposal.valid_until) < new Date();

  const attachments = proposal.attachments ?? [];
  const signingDocuments = proposal.signing_documents ?? [];
  const signingDocumentCount = proposal.signing_document_count ?? signingDocuments.length;
  const hasSigningDocuments = proposal.has_master_contract || signingDocumentCount > 0;
  const proposalOptions = [...(proposal.proposal_options ?? [])].sort(
    (a, b) => (a.bundle_sort_order ?? 0) - (b.bundle_sort_order ?? 0),
  );
  const isBundleChooser = proposalOptions.length > 0;

  const handleAttachmentViewed = (id: number) => {
    // startTransition so the section re-render is treated as
    // non-urgent (the new-tab open is the urgent feedback).
    startTransition(() => {
      setViewedIds((curr) => {
        if (curr.has(id)) return curr;
        const next = new Set(curr);
        next.add(id);
        return next;
      });
    });
  };

  const handleSigningDocumentViewed = (id: number) => {
    startTransition(() => {
      setViewedSigningDocumentIds((curr) => {
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
    !actionDone;

  const recipientEmail = proposal.designated_signer_email ?? '';
  const unopenedDocumentCount =
    attachments.filter((attachment) => !viewedIds.has(attachment.id)).length +
    signingDocuments.filter((document) => !viewedSigningDocumentIds.has(document.id)).length;
  // Guard against future renders that might reach here with a null
  // proposal (e.g. a transient fetch failure that clears `error` but
  // leaves `proposal` null) — defaulted-empty arrays would otherwise
  // collapse to "all opened" and silently let signing proceed.
  const allRequiredDocumentsOpened = proposal != null && unopenedDocumentCount === 0;

  const validUntilDate = proposal.valid_until
    ? formatDate(proposal.valid_until, 'long')
    : null;

  const hasPricingNotes = Boolean(proposal.pricing_section);
  const canCompleteLegacyPayment = Boolean(
    proposal.stripe_payment_url &&
    proposal.status === 'awaiting_payment' &&
    !proposal.paid_at &&
    !isBundleChooser,
  );

  const statusPill = actionDone ?? (
    proposal.status === 'accepted' || proposal.status === 'awaiting_payment' || proposal.status === 'paid' ? 'accepted'
    : proposal.status === 'rejected' ? 'rejected'
    : null
  );

  return (
    // Customer-facing page bg from tenant settings; drop dark variants
    // (`dark:bg-gray-950` was hardcoded outside the bg/surface palette
    // anyway). Logged-in seller previews now match what the customer
    // sees.
    <div className="min-h-screen text-gray-900 antialiased print:bg-white" style={{ backgroundColor: branding.bg_color_light }}>
      <div
        aria-hidden="true"
        className="print:hidden"
        style={{
          height: 4,
          backgroundImage: `linear-gradient(90deg, ${primary}, ${secondary}, ${accent})`,
        }}
      />
      {/* Letterhead — plain, light, business-document feel. Text label
          is dropped when a logo image is present to avoid the "logo
          wordmark + typed company name" duplication. */}
      <header className="border-b border-gray-200 print:border-b-2" style={{ backgroundColor: branding.surface_color_light }}>
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
                    : { color: accent, backgroundColor: withAlpha(accent, '0f'), borderColor: withAlpha(accent, '40') }
                }
              >
                {statusPill === 'accepted' ? 'Accepted' : 'Declined'}
              </span>
            )}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 sm:px-10 py-10 sm:py-14">
        {isBundleChooser ? (
          <BundleOptionsChooser
            bundle={proposal}
            options={proposalOptions}
            accent={primary}
          />
        ) : (
          <>
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
            <p role="doc-subtitle" aria-label="Recipient" className="mt-3 text-[15px] text-gray-600 dark:text-gray-300">
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

        {token && (
          <ProposalAttachmentsSection
            attachments={signingDocuments}
            token={token}
            accent={secondary}
            documentKind="signing-documents"
            title="Signing Documents"
            description="Open each agreement document before signing. Your signature and date will be applied after acceptance."
            viewedIds={viewedSigningDocumentIds}
            onViewed={handleSigningDocumentViewed}
            onReconcile={fetchProposal}
          />
        )}

        {hasPricingNotes && (
          <section className="mt-10 sm:mt-12">
            <PlainSectionHeader
              title="Pricing Notes"
              accent={primary}
            />
            <div className="prose-body">
              <p className="whitespace-pre-wrap text-pretty break-words">
                {proposal.pricing_section}
              </p>
            </div>
          </section>
        )}

        {/* Content fallback */}
        {proposal.content &&
          contentSections.length === 0 &&
          !hasPricingNotes && (
            <section className="mt-10 sm:mt-12">
              <PlainSectionHeader title="Proposal" accent={primary} />
              <div className="prose-body">
                <p className="whitespace-pre-wrap text-pretty break-words">
                  {proposal.content}
                </p>
              </div>
            </section>
          )}

        {/* Accept / Decline — the typed-name form is replaced by the
            Sign-to-Confirm modal (drawn signature + T&C consent). */}
        {canRespond && (
          <section className="mt-10 sm:mt-12 print:hidden" ref={signSectionRef}>
            <PlainSectionHeader title="Your Response" accent={primary} />
            <p className="prose-body mb-5">
              {hasSigningDocuments
                ? `When you're ready, draw your signature to accept this proposal. A signed PDF copy will be emailed to ${proposal.contact?.full_name ?? 'you'}.`
                : 'When you\'re ready, draw your signature to accept this proposal. Your electronic signature records your acceptance of the proposal.'}
            </p>

            {signError && (
              <p
                role="alert"
                aria-live="polite"
                className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2"
              >
                {signError}
              </p>
            )}

            {!allRequiredDocumentsOpened && (
              <p
                role="status"
                className="mb-4 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2"
              >
                Open every document before signing. {unopenedDocumentCount} remaining.
              </p>
            )}

            <div className="flex flex-col sm:flex-row gap-3">
              <button
                type="button"
                aria-label="Open the signing dialog to accept this proposal"
                onClick={() => {
                  setSignError(null);
                  if (!allRequiredDocumentsOpened) {
                    setSignError(`Open every document before signing (${unopenedDocumentCount} remaining).`);
                    return;
                  }
                  setSignModalOpen(true);
                }}
                disabled={actionPending || !allRequiredDocumentsOpened}
                className="inline-flex items-center justify-center gap-2 rounded px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50 transition-opacity"
                style={{ backgroundColor: accent, outlineColor: accent }}
              >
                <PencilSquareIcon className="h-4 w-4" aria-hidden="true" />
                Sign to Accept
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

        {canCompleteLegacyPayment && proposal.stripe_payment_url && (
          <section className="mt-10 sm:mt-12 print:hidden">
            <PlainSectionHeader title="Payment" accent={accent} />
            <p className="prose-body mb-5">
              This proposal has been accepted. Use the secure payment link to complete the existing checkout.
            </p>
            <a
              href={proposal.stripe_payment_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded px-5 py-2.5 text-sm font-semibold text-white shadow-sm hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 transition-opacity"
              style={{ backgroundColor: accent, outlineColor: accent }}
            >
              <ArrowTopRightOnSquareIcon className="h-4 w-4" aria-hidden="true" />
              Complete Payment
            </a>
          </section>
        )}

        <SignToConfirmModal
          isOpen={signModalOpen && canRespond}
          onClose={() => setSignModalOpen(false)}
          recipientEmail={recipientEmail}
          hasSigningDocuments={hasSigningDocuments}
          signingDocumentCount={signingDocumentCount}
          onSubmit={submitSignature}
        />

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
                    ? hasSigningDocuments
                      ? 'A signed copy will be emailed to you shortly. You can safely close this page.'
                      : 'Your acceptance has been recorded. You can safely close this page.'
                    : 'Thank you for your response. We appreciate your consideration.'}
                </p>
              </div>
            </div>
          </section>
        )}
          </>
        )}
      </main>

      {/* Fine-print legal footer — ESIGN disclosure always visible. Pads
          with safe-area-inset-bottom so iPhone home indicator doesn't overlap
          the disclosure text (requires viewport-fit=cover in index.html). */}
      <footer
        className="mt-16 border-t border-gray-200"
        style={{ backgroundColor: branding.surface_color_light, paddingBottom: 'env(safe-area-inset-bottom)' }}
      >
        <div className="mx-auto max-w-3xl px-6 sm:px-10 py-8 space-y-5">
          <details
            ref={esignConsentRef}
            id="esign-consent"
            className="group text-sm scroll-mt-6"
          >
            <summary className="cursor-pointer text-sm font-medium text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100 list-none flex items-center gap-2 select-none">
              <span aria-hidden="true" className="inline-block transition-transform group-open:rotate-90">
                ▸
              </span>
              Electronic signature disclosure &amp; consent
            </summary>
            <div className="mt-3 space-y-2 text-[13px] leading-relaxed text-gray-600 dark:text-gray-400 text-pretty">
              {(proposal.esign_disclosure ?? FALLBACK_ESIGN_DISCLOSURE)
                .split('\n\n')
                .map((para, i) => (
                  <p key={i}>{para}</p>
                ))}
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
        </div>
      </footer>

      {showScrollIndicator && canRespond && (
        <ScrollToSignIndicator onClick={() => signSectionElRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })} />
      )}

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
        @media print {
          .prose-body { color: rgb(17 24 39); }
        }
      `}</style>
    </div>
  );
}

// -----------------------------------------------------------------
// Local components
// -----------------------------------------------------------------

function BundleOptionsChooser({
  bundle,
  options,
  accent,
}: {
  bundle: PublicProposal;
  options: PublicProposal[];
  accent: string;
}) {
  return (
    <section>
      <p className="text-xs uppercase tracking-wider text-gray-500 mb-3">
        Proposal Options <span className="text-gray-300 mx-1">·</span>
        <span className="tabular-nums">{bundle.proposal_number}</span>
      </p>
      <h1 className="text-3xl sm:text-4xl font-semibold text-gray-900 leading-tight tracking-tight text-balance">
        {bundle.title}
      </h1>
      {bundle.content && (
        <p className="mt-3 max-w-2xl text-[15px] leading-7 text-gray-600">
          {bundle.content}
        </p>
      )}

      <div className="mt-8 grid gap-4">
        {options.map((option) => {
          const href = option.public_token ? `/proposals/public/${option.public_token}` : '#';
          return (
            <a
              key={option.id ?? option.proposal_number}
              href={href}
              className="block rounded border border-gray-200 bg-white p-5 shadow-sm transition hover:border-gray-300 hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
              style={{ outlineColor: accent }}
            >
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-lg font-semibold text-gray-900">{option.title}</h2>
                    {option.bundle_is_recommended && (
                      <span
                        className="rounded-full px-2 py-0.5 text-xs font-medium"
                        style={{ color: accent, backgroundColor: withAlpha(accent, '12') }}
                      >
                        Recommended
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-xs tabular-nums text-gray-500">
                    {option.proposal_number}
                  </p>
                </div>
                <span
                  className="inline-flex items-center justify-center rounded px-3 py-1.5 text-sm font-semibold text-white"
                  style={{ backgroundColor: accent }}
                >
                  Review & Sign
                </span>
              </div>
              {(option.executive_summary || option.pricing_section || option.content) && (
                <p className="mt-4 line-clamp-3 text-sm leading-6 text-gray-600">
                  {option.executive_summary || option.pricing_section || option.content}
                </p>
              )}
            </a>
          );
        })}
      </div>

      {bundle.bundle_selected_proposal_id && (
        <div className="mt-8 rounded border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-900">
          One proposal option has already been selected and signed.
        </div>
      )}
    </section>
  );
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

interface PlainSectionHeaderProps {
  title: string;
  accent: string;
}

export default PublicProposalView;
