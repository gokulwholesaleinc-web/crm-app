import { useState, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
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
} from '@heroicons/react/24/outline';
import { Button, HelpLink, Modal, ConfirmDialog, StatusBadge } from '../../components/ui';
import {
  useProposal,
  useUpdateProposal,
  useDeleteProposal,
  useSendProposal,
  useAcceptProposal,
  useRejectProposal,
  useResendProposalPaymentLink,
  useRetryProposalBilling,
} from '../../hooks/useProposals';
import { ProposalBillingCard } from './ProposalBillingCard';
import { ProposalAuditCard } from './ProposalAuditCard';
import {
  listProposalAttachments,
  uploadProposalAttachment,
  deleteProposalAttachment,
  openProposalAttachmentPreview,
} from '../../api/proposals';
import { formatDate } from '../../utils/formatters';
import { usePageTitle } from '../../hooks/usePageTitle';
import { showSuccess, showError } from '../../utils/toast';
import { extractApiErrorDetail } from '../../utils/errors';
import type { ProposalUpdate, ProposalAttachment } from '../../types';

function ProposalDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const handleBack = useSmartBack('/proposals');
  const proposalId = id ? parseInt(id, 10) : undefined;

  const { data: proposal, isLoading, error } = useProposal(proposalId);
  usePageTitle(proposal ? `Proposal - ${proposal.title}` : 'Proposal');

  const updateProposalMutation = useUpdateProposal();
  const deleteProposalMutation = useDeleteProposal();
  const sendProposalMutation = useSendProposal();
  const acceptProposalMutation = useAcceptProposal();
  const rejectProposalMutation = useRejectProposal();
  const resendPaymentLinkMutation = useResendProposalPaymentLink();
  const retryBillingMutation = useRetryProposalBilling();

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editExecutiveSummary, setEditExecutiveSummary] = useState('');
  const [editScopeOfWork, setEditScopeOfWork] = useState('');
  const [editPricingSection, setEditPricingSection] = useState('');
  const [editTimeline, setEditTimeline] = useState('');
  const [editTerms, setEditTerms] = useState('');

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="animate-pulse">
          <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-1/3 mb-4" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/2 mb-2" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/4" />
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

  const handleDelete = async () => {
    try {
      await deleteProposalMutation.mutateAsync(proposal.id);
      showSuccess('Proposal deleted');
      navigate('/proposals');
    } catch {
      showError('Failed to delete proposal');
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const data: ProposalUpdate = {
        title: editTitle,
        executive_summary: editExecutiveSummary || null,
        scope_of_work: editScopeOfWork || null,
        pricing_section: editPricingSection || null,
        timeline: editTimeline || null,
        terms: editTerms || null,
      };
      await updateProposalMutation.mutateAsync({ id: proposal.id, data });
      closeEditModal();
      showSuccess('Proposal updated');
    } catch {
      showError('Failed to update proposal');
    }
  };

  const openEditModal = () => {
    setEditTitle(proposal.title);
    setEditExecutiveSummary(proposal.executive_summary ?? '');
    setEditScopeOfWork(proposal.scope_of_work ?? '');
    setEditPricingSection(proposal.pricing_section ?? '');
    setEditTimeline(proposal.timeline ?? '');
    setEditTerms(proposal.terms ?? '');
    setShowEditModal(true);
  };

  const closeEditModal = () => {
    setShowEditModal(false);
    setEditTitle(proposal.title);
    setEditExecutiveSummary(proposal.executive_summary ?? '');
    setEditScopeOfWork(proposal.scope_of_work ?? '');
    setEditPricingSection(proposal.pricing_section ?? '');
    setEditTimeline(proposal.timeline ?? '');
    setEditTerms(proposal.terms ?? '');
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

  const isDraft = proposal.status === 'draft';
  const proposalRecipient =
    proposal.designated_signer_email || proposal.contact?.email || '';
  // Show Send for draft/sent/viewed so the CRM user can resend if delivery
  // failed (bad Gmail token, sandbox rejection). Require a recipient so the
  // frontend gates the 400 the backend would return without one.
  const canSendStatus = ['draft', 'sent', 'viewed'].includes(proposal.status ?? '');
  const canSend = canSendStatus && Boolean(proposalRecipient);
  const showSendButton = canSendStatus;
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

  return (
    <div className="space-y-6">
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

        <div className="flex flex-wrap items-center gap-2">
          <HelpLink anchor="tutorial-esign" label="How clients sign and accept" />
          {canEdit && (
            <Button variant="secondary" onClick={openEditModal} leftIcon={<PencilIcon className="h-4 w-4" />}>
              Edit
            </Button>
          )}
          <Button variant="secondary" onClick={handleCopyPublicLink} leftIcon={<ClipboardDocumentIcon className="h-4 w-4" />}>
            Copy Link
          </Button>
          {showSendButton && (
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
          {canAcceptReject && (
            <>
              <Button
                onClick={handleAccept}
                leftIcon={<CheckIcon className="h-4 w-4" />}
                disabled={acceptProposalMutation.isPending}
              >
                Accept
              </Button>
              <Button
                variant="secondary"
                onClick={handleReject}
                leftIcon={<XMarkIcon className="h-4 w-4" />}
                disabled={rejectProposalMutation.isPending}
              >
                Reject
              </Button>
            </>
          )}
          {canResendPaymentLink && (
            <Button
              variant="secondary"
              onClick={handleResendPaymentLink}
              leftIcon={<PaperAirplaneIcon className="h-4 w-4" />}
              disabled={resendPaymentLinkMutation.isPending}
            >
              {resendPaymentLinkMutation.isPending ? 'Resending...' : 'Resend Payment Link'}
            </Button>
          )}
          {canRetryBilling && (
            <Button
              variant="secondary"
              onClick={handleRetryBilling}
              leftIcon={<ArrowPathIcon className="h-4 w-4" />}
              disabled={retryBillingMutation.isPending}
            >
              {retryBillingMutation.isPending ? 'Retrying...' : 'Retry Billing'}
            </Button>
          )}
          <Button variant="danger" onClick={() => setShowDeleteConfirm(true)}>
            Delete
          </Button>
        </div>
      </div>

      {/* Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Executive Summary */}
          {proposal.executive_summary && (
            <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
              <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Executive Summary</h2>
              <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap">{proposal.executive_summary}</p>
            </div>
          )}

          {/* Scope of Work */}
          {proposal.scope_of_work && (
            <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
              <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Scope of Work</h2>
              <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap">{proposal.scope_of_work}</p>
            </div>
          )}

          {/* Pricing Section */}
          {proposal.pricing_section && (
            <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
              <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Pricing</h2>
              <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap">{proposal.pricing_section}</p>
            </div>
          )}

          {/* Timeline */}
          {proposal.timeline && (
            <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
              <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Timeline</h2>
              <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap">{proposal.timeline}</p>
            </div>
          )}

          {/* Terms */}
          {proposal.terms && (
            <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
              <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Terms</h2>
              <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap">{proposal.terms}</p>
            </div>
          )}

          {/* Content (fallback) */}
          {proposal.content && !proposal.executive_summary && !proposal.scope_of_work && (
            <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
              <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Content</h2>
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
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
            <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-4">Details</h2>
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

          {/* Related Entities */}
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
            <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-4">Related</h2>
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
              {proposal.opportunity && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Opportunity</dt>
                  <dd className="text-sm font-medium">
                    <Link to={`/opportunities/${proposal.opportunity.id}`} className="text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300">
                      {proposal.opportunity.name}
                    </Link>
                  </dd>
                </div>
              )}
              {proposal.quote && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Quote</dt>
                  <dd className="text-sm font-medium">
                    <Link to={`/quotes/${proposal.quote.id}`} className="text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300">
                      {proposal.quote.title} ({proposal.quote.quote_number})
                    </Link>
                  </dd>
                </div>
              )}
              {!proposal.contact && !proposal.company && !proposal.opportunity && !proposal.quote && (
                <p className="text-sm text-gray-500 dark:text-gray-400">No related entities</p>
              )}
            </dl>
          </div>
        </div>
      </div>

      {/* Edit Proposal Modal */}
      <Modal
        isOpen={showEditModal}
        onClose={closeEditModal}
        title="Edit Proposal"
        size="lg"
        fullScreenOnMobile
      >
        <form onSubmit={handleEditSubmit} className="space-y-4">
          <div>
            <label htmlFor="edit-proposal-title" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Title *</label>
            <input
              type="text"
              id="edit-proposal-title"
              required
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            />
          </div>
          <div>
            <label htmlFor="edit-exec-summary" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Executive Summary</label>
            <textarea
              id="edit-exec-summary"
              rows={3}
              value={editExecutiveSummary}
              onChange={(e) => setEditExecutiveSummary(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            />
          </div>
          <div>
            <label htmlFor="edit-scope" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Scope of Work</label>
            <textarea
              id="edit-scope"
              rows={3}
              value={editScopeOfWork}
              onChange={(e) => setEditScopeOfWork(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            />
          </div>
          <div>
            <label htmlFor="edit-pricing" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Pricing</label>
            <textarea
              id="edit-pricing"
              rows={3}
              value={editPricingSection}
              onChange={(e) => setEditPricingSection(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            />
          </div>
          <div>
            <label htmlFor="edit-timeline" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Timeline</label>
            <textarea
              id="edit-timeline"
              rows={2}
              value={editTimeline}
              onChange={(e) => setEditTimeline(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            />
          </div>
          <div>
            <label htmlFor="edit-terms" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Terms</label>
            <textarea
              id="edit-terms"
              rows={2}
              value={editTerms}
              onChange={(e) => setEditTerms(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            />
          </div>
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <Button type="button" variant="secondary" onClick={closeEditModal}>Cancel</Button>
            <Button type="submit" disabled={updateProposalMutation.isPending || !editTitle.trim()}>
              {updateProposalMutation.isPending ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </form>
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
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
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

export default ProposalDetailPage;
