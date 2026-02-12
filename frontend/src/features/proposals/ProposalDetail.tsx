import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeftIcon,
  PaperAirplaneIcon,
  CheckIcon,
  XMarkIcon,
  PencilIcon,
  EyeIcon,
  ClipboardDocumentIcon,
} from '@heroicons/react/24/outline';
import { Button, Modal, ConfirmDialog, StatusBadge } from '../../components/ui';
import type { StatusType } from '../../components/ui/Badge';
import {
  useProposal,
  useUpdateProposal,
  useDeleteProposal,
  useSendProposal,
  useAcceptProposal,
  useRejectProposal,
} from '../../hooks/useProposals';
import { formatDate } from '../../utils/formatters';
import { usePageTitle } from '../../hooks/usePageTitle';
import { showSuccess, showError } from '../../utils/toast';
import type { ProposalUpdate } from '../../types';

function ProposalDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const proposalId = id ? parseInt(id, 10) : undefined;

  const { data: proposal, isLoading, error } = useProposal(proposalId);
  usePageTitle(proposal ? `Proposal - ${proposal.title}` : 'Proposal');

  const updateProposalMutation = useUpdateProposal();
  const deleteProposalMutation = useDeleteProposal();
  const sendProposalMutation = useSendProposal();
  const acceptProposalMutation = useAcceptProposal();
  const rejectProposalMutation = useRejectProposal();

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
        <Link to="/proposals" className="mt-2 text-primary-600 hover:text-primary-900">
          Back to Proposals
        </Link>
      </div>
    );
  }

  const handleSend = async () => {
    try {
      await sendProposalMutation.mutateAsync(proposal.id);
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
      setShowEditModal(false);
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

  const handleCopyPublicLink = () => {
    const url = `${window.location.origin}/api/proposals/public/${proposal.proposal_number}`;
    navigator.clipboard.writeText(url).then(
      () => showSuccess('Public link copied to clipboard'),
      () => showError('Failed to copy link')
    );
  };

  const isDraft = proposal.status === 'draft';
  const canSend = isDraft;
  const canAcceptReject = proposal.status === 'sent' || proposal.status === 'viewed';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          <Link
            to="/proposals"
            className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
            aria-label="Back to proposals"
          >
            <ArrowLeftIcon className="h-5 w-5" aria-hidden="true" />
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">
                {proposal.title}
              </h1>
              <StatusBadge status={proposal.status as StatusType} size="sm" showDot={false} />
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400">{proposal.proposal_number}</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {isDraft && (
            <Button variant="secondary" onClick={openEditModal} leftIcon={<PencilIcon className="h-4 w-4" />}>
              Edit
            </Button>
          )}
          <Button variant="secondary" onClick={handleCopyPublicLink} leftIcon={<ClipboardDocumentIcon className="h-4 w-4" />}>
            Copy Link
          </Button>
          {canSend && (
            <Button
              onClick={handleSend}
              leftIcon={<PaperAirplaneIcon className="h-4 w-4" />}
              disabled={sendProposalMutation.isPending}
            >
              {sendProposalMutation.isPending ? 'Sending...' : 'Send'}
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

          {/* Related Entities */}
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
            <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-4">Related</h2>
            <dl className="space-y-3">
              {proposal.contact && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Contact</dt>
                  <dd className="text-sm font-medium">
                    <Link to={`/contacts/${proposal.contact.id}`} className="text-primary-600 hover:text-primary-900">
                      {proposal.contact.full_name}
                    </Link>
                  </dd>
                </div>
              )}
              {proposal.company && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Company</dt>
                  <dd className="text-sm font-medium">
                    <Link to={`/companies/${proposal.company.id}`} className="text-primary-600 hover:text-primary-900">
                      {proposal.company.name}
                    </Link>
                  </dd>
                </div>
              )}
              {proposal.opportunity && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Opportunity</dt>
                  <dd className="text-sm font-medium">
                    <Link to={`/opportunities/${proposal.opportunity.id}`} className="text-primary-600 hover:text-primary-900">
                      {proposal.opportunity.name}
                    </Link>
                  </dd>
                </div>
              )}
              {proposal.quote && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Quote</dt>
                  <dd className="text-sm font-medium">
                    <Link to={`/quotes/${proposal.quote.id}`} className="text-primary-600 hover:text-primary-900">
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
        onClose={() => setShowEditModal(false)}
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
            <Button type="button" variant="secondary" onClick={() => setShowEditModal(false)}>Cancel</Button>
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

export default ProposalDetailPage;
