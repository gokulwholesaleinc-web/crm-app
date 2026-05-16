import { useState, useRef, useEffect, lazy, Suspense } from 'react';
import { useParams, useNavigate, useLocation, Link } from 'react-router-dom';
import { useSmartBack } from '../../hooks/useSmartBack';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeftIcon,
  ArrowPathIcon,
  ArrowUpTrayIcon,
  DocumentTextIcon,
  PaperAirplaneIcon,
  CheckIcon,
  TrashIcon,
  XMarkIcon,
  PencilIcon,
  EyeIcon,
  ClipboardDocumentIcon,
  TrophyIcon,
} from '@heroicons/react/24/outline';
import { Button, HelpLink, Modal, ConfirmDialog, StatusBadge } from '../../components/ui';
import { StickyActionBar } from '../../components/shared/StickyActionBar';
import { EntitySharing } from '../../components/shared/EntitySharing';
import { useAuthStore } from '../../store/authStore';
import {
  useProposal,
  useUpdateProposal,
  useDeleteProposal,
  useSendProposal,
  useAcceptProposal,
  useRejectProposal,
  useResendProposalPaymentLink,
  useRetryProposalBilling,
  useRestampProposalSignedPdf,
  useUpdateProposalSignatureCoords,
} from '../../hooks/useProposals';
import { ProposalBillingCard } from './ProposalBillingCard';
import { ProposalAuditCard } from './ProposalAuditCard';
// Lazy-loaded because pdf.js (~300 KB gzipped) only needs to land in
// the bundle when an admin actually opens the picker.
const SignatureFieldPicker = lazy(() =>
  import('./SignatureFieldPicker').then((m) => ({ default: m.SignatureFieldPicker })),
);
import { ProposalForm } from './ProposalForm';
import { StatusTimeline } from '../../components/shared/StatusTimeline';
import { SendChecklist } from '../../components/shared/SendChecklist';
import { isChecklistReady } from '../../components/shared/checklist';
import { InlineSectionEditor } from '../../components/shared/InlineSectionEditor';
import {
  buildProposalTimelineSteps,
  buildProposalSendChecklist,
} from './proposalStatus';
import {
  listProposalAttachments,
  uploadProposalAttachment,
  deleteProposalAttachment,
  openProposalAttachmentPreview,
  downloadProposalMasterContract,
  uploadProposalMasterContract,
  PROPOSAL_MASTER_CONTRACT_MAX_BYTES,
} from '../../api/proposals';
import { formatDate } from '../../utils/formatters';
import { usePageTitle } from '../../hooks/usePageTitle';
import { showSuccess, showError } from '../../utils/toast';
import { extractApiErrorDetail } from '../../utils/errors';
import type {
  ProposalCreate,
  ProposalUpdate,
  ProposalAttachment,
  SignatureFieldCoords,
} from '../../types';

function ProposalDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const handleBack = useSmartBack('/proposals');
  const proposalId = id ? parseInt(id, 10) : undefined;
  // ``masterUploadFailed`` from the two-step create flow on
  // ``ProposalsPage`` — surfaced as a persistent banner inside
  // ``MasterContractCard`` so the user can't miss the retry surface
  // when the disappearing toast on navigation goes away.
  const masterUploadFailedMessage =
    (location.state as { masterUploadFailed?: string | null } | null)
      ?.masterUploadFailed ?? null;

  const { data: proposal, isLoading, error, refetch } = useProposal(proposalId);
  usePageTitle(proposal ? `Proposal - ${proposal.title}` : 'Proposal');

  const updateProposalMutation = useUpdateProposal();
  const deleteProposalMutation = useDeleteProposal();
  const sendProposalMutation = useSendProposal();
  const acceptProposalMutation = useAcceptProposal();
  const rejectProposalMutation = useRejectProposal();
  const resendPaymentLinkMutation = useResendProposalPaymentLink();
  const retryBillingMutation = useRetryProposalBilling();
  const restampSignedPdfMutation = useRestampProposalSignedPdf();

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showDealWonBanner, setShowDealWonBanner] = useState(false);
  const actionRowRef = useRef<HTMLDivElement>(null);
  const prevStatusRef = useRef<string | undefined>(undefined);

  const currentStatus = proposal?.status;

  // Show a celebratory banner the first time we observe status flip to
  // 'accepted' within this session (polling from sent/viewed → accepted).
  useEffect(() => {
    const prev = prevStatusRef.current;
    if (
      currentStatus !== undefined &&
      prev !== undefined &&
      prev !== 'accepted' &&
      currentStatus === 'accepted'
    ) {
      setShowDealWonBanner(true);
    }
    if (currentStatus !== undefined) {
      prevStatusRef.current = currentStatus;
    }
  }, [currentStatus]);

  if (isLoading) {
    // Mirror the real 3-column layout so content loading doesn't jolt
    // the page width / sidebar position. `motion-reduce:animate-none`
    // honors the OS reduce-motion preference (the rest of the codebase
    // uses this; the original skeleton was an exception).
    return (
      <div className="space-y-6 animate-pulse motion-reduce:animate-none">
        <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-1/3" />
        <div className="h-16 bg-gray-200 dark:bg-gray-700 rounded" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded-lg" />
            <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded-lg" />
            <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded-lg" />
          </div>
          <div className="space-y-4">
            <div className="h-40 bg-gray-200 dark:bg-gray-700 rounded-lg" />
            <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded-lg" />
            <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded-lg" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !proposal) {
    return (
      <div className="text-center py-12">
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">Proposal not found</h3>
        <Link to="/proposals" className="mt-2 text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300">
          Back to Proposals
        </Link>
      </div>
    );
  }

  const handleSend = async () => {
    try {
      await sendProposalMutation.mutateAsync({ proposalId: proposal.id });
      showSuccess('Proposal sent');
    } catch {
      showError('Failed to send proposal');
    }
  };

  const handleAccept = async () => {
    try {
      await acceptProposalMutation.mutateAsync(proposal.id);
      showSuccess('Proposal accepted');
    } catch {
      showError('Failed to accept proposal');
    }
  };

  const handleReject = async () => {
    try {
      await rejectProposalMutation.mutateAsync(proposal.id);
      showSuccess('Proposal rejected');
    } catch {
      showError('Failed to reject proposal');
    }
  };

  const handleResendPaymentLink = async () => {
    try {
      const result = await resendPaymentLinkMutation.mutateAsync(proposal.id);
      if (result.action === 'already_paid_reconciled') {
        showSuccess('Already paid — status reconciled');
      } else if (result.action === 'regenerated') {
        showSuccess('Checkout session expired — new link generated and emailed');
      } else {
        showSuccess('Payment link re-emailed to the customer');
      }
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to resend payment link');
    }
  };

  const handleRetryBilling = async () => {
    try {
      const updated = await retryBillingMutation.mutateAsync(proposal.id);
      if (updated.stripe_payment_url) {
        showSuccess('Billing spawned — payment link emailed to the customer');
      } else if (updated.billing_error) {
        showError(`Billing still failing: ${updated.billing_error}`);
      } else {
        showSuccess('Billing retried');
      }
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to retry billing');
    }
  };

  const handleRestampSignedPdf = async () => {
    try {
      const updated = await restampSignedPdfMutation.mutateAsync(proposal.id);
      if (updated.signed_pdf_path) {
        showSuccess('Signed PDF re-generated');
        return;
      }
      // Empty-string error is still a recorded failure (str(exc) can
      // produce ""), so `!= null` keeps the diagnostic visible.
      if (updated.signed_pdf_error != null) {
        showError(`Re-stamp still failing: ${updated.signed_pdf_error}`);
        return;
      }
      showError('Re-stamp did not produce a signed PDF');
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to re-stamp signed PDF');
    }
  };

  const handleDelete = async () => {
    try {
      await deleteProposalMutation.mutateAsync(proposal.id);
      showSuccess('Proposal deleted');
      navigate('/proposals');
    } catch {
      showError('Failed to delete proposal');
    }
  };

  // ProposalForm emits a ProposalCreate. ProposalUpdate is a strict subset
  // (no `status`), so we forward every field the backend update schema
  // accepts and drop the create-only `status` field.
  const handleEditSubmit = async (formData: ProposalCreate) => {
    const { status: _status, ...rest } = formData;
    const data: ProposalUpdate = rest;
    try {
      await updateProposalMutation.mutateAsync({ id: proposal.id, data });
      setShowEditModal(false);
      showSuccess('Proposal updated');
    } catch {
      showError('Failed to update proposal');
    }
  };

  // Per-section inline save: each InlineSectionEditor calls this with the
  // field name it controls. Thrown errors propagate so the editor stays
  // in edit mode and surfaces an inline message — toast is the secondary
  // signal, not the primary recovery path.
  const handleSectionSave = async (
    field: keyof ProposalUpdate,
    value: string | null,
  ) => {
    try {
      await updateProposalMutation.mutateAsync({
        id: proposal.id,
        data: { [field]: value } as ProposalUpdate,
      });
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to save changes');
      throw err;
    }
  };

  const handleCopyPublicLink = () => {
    // Use the SPA route — not the raw JSON API path — and key on the
    // unguessable public_token, not the enumerable proposal_number.
    if (!proposal.public_token) {
      showError('This proposal has no public link yet; save or send it first.');
      return;
    }
    const url = `${window.location.origin}/proposals/public/${proposal.public_token}`;
    navigator.clipboard.writeText(url).then(
      () => showSuccess('Public link copied to clipboard'),
      () => showError('Failed to copy link')
    );
  };

  const currentUser = useAuthStore.getState().user;
  const canManageSharing =
    !!currentUser &&
    (currentUser.id === (proposal.owner?.id ?? proposal.owner_id) ||
      currentUser.is_superuser ||
      currentUser.role === 'admin' ||
      currentUser.role === 'manager');

  const isDraft = proposal.status === 'draft';
  const proposalRecipient =
    proposal.designated_signer_email || proposal.contact?.email || '';
  // Show Send for draft/sent/viewed so the CRM user can resend if delivery
  // failed (bad Gmail token, sandbox rejection). Require a recipient so the
  // frontend gates the 400 the backend would return without one.
  const canSendStatus = ['draft', 'sent', 'viewed'].includes(proposal.status ?? '');
  const canSend = canSendStatus && Boolean(proposalRecipient);
  const sendLabel = isDraft ? 'Send' : 'Resend';
  const canAcceptReject = proposal.status === 'sent' || proposal.status === 'viewed';
  const canEdit = ['draft', 'sent', 'viewed'].includes(proposal.status ?? '');
  const canResendPaymentLink =
    proposal.status === 'awaiting_payment' &&
    !proposal.paid_at &&
    Boolean(proposal.stripe_invoice_id || proposal.stripe_checkout_session_id);
  // Retry billing covers the case where accept landed (signature recorded)
  // but the Stripe spawn failed. The backend refuses retry once any
  // Stripe artifact is present, so the button only matters when none are.
  const canRetryBilling =
    ['accepted', 'awaiting_payment'].includes(proposal.status ?? '') &&
    !proposal.stripe_invoice_id &&
    !proposal.stripe_checkout_session_id &&
    !proposal.stripe_payment_url;

  // Build the timeline + checklist from the proposal record. Checklist
  // hides itself once everything required passes, so it only nags when
  // there's something to fix.
  const timelineSteps = buildProposalTimelineSteps(proposal);
  const sendChecklist = buildProposalSendChecklist(proposal, {
    onEditContact: () => setShowEditModal(true),
    onEditValidUntil: () => setShowEditModal(true),
  });
  const checklistReady = isChecklistReady(sendChecklist);

  const hasAnyContent = Boolean(
    proposal.executive_summary ||
      proposal.scope_of_work ||
      proposal.pricing_section ||
      proposal.timeline ||
      proposal.terms ||
      proposal.content,
  );

  return (
    <div className="space-y-6">
      <StickyActionBar triggerRef={actionRowRef}>
        {canSendStatus && (
          <Button
            size="sm"
            onClick={handleSend}
            disabled={sendProposalMutation.isPending || !canSend}
            variant={isDraft ? 'primary' : 'secondary'}
          >
            {sendProposalMutation.isPending ? 'Sending...' : sendLabel}
          </Button>
        )}
        {canEdit && (
          <Button variant="secondary" size="sm" onClick={() => setShowEditModal(true)}>
            Edit
          </Button>
        )}
      </StickyActionBar>
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={handleBack}
            className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
            aria-label="Go back"
          >
            <ArrowLeftIcon className="h-5 w-5" aria-hidden="true" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">
                {proposal.title}
              </h1>
              {/* Stack an Accepted pill once signed so awaiting_payment/paid
                  doesn't visually overwrite the fact that the customer signed. */}
              {proposal.signed_at && proposal.status !== 'accepted' && (
                <StatusBadge status="accepted" size="sm" showDot={false} />
              )}
              <StatusBadge status={proposal.status} size="sm" showDot={false} />
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400">{proposal.proposal_number}</p>
          </div>
        </div>

        {/* Action row — one primary CTA per status, others demoted to
            secondary. Accept/Reject collapse into a single "Mark Result"
            disclosure to avoid the wall-of-buttons clutter. Delete lives
            in the overflow menu so a misclick can't nuke a sent proposal. */}
        <div ref={actionRowRef} className="flex flex-wrap items-center gap-2">
          <HelpLink anchor="tutorial-esign" label="How clients sign and accept" />

          {/* PRIMARY action — status-driven. The single highest-leverage
              next step the user can take. */}
          {canSendStatus && (
            <Button
              onClick={handleSend}
              leftIcon={<PaperAirplaneIcon className="h-4 w-4" />}
              disabled={sendProposalMutation.isPending || !canSend}
              title={
                canSend
                  ? undefined
                  : 'Set a designated signer email or attach a contact with an email before sending'
              }
              variant={isDraft ? 'primary' : 'secondary'}
            >
              {sendProposalMutation.isPending ? 'Sending...' : sendLabel}
            </Button>
          )}
          {canResendPaymentLink && (
            <Button
              onClick={handleResendPaymentLink}
              leftIcon={<PaperAirplaneIcon className="h-4 w-4" />}
              disabled={resendPaymentLinkMutation.isPending}
            >
              {resendPaymentLinkMutation.isPending ? 'Resending...' : 'Resend Payment Link'}
            </Button>
          )}
          {canRetryBilling && (
            <Button
              onClick={handleRetryBilling}
              leftIcon={<ArrowPathIcon className="h-4 w-4" />}
              disabled={retryBillingMutation.isPending}
            >
              {retryBillingMutation.isPending ? 'Retrying...' : 'Retry Billing'}
            </Button>
          )}

          {/* SECONDARY — common follow-ups, always visible when applicable. */}
          {canAcceptReject && (
            <>
              <Button
                variant="secondary"
                onClick={handleAccept}
                leftIcon={<CheckIcon className="h-4 w-4" />}
                disabled={acceptProposalMutation.isPending}
              >
                Mark Accepted
              </Button>
              <Button
                variant="secondary"
                onClick={handleReject}
                leftIcon={<XMarkIcon className="h-4 w-4" />}
                disabled={rejectProposalMutation.isPending}
              >
                Mark Rejected
              </Button>
            </>
          )}
          <Button
            variant="secondary"
            onClick={handleCopyPublicLink}
            leftIcon={<ClipboardDocumentIcon className="h-4 w-4" />}
            disabled={!proposal.public_token}
            title={proposal.public_token ? undefined : 'Save or send the proposal first to generate a public link.'}
          >
            Copy Link
          </Button>
          {canEdit && (
            <Button
              variant="secondary"
              onClick={() => setShowEditModal(true)}
              leftIcon={<PencilIcon className="h-4 w-4" />}
            >
              Edit
            </Button>
          )}

          {/* Delete is always last + always danger. Confirm modal gates it. */}
          <Button variant="danger" onClick={() => setShowDeleteConfirm(true)}>
            Delete
          </Button>
        </div>
      </div>

      {/* Deal Won banner — appears when polling detects accepted status
          during the current session. Dismissible, no auto-toast spam. */}
      {showDealWonBanner && (
        <div
          role="status"
          aria-live="polite"
          className="flex items-center justify-between gap-3 rounded-lg bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 px-4 py-3"
        >
          <div className="flex items-center gap-3">
            <TrophyIcon className="h-5 w-5 text-green-600 dark:text-green-400 flex-shrink-0" aria-hidden="true" />
            <div>
              <p className="text-sm font-semibold text-green-800 dark:text-green-300">Deal won!</p>
              <p className="text-xs text-green-700 dark:text-green-400">The proposal was just accepted.</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setShowDealWonBanner(false)}
            aria-label="Dismiss deal won banner"
            className="p-1 text-green-600 dark:text-green-400 hover:text-green-800 dark:hover:text-green-200 rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-green-500"
          >
            <XMarkIcon className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      )}

      {/* Fail-soft stamp left no countersigned copy — surface so the
          operator can retry. Check `!= null` rather than truthiness so
          an empty-string error (from str(exc) where exc has no repr)
          still surfaces the banner instead of silently hiding. */}
      {proposal.signed_pdf_error != null && !proposal.signed_pdf_path && (
        <div
          role="alert"
          aria-live="polite"
          className="flex items-start justify-between gap-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 px-4 py-3"
        >
          <div className="flex items-start gap-3">
            <ArrowPathIcon className="h-5 w-5 text-amber-600 dark:text-amber-400 flex-shrink-0 mt-0.5" aria-hidden="true" />
            <div className="min-w-0">
              <p className="text-sm font-semibold text-amber-800 dark:text-amber-300">
                Signed PDF generation failed
              </p>
              <p className="text-xs text-amber-700 dark:text-amber-400 break-words">
                {proposal.signed_pdf_error}
              </p>
            </div>
          </div>
          <Button
            variant="secondary"
            onClick={handleRestampSignedPdf}
            leftIcon={<ArrowPathIcon className="h-4 w-4" />}
            disabled={restampSignedPdfMutation.isPending}
          >
            {restampSignedPdfMutation.isPending ? 'Re-stamping...' : 'Re-stamp'}
          </Button>
        </div>
      )}

      {/* Status timeline — tells the Draft → Sent → Viewed → Signed → Paid
          story at a glance. Replaces the implicit "stack two status pills
          and bury dates in the sidebar" pattern. */}
      <StatusTimeline steps={timelineSteps} />

      {/* Pre-send checklist — only shows when the proposal is in a
          sendable status AND at least one required gate is failing.
          Once everything's green it auto-hides so a polished proposal
          doesn't carry a clutter card. */}
      {canSendStatus && !checklistReady && (
        <SendChecklist
          items={sendChecklist}
          hideWhenAllGreen
        />
      )}

      {/* Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content — each section is inline-editable via pencil
            icon; the original "open the entire edit modal to tweak two
            sentences in Scope" friction is gone. The modal still owns
            related-record reassignment + billing changes. */}
        <div className="lg:col-span-2 space-y-6">
          {!hasAnyContent && canEdit && (
            <div className="rounded-lg border-2 border-dashed border-gray-300 dark:border-gray-600 bg-gray-50/50 dark:bg-gray-800/40 p-8 text-center">
              <DocumentTextIcon className="mx-auto h-10 w-10 text-gray-300 dark:text-gray-600" aria-hidden="true" />
              <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">
                This proposal is empty
              </h3>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Add an executive summary, scope, pricing, and terms so the client sees what you&rsquo;re proposing.
              </p>
              <div className="mt-4">
                <Button variant="primary" onClick={() => setShowEditModal(true)}>
                  Fill in the proposal
                </Button>
              </div>
            </div>
          )}

          <InlineSectionEditor
            title="Executive Summary"
            value={proposal.executive_summary ?? null}
            onSave={(v) => handleSectionSave('executive_summary', v)}
            canEdit={canEdit}
            placeholder="The 30-second pitch. What we're proposing, why it matters to the client."
          />
          <InlineSectionEditor
            title="Scope of Work"
            value={proposal.scope_of_work ?? null}
            onSave={(v) => handleSectionSave('scope_of_work', v)}
            canEdit={canEdit}
            rows={6}
            placeholder="Deliverables, phases, what's in and out of scope."
          />
          <InlineSectionEditor
            title="Pricing"
            value={proposal.pricing_section ?? null}
            onSave={(v) => handleSectionSave('pricing_section', v)}
            canEdit={canEdit}
            placeholder="Line-item breakdown, assumptions, anything beyond the structured amount on the right."
          />
          <InlineSectionEditor
            title="Timeline"
            value={proposal.timeline ?? null}
            onSave={(v) => handleSectionSave('timeline', v)}
            canEdit={canEdit}
            rows={3}
            placeholder="Kickoff, milestones, expected completion."
          />
          <InlineSectionEditor
            title="Terms"
            value={proposal.terms ?? null}
            onSave={(v) => handleSectionSave('terms', v)}
            canEdit={canEdit}
            rows={3}
            placeholder="Payment terms, IP, cancellation, anything legal."
          />

          {/* Content (fallback) — only renders for legacy proposals that
              were authored before the structured-section split. Read-only
              because editing a free-form blob doesn't have a destination
              field on the new schema. */}
          {proposal.content && !proposal.executive_summary && !proposal.scope_of_work && (
            <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-gray-100 dark:border-gray-700">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-2">Content</h2>
              <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap">{proposal.content}</p>
            </div>
          )}

          {/* Attachments — PDFs that ride along on the public link.
              Locked once the customer signs so the audit trail stays
              honest about what they were shown. */}
          <ProposalAttachmentsCard
            proposalId={proposal.id}
            isLocked={Boolean(proposal.signed_at)}
          />
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Proposal Info */}
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-gray-100 dark:border-gray-700">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-4">Details</h2>
            <dl className="space-y-3">
              <div>
                <dt className="text-xs text-gray-500 dark:text-gray-400">Valid Until</dt>
                <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{formatDate(proposal.valid_until)}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500 dark:text-gray-400">Created</dt>
                <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{formatDate(proposal.created_at)}</dd>
              </div>
              {proposal.created_by && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Created by</dt>
                  <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{proposal.created_by.full_name}</dd>
                </div>
              )}
              {proposal.owner && proposal.owner.id !== proposal.created_by?.id && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Owner</dt>
                  <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{proposal.owner.full_name}</dd>
                </div>
              )}
              {proposal.sent_at && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Sent</dt>
                  <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{formatDate(proposal.sent_at)}</dd>
                </div>
              )}
              {proposal.accepted_at && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Accepted</dt>
                  <dd className="text-sm font-medium text-green-600 dark:text-green-400">{formatDate(proposal.accepted_at)}</dd>
                </div>
              )}
              {proposal.rejected_at && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Rejected</dt>
                  <dd className="text-sm font-medium text-red-600 dark:text-red-400">{formatDate(proposal.rejected_at)}</dd>
                </div>
              )}
              <div className="pt-2 border-t border-gray-200 dark:border-gray-700">
                <dt className="text-xs text-gray-500 dark:text-gray-400">Views</dt>
                <dd className="flex items-center gap-2 text-sm font-medium text-gray-900 dark:text-gray-100">
                  <EyeIcon className="h-4 w-4 text-gray-400" aria-hidden="true" />
                  <span style={{ fontVariantNumeric: 'tabular-nums' }}>{proposal.view_count}</span>
                </dd>
              </div>
              {proposal.last_viewed_at && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Last Viewed</dt>
                  <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{formatDate(proposal.last_viewed_at)}</dd>
                </div>
              )}
            </dl>
          </div>

          {/* Billing — shows the structured pricing Giancarlo picked on
              create + any Stripe artifact that was spawned on e-sign
              (invoice id / subscription id / pay URL) so the CRM side
              mirrors what the client sees on the public page. */}
          <ProposalBillingCard proposal={proposal} />

          {/* E-sign + view audit trail. Signer name/email/IP/UA +
              timestamp on accept, plus the full public-link view log
              for forensics and billing disputes. */}
          <ProposalAuditCard proposal={proposal} />

          {/* Master service agreement upload. Always visible so the
              admin can attach the PDF after creating a proposal — the
              card is the discoverable entry point. Locked (read-only)
              once the proposal is signed so the signed audit bundle
              stays immutable. */}
          <MasterContractCard
            proposalId={proposal.id}
            currentPath={proposal.master_contract_pdf_path ?? null}
            isLocked={Boolean(proposal.signed_at)}
            initialError={masterUploadFailedMessage}
            onUploaded={() => {
              void refetch();
            }}
          />

          {/* Visual placement of the signer's signature box on the
              master contract. Only relevant once a master is on file;
              locked once the proposal is signed. */}
          {proposal.master_contract_pdf_path && (
            <SignaturePlacementCard
              proposalId={proposal.id}
              currentCoords={proposal.signature_field_coords ?? null}
              isLocked={Boolean(proposal.signed_at)}
            />
          )}

          {/* Sharing */}
          <EntitySharing
            entityType="proposals"
            entityId={proposal.id}
            ownerName={proposal.owner?.full_name ?? undefined}
            canManage={canManageSharing}
          />

          {/* Related Entities */}
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-gray-100 dark:border-gray-700">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-4">Related</h2>
            <dl className="space-y-3">
              {proposal.contact && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Contact</dt>
                  <dd className="text-sm font-medium">
                    <Link to={`/contacts/${proposal.contact.id}`} className="text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300">
                      {proposal.contact.full_name}
                    </Link>
                  </dd>
                </div>
              )}
              {proposal.company && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Company</dt>
                  <dd className="text-sm font-medium">
                    <Link to={`/companies/${proposal.company.id}`} className="text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300">
                      {proposal.company.name}
                    </Link>
                  </dd>
                </div>
              )}
              {/* Quote relation removed 2026-05-14 — quotes router unmounted. */}
              {!proposal.contact && !proposal.company && (
                <p className="text-sm text-gray-500 dark:text-gray-400">No related entities</p>
              )}
            </dl>
          </div>
        </div>
      </div>

      {/* Edit Proposal Modal — reuses ProposalForm so edit exposes every
          field create does (related records, billing, valid_until, etc.).
          `key` forces a remount per proposal version so the form picks
          up server-side mutations (e.g. signed_at landing). */}
      <Modal
        isOpen={showEditModal}
        onClose={() => setShowEditModal(false)}
        title="Edit Proposal"
        size="lg"
        fullScreenOnMobile
      >
        <ProposalForm
          key={`${proposal.id}-${proposal.updated_at ?? ''}`}
          initialData={{
            title: proposal.title,
            content: proposal.content ?? null,
            executive_summary: proposal.executive_summary ?? null,
            scope_of_work: proposal.scope_of_work ?? null,
            pricing_section: proposal.pricing_section ?? null,
            timeline: proposal.timeline ?? null,
            terms: proposal.terms ?? null,
            valid_until: proposal.valid_until ?? null,
            contact_id: proposal.contact?.id ?? null,
            company_id: proposal.company?.id ?? null,
            payment_type: proposal.payment_type,
            recurring_interval: proposal.recurring_interval,
            recurring_interval_count: proposal.recurring_interval_count,
            amount: proposal.amount,
            currency: proposal.currency,
            terms_and_conditions: proposal.terms_and_conditions ?? null,
          }}
          proposalId={proposal.id}
          onSubmit={handleEditSubmit}
          onCancel={() => setShowEditModal(false)}
          isLoading={updateProposalMutation.isPending}
        />
      </Modal>

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleDelete}
        title="Delete Proposal"
        message={`Are you sure you want to delete "${proposal.title}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteProposalMutation.isPending}
      />
    </div>
  );
}

// -----------------------------------------------------------------
// ProposalAttachmentsCard
// -----------------------------------------------------------------

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

interface ProposalAttachmentsCardProps {
  proposalId: number;
  isLocked: boolean;
}

function ProposalAttachmentsCard({ proposalId, isLocked }: ProposalAttachmentsCardProps) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<ProposalAttachment | null>(null);

  const queryKey = ['proposals', proposalId, 'attachments'] as const;

  const { data: attachments, isLoading, error } = useQuery({
    queryKey,
    queryFn: () => listProposalAttachments(proposalId),
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => uploadProposalAttachment(proposalId, file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
      showSuccess('Attachment uploaded');
    },
    onError: (err) => {
      showError(extractApiErrorDetail(err) ?? 'Failed to upload attachment');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (attachmentId: number) =>
      deleteProposalAttachment(proposalId, attachmentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey });
      showSuccess('Attachment deleted');
    },
    onError: (err) => {
      showError(extractApiErrorDetail(err) ?? 'Failed to delete attachment');
    },
  });

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0 || isLocked) return;
    Array.from(files).forEach((file) => {
      uploadMutation.mutate(file);
    });
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (isLocked) return;
    handleFiles(e.dataTransfer.files);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (isLocked) return;
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleConfirmDelete = () => {
    if (!pendingDelete) return;
    deleteMutation.mutate(pendingDelete.id);
    setPendingDelete(null);
  };

  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-gray-100 dark:border-gray-700">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400">Attachments</h2>
        {isLocked && (
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Locked — proposal signed
          </span>
        )}
      </div>

      {!isLocked && (
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          className={`mb-4 rounded border-2 border-dashed px-4 py-6 text-center transition-colors ${
            isDragging
              ? 'border-primary-500 bg-primary-50 dark:bg-primary-950/30'
              : 'border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-900'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,application/pdf"
            multiple
            className="sr-only"
            onChange={(e) => {
              handleFiles(e.target.files);
              // Reset so re-selecting the same file fires onChange.
              if (e.target) e.target.value = '';
            }}
          />
          <ArrowUpTrayIcon
            className="mx-auto h-6 w-6 text-gray-400 dark:text-gray-500"
            aria-hidden="true"
          />
          <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">
            Drop a PDF here, or
          </p>
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadMutation.isPending}
            className="mt-2 inline-flex items-center gap-1.5 text-sm font-medium text-primary-600 hover:text-primary-700 dark:text-primary-400 dark:hover:text-primary-300 disabled:opacity-50"
          >
            {uploadMutation.isPending ? 'Uploading…' : 'Choose file'}
          </button>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">PDF only</p>
        </div>
      )}

      {isLoading && (
        <p className="text-sm text-gray-500 dark:text-gray-400">Loading attachments…</p>
      )}

      {error && !isLoading && (
        <p className="text-sm text-red-600 dark:text-red-400">
          Failed to load attachments.
        </p>
      )}

      {!isLoading && !error && attachments && attachments.length === 0 && (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          No attachments yet.
        </p>
      )}

      {!isLoading && attachments && attachments.length > 0 && (
        <ul className="divide-y divide-gray-200 dark:divide-gray-700 border border-gray-200 dark:border-gray-700 rounded">
          {attachments.map((attachment) => (
            <li
              key={attachment.id}
              className="flex items-center justify-between gap-3 px-3 py-2"
            >
              <div className="flex min-w-0 items-center gap-3">
                <DocumentTextIcon
                  className="h-5 w-5 flex-shrink-0 text-gray-400 dark:text-gray-500"
                  aria-hidden="true"
                />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                    {attachment.original_filename}
                  </p>
                  <p className="text-xs text-gray-500 dark:text-gray-400 tabular-nums">
                    {formatFileSize(attachment.file_size)}
                    {attachment.created_at && (
                      <> · {formatDate(attachment.created_at)}</>
                    )}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1 flex-shrink-0">
                <button
                  type="button"
                  aria-label={`View ${attachment.original_filename} in a new tab`}
                  onClick={async () => {
                    try {
                      await openProposalAttachmentPreview(attachment.id);
                    } catch (err) {
                      showError(
                        extractApiErrorDetail(err) ?? 'Failed to open attachment',
                      );
                    }
                  }}
                  className="p-1.5 text-gray-400 hover:text-primary-600 dark:hover:text-primary-400 rounded focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-500"
                >
                  <EyeIcon className="h-4 w-4" aria-hidden="true" />
                </button>
                <button
                  type="button"
                  aria-label={`Delete ${attachment.original_filename}`}
                  onClick={() => setPendingDelete(attachment)}
                  disabled={isLocked || deleteMutation.isPending}
                  className="p-1.5 text-gray-400 hover:text-red-600 dark:hover:text-red-400 rounded disabled:opacity-30 disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-red-500"
                >
                  <TrashIcon className="h-4 w-4" aria-hidden="true" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        isOpen={pendingDelete !== null}
        onClose={() => setPendingDelete(null)}
        onConfirm={handleConfirmDelete}
        title="Delete attachment"
        message={
          pendingDelete
            ? `Delete "${pendingDelete.original_filename}"? Customers with the public link will no longer see it.`
            : ''
        }
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}

// -----------------------------------------------------------------
// MasterContractCard
// -----------------------------------------------------------------

interface MasterContractCardProps {
  proposalId: number;
  currentPath: string | null;
  isLocked: boolean;
  /** Persistent error surface for the post-create retry path. When the
   *  two-step create flow fails on step 2, ProposalsPage navigates here
   *  with ``location.state.masterUploadFailed`` set, and ProposalDetail
   *  passes the resulting message down — keeps the failure visible
   *  past the disappearing toast. */
  initialError?: string | null;
  onUploaded: () => void;
}

/**
 * Sidebar card for managing the master service agreement PDF.
 *
 * Surfacing this on the detail page (rather than burying it inside the
 * edit modal) makes it discoverable from the moment a proposal exists,
 * and keeps the upload entry point available even after ``signed_at``
 * lands and the Edit button hides. Locked once signed so the
 * signed-bundle audit trail can't be mutated post-hoc.
 */
function MasterContractCard({
  proposalId,
  currentPath,
  isLocked,
  initialError = null,
  onUploaded,
}: MasterContractCardProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  // ``isMountedRef`` keeps setState/toast calls from firing after the
  // user navigates away mid-upload — without it a failed upload would
  // silently swallow the error (no toast on the destination page) and
  // a successful one would flash "Master contract uploaded" while the
  // user is already on an unrelated screen.
  const isMountedRef = useRef(true);
  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);
  const [uploading, setUploading] = useState(false);
  const [viewing, setViewing] = useState(false);
  const [error, setError] = useState<string | null>(initialError);

  // Revoke the view-blob after the new tab has had time to load it;
  // immediate revoke races the open and the viewer shows nothing.
  const revokeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (revokeTimerRef.current) clearTimeout(revokeTimerRef.current);
  }, []);

  const handleView = async () => {
    if (!currentPath) return;
    setViewing(true);
    setError(null);
    try {
      const blob = await downloadProposalMasterContract(proposalId);
      const url = URL.createObjectURL(blob);
      // window.open returns null when a popup blocker fires — strict
      // blockers treat the post-fetch open as a stale user-gesture.
      const popup = window.open(url, '_blank', 'noopener,noreferrer');
      if (!popup) {
        URL.revokeObjectURL(url);
        if (!isMountedRef.current) return;
        setError(
          'Popup blocked — allow popups for this site to view the master contract.',
        );
        return;
      }
      if (revokeTimerRef.current) clearTimeout(revokeTimerRef.current);
      revokeTimerRef.current = setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(
        extractApiErrorDetail(err) ?? 'Failed to load master contract.',
      );
    } finally {
      if (isMountedRef.current) {
        setViewing(false);
      }
    }
  };

  const handleFile = async (file: File) => {
    if (file.type && file.type !== 'application/pdf') {
      setError('Master contract must be a PDF file.');
      return;
    }
    if (file.size > PROPOSAL_MASTER_CONTRACT_MAX_BYTES) {
      setError('Master contract exceeds the 25 MB limit.');
      return;
    }
    setUploading(true);
    setError(null);
    try {
      await uploadProposalMasterContract(proposalId, file);
      if (!isMountedRef.current) return;
      showSuccess(
        currentPath ? 'Master contract replaced' : 'Master contract uploaded',
      );
      onUploaded();
    } catch (err) {
      if (!isMountedRef.current) return;
      setError(
        extractApiErrorDetail(err) ?? 'Master contract upload failed.',
      );
    } finally {
      if (isMountedRef.current) {
        setUploading(false);
      }
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-gray-100 dark:border-gray-700">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-4">
        Master service agreement
      </h2>
      <p className="text-sm text-gray-700 dark:text-gray-300">
        {currentPath
          ? 'PDF on file. The signer’s drawn signature is stamped onto a copy at sign time.'
          : 'No PDF on file. Upload one so the customer’s signature can be stamped onto your service agreement.'}
      </p>
      {currentPath && (
        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400 font-mono break-all">
          {currentPath}
        </p>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {currentPath && (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={handleView}
            disabled={viewing}
            isLoading={viewing}
            leftIcon={<EyeIcon className="h-4 w-4" />}
          >
            View PDF
          </Button>
        )}
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => inputRef.current?.click()}
          disabled={isLocked || uploading}
          isLoading={uploading}
          leftIcon={<ArrowUpTrayIcon className="h-4 w-4" />}
        >
          {currentPath ? 'Replace PDF' : 'Upload PDF'}
        </Button>
      </div>
      {isLocked && (
        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
          Locked &mdash; proposal signed.
        </p>
      )}
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          // Reset so re-uploading the same filename still re-fires onChange.
          e.target.value = '';
          if (file) {
            void handleFile(file);
          }
        }}
      />
      {error && (
        <p
          role="alert"
          aria-live="polite"
          className="mt-3 text-sm text-red-700 dark:text-red-400 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded px-3 py-2"
        >
          {error}
        </p>
      )}
    </div>
  );
}

// -----------------------------------------------------------------
// SignaturePlacementCard
// -----------------------------------------------------------------

interface SignaturePlacementCardProps {
  proposalId: number;
  currentCoords: SignatureFieldCoords | null;
  isLocked: boolean;
}

/**
 * Sidebar card that opens the visual signature-box picker.
 *
 * The master-contract PDF is fetched lazily — only when the admin
 * opens the picker — so the detail page itself doesn't pull the PDF
 * bytes on every load.
 */
function SignaturePlacementCard({
  proposalId,
  currentCoords,
  isLocked,
}: SignaturePlacementCardProps) {
  const [isPickerOpen, setIsPickerOpen] = useState(false);
  const [pdfUrl, setPdfUrl] = useState<string | null>(null);
  const [loadingPdf, setLoadingPdf] = useState(false);
  const updateCoordsMutation = useUpdateProposalSignatureCoords();

  // Revoke the blob URL when the card unmounts or the URL changes,
  // so we don't leak object URLs across re-opens.
  useEffect(() => {
    return () => {
      if (pdfUrl) {
        URL.revokeObjectURL(pdfUrl);
      }
    };
  }, [pdfUrl]);

  const handleOpen = async () => {
    if (isLocked) return;
    setLoadingPdf(true);
    try {
      const blob = await downloadProposalMasterContract(proposalId);
      const url = URL.createObjectURL(blob);
      setPdfUrl(url);
      setIsPickerOpen(true);
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to load master contract');
    } finally {
      setLoadingPdf(false);
    }
  };

  const handleClose = () => {
    setIsPickerOpen(false);
    if (pdfUrl) {
      URL.revokeObjectURL(pdfUrl);
      setPdfUrl(null);
    }
  };

  const handleSave = async (coords: SignatureFieldCoords) => {
    try {
      await updateCoordsMutation.mutateAsync({ proposalId, coords });
      showSuccess('Signature box saved');
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to save signature box');
      throw err;
    }
  };

  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-gray-100 dark:border-gray-700">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-4">
        Signature placement
      </h2>
      <p className="text-sm text-gray-700 dark:text-gray-300">
        {currentCoords
          ? `Box placed on page ${currentCoords.page}.`
          : 'No box placed — signature will land in the auto-box (bottom of last page).'}
      </p>
      <div className="mt-3">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={handleOpen}
          disabled={isLocked}
          isLoading={loadingPdf}
        >
          {currentCoords ? 'Edit placement' : 'Place signature'}
        </Button>
        {isLocked && (
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
            Locked — proposal signed.
          </p>
        )}
      </div>
      {isPickerOpen && pdfUrl && (
        <Suspense fallback={null}>
          <SignatureFieldPicker
            isOpen={isPickerOpen}
            onClose={handleClose}
            masterPdfUrl={pdfUrl}
            currentCoords={currentCoords}
            onSave={handleSave}
          />
        </Suspense>
      )}
    </div>
  );
}

export default ProposalDetailPage;
