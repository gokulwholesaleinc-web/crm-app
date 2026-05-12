import { useState, useRef } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useSmartBack } from '../../hooks/useSmartBack';
import {
  ArrowLeftIcon,
  PaperAirplaneIcon,
  ArrowDownTrayIcon,
  PencilIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';
import { Button, Modal, ConfirmDialog } from '../../components/ui';
import { SearchableSelect } from '../../components/ui/SearchableSelect';
import { StickyActionBar } from '../../components/shared/StickyActionBar';
import { useContract, useUpdateContract, useDeleteContract, useSendContract } from '../../hooks/useContracts';
import { useContacts } from '../../hooks/useContacts';
import { useCompanies } from '../../hooks/useCompanies';
import { useAuthStore } from '../../store/authStore';
import { formatDate, formatCurrency } from '../../utils/formatters';
import { usePageTitle } from '../../hooks/usePageTitle';
import { showSuccess, showError } from '../../utils/toast';
import { extractApiErrorDetail } from '../../utils/errors';
import type { ContractUpdate } from '../../types';

import { ContractAttachmentsSection } from './ContractAttachmentsSection';
import { ContractAuditCard } from './ContractAuditCard';
import { ContractStatusBadge } from './statusBadge';
import EntitySharing from '../../components/shared/EntitySharing';
import { StatusTimeline } from '../../components/shared/StatusTimeline';
import { SendChecklist } from '../../components/shared/SendChecklist';
import { isChecklistReady } from '../../components/shared/checklist';
import { InlineSectionEditor } from '../../components/shared/InlineSectionEditor';
import {
  buildContractTimelineSteps,
  buildContractSendChecklist,
} from './contractStatus';

function ContractDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const handleBack = useSmartBack('/contracts');
  const contractId = id ? parseInt(id, 10) : undefined;

  const currentUser = useAuthStore((s) => s.user);
  const { data: contract, isLoading, error } = useContract(contractId);
  usePageTitle(contract ? `Contract - ${contract.title}` : 'Contract');

  const updateMutation = useUpdateContract();
  const deleteMutation = useDeleteContract();
  const sendMutation = useSendContract();
  const actionRowRef = useRef<HTMLDivElement>(null);

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showSendModal, setShowSendModal] = useState(false);
  const [sendToEmail, setSendToEmail] = useState('');
  const [sendMessage, setSendMessage] = useState('');
  const [showEditModal, setShowEditModal] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editContractNumber, setEditContractNumber] = useState('');
  const [editScope, setEditScope] = useState('');
  const [editValue, setEditValue] = useState('');
  const [editCurrency, setEditCurrency] = useState('USD');
  const [editStartDate, setEditStartDate] = useState('');
  const [editEndDate, setEditEndDate] = useState('');
  const [editStatus, setEditStatus] = useState('draft');
  const [editContactId, setEditContactId] = useState<number | null>(null);
  const [editCompanyId, setEditCompanyId] = useState<number | null>(null);
  const [editDesignatedSignerEmail, setEditDesignatedSignerEmail] = useState('');

  // Fetch contacts + companies for the pickers
  const { data: contactsData } = useContacts({ page_size: 100 });
  const { data: companiesData } = useCompanies({ page_size: 100 });

  const contactOptions = (contactsData?.items ?? []).map((c) => ({
    value: c.id,
    label: c.full_name ?? c.email ?? `Contact #${c.id}`,
  }));

  const companyOptions = (companiesData?.items ?? []).map((c) => ({
    value: c.id,
    label: c.name,
  }));

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse motion-reduce:animate-none">
        <div className="h-8 bg-gray-200 dark:bg-gray-700 rounded w-1/3" />
        <div className="h-16 bg-gray-200 dark:bg-gray-700 rounded" />
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-4">
            <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded-lg" />
            <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded-lg" />
          </div>
          <div className="space-y-4">
            <div className="h-40 bg-gray-200 dark:bg-gray-700 rounded-lg" />
            <div className="h-32 bg-gray-200 dark:bg-gray-700 rounded-lg" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !contract) {
    return (
      <div className="text-center py-12">
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">Contract not found</h3>
        <Link to="/contracts" className="mt-2 text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300">
          Back to Contracts
        </Link>
      </div>
    );
  }

  const isDraft = contract.status === 'draft';
  const isSent = contract.status === 'sent';
  const isSigned = contract.status === 'signed';
  const canEdit = ['draft', 'sent', 'active'].includes(contract.status);
  const canSend = isDraft;
  const canResend = isSent;
  const hasSignedPdf = isSigned && Boolean(contract.signed_pdf_r2_key);

  // canManage: owner, admin/manager, or superuser
  const canManage =
    currentUser != null && (
      currentUser.id === contract.owner_id ||
      currentUser.is_superuser ||
      currentUser.role === 'admin' ||
      currentUser.role === 'manager'
    );

  const ownerName = contract.owner_id != null
    ? (currentUser?.id === contract.owner_id ? currentUser.full_name : `User #${contract.owner_id}`)
    : '';

  const openEditModal = () => {
    setEditTitle(contract.title);
    setEditContractNumber(contract.contract_number ?? '');
    setEditScope(contract.scope ?? '');
    setEditValue(contract.value != null ? String(contract.value) : '');
    setEditCurrency(contract.currency ?? 'USD');
    setEditStartDate(contract.start_date ?? '');
    setEditEndDate(contract.end_date ?? '');
    setEditStatus(contract.status);
    setEditContactId(contract.contact_id ?? contract.contact?.id ?? null);
    setEditCompanyId(contract.company_id ?? contract.company?.id ?? null);
    setEditDesignatedSignerEmail(contract.designated_signer_email ?? '');
    setShowEditModal(true);
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const data: ContractUpdate = {
        title: editTitle,
        contract_number: editContractNumber.trim() || null,
        scope: editScope || null,
        value: editValue ? parseFloat(editValue) : null,
        currency: editCurrency,
        start_date: editStartDate || null,
        end_date: editEndDate || null,
        status: editStatus,
        contact_id: editContactId,
        company_id: editCompanyId,
        designated_signer_email: editDesignatedSignerEmail.trim() || null,
      };
      await updateMutation.mutateAsync({ id: contract.id, data });
      setShowEditModal(false);
      showSuccess('Contract updated');
    } catch {
      showError('Failed to update contract');
    }
  };

  const handleDelete = async () => {
    try {
      await deleteMutation.mutateAsync(contract.id);
      showSuccess('Contract deleted');
      navigate('/contracts');
    } catch {
      showError('Failed to delete contract');
    }
  };

  const openSendModal = () => {
    // Pre-fill the recipient from the contract's designated signer
    // when set; the contact email remains the backend fallback when
    // this is blank, mirroring `ContractService.send_for_signature`.
    // Mirrors the inline pattern in ProposalDetail.openSendModal.
    setSendToEmail(contract.designated_signer_email?.trim() ?? '');
    setSendMessage('');
    setShowSendModal(true);
  };

  const handleSend = async () => {
    try {
      const email = sendToEmail.trim();
      const note = sendMessage.trim();
      const body = {
        ...(email && { to_email: email }),
        ...(note && { message: note }),
      };
      await sendMutation.mutateAsync({ id: contract.id, body });
      setShowSendModal(false);
      showSuccess('Contract sent for signature');
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to send contract');
    }
  };

  // Per-section inline save: throws so the editor stays in edit mode
  // on failure with an inline error. Toast is the secondary signal.
  const handleSectionSave = async (
    field: keyof ContractUpdate,
    value: string | null,
  ) => {
    try {
      await updateMutation.mutateAsync({
        id: contract.id,
        data: { [field]: value } as ContractUpdate,
      });
    } catch (err) {
      showError(extractApiErrorDetail(err) ?? 'Failed to save changes');
      throw err;
    }
  };

  // Build timeline + send checklist from the contract record.
  const timelineSteps = buildContractTimelineSteps(contract);
  const sendChecklist = buildContractSendChecklist(contract, {
    onEditContact: openEditModal,
  });
  const checklistReady = isChecklistReady(sendChecklist);
  const canSendStatus = canSend || canResend;

  return (
    <div className="space-y-6">
      <StickyActionBar triggerRef={actionRowRef}>
        {canEdit && (
          <Button size="sm" variant="secondary" onClick={openEditModal}>
            Edit
          </Button>
        )}
        {canSend && (
          <Button size="sm" onClick={openSendModal} disabled={sendMutation.isPending}>
            {sendMutation.isPending ? 'Sending...' : 'Send for Signature'}
          </Button>
        )}
        {canResend && (
          <Button size="sm" variant="secondary" onClick={openSendModal} disabled={sendMutation.isPending}>
            {sendMutation.isPending ? 'Resending...' : 'Resend'}
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
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">
                {contract.title}
              </h1>
              <ContractStatusBadge status={contract.status} />
              {contract.contract_number && (
                <span
                  className="inline-flex items-center rounded-md bg-gray-100 dark:bg-gray-700 px-2 py-0.5 text-xs font-mono font-medium text-gray-700 dark:text-gray-300"
                  title="Contract number"
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                >
                  {contract.contract_number}
                </span>
              )}
            </div>
            {/* Contact / company headline beneath the title — mirrors ProposalDetail */}
            {(contract.contact || contract.company) && (
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                {contract.contact && (
                  <Link
                    to={`/contacts/${contract.contact.id}`}
                    className="text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300"
                  >
                    {contract.contact.full_name}
                  </Link>
                )}
                {contract.contact && contract.company && (
                  <span className="mx-1 text-gray-400">&middot;</span>
                )}
                {contract.company && (
                  <Link
                    to={`/companies/${contract.company.id}`}
                    className="text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300"
                  >
                    {contract.company.name}
                  </Link>
                )}
              </p>
            )}
          </div>
        </div>

        {/* Action row — one primary CTA per status, secondary follows. */}
        <div ref={actionRowRef} className="flex flex-wrap items-center gap-2">
          {/* PRIMARY action — the highest-leverage next step per status. */}
          {canSend && (
            <Button
              onClick={openSendModal}
              leftIcon={<PaperAirplaneIcon className="h-4 w-4" />}
              disabled={sendMutation.isPending}
            >
              {sendMutation.isPending ? 'Sending...' : 'Send for Signature'}
            </Button>
          )}
          {canResend && (
            <Button
              variant="secondary"
              onClick={openSendModal}
              leftIcon={<PaperAirplaneIcon className="h-4 w-4" />}
              disabled={sendMutation.isPending}
            >
              {sendMutation.isPending ? 'Resending...' : 'Resend'}
            </Button>
          )}

          {/* SECONDARY — common follow-ups when applicable. */}
          {hasSignedPdf && (
            <Button
              variant="secondary"
              leftIcon={<ArrowDownTrayIcon className="h-4 w-4" />}
              onClick={() => {
                window.open(`/api/contracts/${contract.id}/signed-pdf`, '_blank', 'noopener');
              }}
            >
              Download Signed PDF
            </Button>
          )}
          {canEdit && (
            <Button variant="secondary" onClick={openEditModal} leftIcon={<PencilIcon className="h-4 w-4" />}>
              Edit
            </Button>
          )}

          {/* Delete always last + always danger variant. */}
          <Button variant="danger" onClick={() => setShowDeleteConfirm(true)} leftIcon={<TrashIcon className="h-4 w-4" />}>
            Delete
          </Button>
        </div>
      </div>

      {/* Status timeline — Draft → Sent → Signed → Active (→ Expired
          when end_date is set). Tells the lifecycle story at a glance
          and mirrors the proposal surface so the two flows feel like
          one product. */}
      <StatusTimeline steps={timelineSteps} />

      {/* Pre-send checklist — auto-hides when every required gate
          passes so a polished contract doesn't carry the gate card. */}
      {canSendStatus && !checklistReady && (
        <SendChecklist items={sendChecklist} hideWhenAllGreen />
      )}

      {/* Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main */}
        <div className="lg:col-span-2 space-y-6">
          <InlineSectionEditor
            title="Scope"
            value={contract.scope ?? null}
            onSave={(v) => handleSectionSave('scope', v)}
            canEdit={canEdit}
            rows={8}
            placeholder="Deliverables, terms, what each party is committing to. This is the body of what gets signed."
          />

          <ContractAttachmentsSection contractId={contract.id} canEdit={canEdit} />
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Details */}
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-gray-100 dark:border-gray-700">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-4">Details</h2>
            <dl className="space-y-3">
              {contract.value != null && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Value</dt>
                  <dd className="text-sm font-medium text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {formatCurrency(contract.value, contract.currency)}
                  </dd>
                </div>
              )}
              {contract.start_date && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Start Date</dt>
                  <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{formatDate(contract.start_date)}</dd>
                </div>
              )}
              {contract.end_date && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">End Date</dt>
                  <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{formatDate(contract.end_date)}</dd>
                </div>
              )}
              <div>
                <dt className="text-xs text-gray-500 dark:text-gray-400">Created</dt>
                <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{formatDate(contract.created_at)}</dd>
              </div>
              {contract.sent_at && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Sent</dt>
                  <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{formatDate(contract.sent_at)}</dd>
                </div>
              )}
              {contract.signed_at && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Signed</dt>
                  <dd className="text-sm font-medium text-green-600 dark:text-green-400">{formatDate(contract.signed_at)}</dd>
                </div>
              )}
              {contract.signed_by_name && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Signed by</dt>
                  <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{contract.signed_by_name}</dd>
                </div>
              )}
            </dl>
          </div>

          {/* Related */}
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-gray-100 dark:border-gray-700">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-4">Related</h2>
            <dl className="space-y-3">
              {contract.contact && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Contact</dt>
                  <dd className="text-sm font-medium">
                    <Link to={`/contacts/${contract.contact.id}`} className="text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300">
                      {contract.contact.full_name}
                    </Link>
                  </dd>
                </div>
              )}
              {contract.company && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Company</dt>
                  <dd className="text-sm font-medium">
                    <Link to={`/companies/${contract.company.id}`} className="text-primary-600 hover:text-primary-900 dark:text-primary-400 dark:hover:text-primary-300">
                      {contract.company.name}
                    </Link>
                  </dd>
                </div>
              )}
              {!contract.contact && !contract.company && (
                <p className="text-sm text-gray-500 dark:text-gray-400">No related entities</p>
              )}
            </dl>
          </div>

          <EntitySharing
            entityType="contracts"
            entityId={contract.id}
            ownerName={ownerName}
            canManage={canManage}
          />

          <ContractAuditCard contract={contract} />
        </div>
      </div>

      {/* Send / Resend Modal */}
      <Modal
        isOpen={showSendModal}
        onClose={() => setShowSendModal(false)}
        title={canSend ? 'Send for Signature' : 'Resend for Signature'}
        size="md"
      >
        <div className="space-y-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {canSend
              ? 'Send this contract to the signer. Leave the email blank to use the contact\'s default address.'
              : 'Resend this contract to the signer.'}
          </p>
          <div>
            <label htmlFor="send-to-email" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Override recipient email
            </label>
            <input
              id="send-to-email"
              type="email"
              autoComplete="email"
              spellCheck={false}
              value={sendToEmail}
              onChange={(e) => setSendToEmail(e.target.value)}
              placeholder="Leave blank to use contact email..."
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            />
          </div>
          <div>
            <label htmlFor="send-message" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Custom message <span className="font-normal text-gray-400">(optional)</span>
            </label>
            <textarea
              id="send-message"
              rows={3}
              value={sendMessage}
              onChange={(e) => setSendMessage(e.target.value)}
              placeholder="Add a personal note to the signing email..."
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            />
          </div>
          <div className="flex justify-end gap-3 pt-2 border-t border-gray-200 dark:border-gray-700">
            <Button type="button" variant="secondary" onClick={() => setShowSendModal(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleSend}
              disabled={sendMutation.isPending}
              leftIcon={<PaperAirplaneIcon className="h-4 w-4" />}
            >
              {sendMutation.isPending ? 'Sending...' : canSend ? 'Send' : 'Resend'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Edit Modal */}
      <Modal isOpen={showEditModal} onClose={() => setShowEditModal(false)} title="Edit Contract" size="lg" fullScreenOnMobile>
        <form onSubmit={handleEditSubmit} className="space-y-4">
          <div>
            <label htmlFor="edit-title" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Title *</label>
            <input
              type="text"
              id="edit-title"
              required
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="edit-contract-number" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Contract number
              </label>
              <input
                type="text"
                id="edit-contract-number"
                value={editContractNumber}
                onChange={(e) => setEditContractNumber(e.target.value)}
                placeholder="e.g. CO-2026-0001"
                spellCheck={false}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm font-mono"
              />
            </div>
            <div>
              <label htmlFor="edit-designated-signer-email" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                Designated signer email
              </label>
              <input
                type="email"
                id="edit-designated-signer-email"
                value={editDesignatedSignerEmail}
                onChange={(e) => setEditDesignatedSignerEmail(e.target.value)}
                placeholder="signer@company.com"
                autoComplete="email"
                spellCheck={false}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
              />
            </div>
          </div>
          <div>
            <label htmlFor="edit-scope" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Scope</label>
            <textarea
              id="edit-scope"
              rows={4}
              value={editScope}
              onChange={(e) => setEditScope(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            />
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="edit-value" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Value</label>
              <div className="mt-1 flex rounded-md shadow-sm">
                <input
                  id="edit-value"
                  type="number"
                  step="0.01"
                  min="0"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  className="block w-full rounded-l-md border-gray-300 dark:border-gray-600 focus:border-primary-500 focus:ring-primary-500 sm:text-sm bg-white dark:bg-gray-700 dark:text-gray-100"
                />
                <select
                  aria-label="Currency"
                  value={editCurrency}
                  onChange={(e) => setEditCurrency(e.target.value)}
                  className="rounded-r-md border-l-0 border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-600 text-gray-500 dark:text-gray-300 sm:text-sm"
                >
                  <option value="USD">USD</option>
                  <option value="EUR">EUR</option>
                  <option value="GBP">GBP</option>
                </select>
              </div>
            </div>
            <div>
              <label htmlFor="edit-status" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Status</label>
              <select
                id="edit-status"
                value={editStatus}
                onChange={(e) => setEditStatus(e.target.value)}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm bg-white dark:bg-gray-700 dark:text-gray-100"
              >
                <option value="draft">Draft</option>
                <option value="sent">Sent</option>
                <option value="signed">Signed</option>
                <option value="active">Active</option>
                <option value="expired">Expired</option>
                <option value="terminated">Terminated</option>
              </select>
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label htmlFor="edit-start-date" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Start Date</label>
              <input
                id="edit-start-date"
                type="date"
                value={editStartDate}
                onChange={(e) => setEditStartDate(e.target.value)}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
              />
            </div>
            <div>
              <label htmlFor="edit-end-date" className="block text-sm font-medium text-gray-700 dark:text-gray-300">End Date</label>
              <input
                id="edit-end-date"
                type="date"
                value={editEndDate}
                onChange={(e) => setEditEndDate(e.target.value)}
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
              />
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <SearchableSelect
              label="Contact"
              id="edit-contact"
              value={editContactId}
              onChange={setEditContactId}
              options={contactOptions}
              placeholder="Search contacts..."
            />
            <SearchableSelect
              label="Company"
              id="edit-company"
              value={editCompanyId}
              onChange={setEditCompanyId}
              options={companyOptions}
              placeholder="Search companies..."
            />
          </div>
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <Button type="button" variant="secondary" onClick={() => setShowEditModal(false)}>Cancel</Button>
            <Button type="submit" disabled={updateMutation.isPending || !editTitle.trim()}>
              {updateMutation.isPending ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleDelete}
        title="Delete Contract"
        message={`Are you sure you want to delete "${contract.title}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}

export default ContractDetailPage;
