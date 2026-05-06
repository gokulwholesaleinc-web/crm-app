import { useState, useRef, lazy, Suspense } from 'react';
import { useParams, useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Button, HelpLink, Spinner, Modal, ConfirmDialog } from '../../components/ui';
import { TabBar, ActivitiesTab, CommonTabContent, SuspenseFallback } from '../../components/shared/DetailPageShell';
import { EmailComposeModal, EmailThread, GmailReconnectBanner } from '../../components/email';
import { useGmailStatus } from '../../hooks/useGmailStatus';
import { ContactForm } from './components/ContactForm';
import {
  contactFormDataToUpdate,
  contactToFormData,
  type ContactFormData,
} from './components/contactFormHelpers';
import { NextBestActionCard } from '../../components/ai';
import { useContact, useDeleteContact, useUpdateContact } from '../../hooks/useContacts';
import { useContactAliases, useAddAlias, useDeleteAlias } from '../../hooks/useContactAliases';
import { showSuccess, showError } from '../../utils/toast';
import { useQuotes } from '../../hooks/useQuotes';
import { useProposals } from '../../hooks/useProposals';
import { useSubscriptions } from '../../hooks/usePayments';
import { formatDate, formatPhoneNumber, formatCurrency } from '../../utils/formatters';
import { StatusBadge } from '../../components/ui';
import type { Quote, Proposal } from '../../types';
import type { ThreadEmailItem } from '../../types/email';

const ContractsList = lazy(() => import('../../components/shared/ContractsList'));
const PaymentSummary = lazy(() => import('../../components/shared/PaymentSummary'));
const DocumentsTab = lazy(() => import('../../components/shared/DocumentsTab'));
const EntityPaymentsTab = lazy(() => import('../../components/shared/EntityPaymentsTab'));
const SendInvoiceModal = lazy(() =>
  import('../payments/components/SendInvoiceModal').then(m => ({ default: m.SendInvoiceModal }))
);
const OnboardingLinkGenerator = lazy(() =>
  import('../payments/components/OnboardingLinkGenerator').then(m => ({ default: m.OnboardingLinkGenerator }))
);

type TabType = 'details' | 'activities' | 'notes' | 'emails' | 'contracts' | 'quotes' | 'proposals' | 'payments' | 'documents' | 'attachments' | 'history' | 'sharing';

const TABS: { id: TabType; name: string }[] = [
  { id: 'details', name: 'Details' },
  { id: 'activities', name: 'Activities' },
  { id: 'notes', name: 'Notes' },
  { id: 'emails', name: 'Emails' },
  { id: 'contracts', name: 'Contracts' },
  { id: 'quotes', name: 'Quotes' },
  { id: 'proposals', name: 'Proposals' },
  { id: 'payments', name: 'Payments' },
  { id: 'documents', name: 'Documents' },
  { id: 'attachments', name: 'Attachments' },
  { id: 'history', name: 'History' },
  { id: 'sharing', name: 'Sharing' },
];

const TAB_IDS: ReadonlySet<TabType> = new Set(TABS.map((t) => t.id));

function ContactDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const contactId = id ? parseInt(id, 10) : undefined;
  // Honor `?tab=` so deep links from the email search modal land on
  // the right tab; `?email=` carries the kind:id deep-link target the
  // EmailThread will scroll to.
  const initialTab = (() => {
    const requested = searchParams.get('tab');
    return requested && TAB_IDS.has(requested as TabType)
      ? (requested as TabType)
      : 'details';
  })();
  const [activeTab, setActiveTab] = useState<TabType>(initialTab);
  const targetEmail = searchParams.get('email');
  const [showEditForm, setShowEditForm] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showEmailCompose, setShowEmailCompose] = useState(false);
  const [showInvoiceModal, setShowInvoiceModal] = useState(false);
  const [replyToEmail, setReplyToEmail] = useState<ThreadEmailItem | null>(null);
  const [aliasInput, setAliasInput] = useState('');
  const [aliasError, setAliasError] = useState<string | null>(null);
  const aliasInputRef = useRef<HTMLInputElement>(null);

  const { data: contact, isLoading, error } = useContact(contactId);
  const { data: gmailStatus } = useGmailStatus();
  const gmailNeedsReconnect = gmailStatus?.state === 'needs_reconnect';
  const deleteContactMutation = useDeleteContact();
  const updateContactMutation = useUpdateContact();
  const { data: aliases = [] } = useContactAliases(contactId);
  const addAliasMutation = useAddAlias(contactId ?? 0);
  const deleteAliasMutation = useDeleteAlias(contactId ?? 0);

  const { data: quotesData } = useQuotes(
    activeTab === 'quotes' && contactId ? { contact_id: contactId } : undefined
  );
  const { data: proposalsData } = useProposals(
    activeTab === 'proposals' && contactId ? { contact_id: contactId } : undefined
  );
  // Header badge — surface that this contact has a recurring billing
  // arrangement so Giancarlo doesn't have to dig into the Payments tab
  // to see it. Only fetch once we have a contactId; status='active'
  // filter narrows to subs Stripe is currently charging on.
  const { data: subscriptionsData } = useSubscriptions(
    contactId ? { contact_id: contactId, status: 'active', page_size: 1 } : undefined
  );
  const quotes = quotesData?.items ?? [];
  const proposals = proposalsData?.items ?? [];
  const hasActiveSubscription = (subscriptionsData?.total ?? 0) > 0;

  const handleEditSubmit = async (data: ContactFormData) => {
    if (!contactId) return;
    try {
      await updateContactMutation.mutateAsync({ id: contactId, data: contactFormDataToUpdate(data) });
      setShowEditForm(false);
      showSuccess('Contact updated successfully');
    } catch {
      showError('Failed to update contact');
    }
  };

  const handleAddAlias = async () => {
    const trimmed = aliasInput.trim().toLowerCase();
    if (!trimmed) return;
    setAliasError(null);
    try {
      await addAliasMutation.mutateAsync({ email: trimmed });
      setAliasInput('');
      aliasInputRef.current?.focus();
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      setAliasError(status === 409 ? 'That address is already in use' : 'Failed to add alias');
    }
  };

  const getInitialFormData = (): Partial<ContactFormData> | undefined => {
    if (!contact) return undefined;
    return contactToFormData(contact);
  };

  const handleDeleteConfirm = async () => {
    if (!contactId) return;
    try {
      await deleteContactMutation.mutateAsync(contactId);
      navigate('/contacts');
    } catch {
      // Error is handled by the mutation
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  const errorMessage = error instanceof Error ? error.message : error ? String(error) : null;

  if (errorMessage || !contact) {
    return (
      <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
        <div className="flex">
          <div className="ml-3">
            <h3 className="text-sm font-medium text-red-800 dark:text-red-300">
              {errorMessage || 'Contact not found'}
            </h3>
            <div className="mt-4">
              <Link to="/contacts" className="text-red-600 hover:text-red-500">
                Back to contacts
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center space-x-4">
          <Link
            to="/contacts"
            className="text-gray-400 hover:text-gray-500 dark:hover:text-gray-300 flex-shrink-0"
            aria-label="Back to contacts"
          >
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </Link>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100 truncate">
                {contact.first_name} {contact.last_name}
              </h1>
              {hasActiveSubscription && (
                <span
                  className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300"
                  title="This contact has at least one active Stripe subscription"
                >
                  <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  Subscriber
                </span>
              )}
            </div>
            {(contact.job_title || contact.company?.name) && (
              <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                {contact.job_title}
                {contact.job_title && contact.company?.name && ' at '}
                {contact.company?.name && (
                  <Link
                    to={`/companies/${contact.company.id}`}
                    className="text-primary-600 hover:text-primary-500 focus-visible:underline focus-visible:outline-none"
                  >
                    {contact.company.name}
                  </Link>
                )}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <Button
            variant="primary"
            onClick={() => setShowEmailCompose(true)}
            disabled={!contact.email}
            title={contact.email ? undefined : 'Add an email address to this contact before sending'}
            className="flex-1 sm:flex-none"
          >
            Send Email
          </Button>
          <Button
            variant="secondary"
            onClick={() => setShowInvoiceModal(true)}
            disabled={!contact.email}
            title={contact.email ? undefined : 'Add an email address to this contact before sending'}
            className="flex-1 sm:flex-none"
          >
            Send Invoice
          </Button>
          <Button
            variant="secondary"
            onClick={() => navigate(`/proposals?action=new&contact_id=${contactId}${contact.company_id ? `&company_id=${contact.company_id}` : ''}`)}
            className="flex-1 sm:flex-none"
          >
            Create Proposal
          </Button>
          <Button variant="secondary" onClick={() => setShowEditForm(true)} className="flex-1 sm:flex-none">
            Edit
          </Button>
          <Button
            variant="danger"
            onClick={() => setShowDeleteConfirm(true)}
            isLoading={deleteContactMutation.isPending}
            className="flex-1 sm:flex-none"
          >
            Delete
          </Button>
        </div>
      </div>

      {/* AI Suggestions */}
      <NextBestActionCard entityType="contact" entityId={contact.id} />

      {/* Tabs */}
      <TabBar tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Tab Content */}
      {activeTab === 'details' && contactId && (
        <>
          <Suspense fallback={<div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 animate-pulse"><div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/3 mb-4" /><div className="h-20 bg-gray-200 dark:bg-gray-700 rounded" /></div>}>
            <PaymentSummary contactId={contactId} />
          </Suspense>
          <Suspense fallback={null}>
            <OnboardingLinkGenerator contactId={contactId} contactEmail={contact.email ?? undefined} />
          </Suspense>
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg">
            <div className="p-4 sm:p-6">
              <dl className="grid grid-cols-1 gap-4 sm:gap-x-4 sm:gap-y-6 sm:grid-cols-2">
                <div>
                  <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Email</dt>
                  <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                    <a href={`mailto:${contact.email}`} className="text-primary-600 hover:text-primary-500">
                      {contact.email}
                    </a>
                  </dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Email aliases</dt>
                  <dd className="mt-2">
                    {aliases.length > 0 && (
                      <div className="flex flex-wrap gap-2 mb-2">
                        {aliases.map((alias) => (
                          <span
                            key={alias.id}
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                          >
                            {alias.label && (
                              <span className="font-medium text-gray-500 dark:text-gray-400">{alias.label} &middot;</span>
                            )}
                            <span>{alias.email}</span>
                            <button
                              type="button"
                              aria-label={`Remove alias ${alias.email}`}
                              onClick={() => deleteAliasMutation.mutate(alias.id)}
                              className="ml-0.5 text-gray-400 hover:text-red-500 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-red-400 rounded"
                            >
                              <svg className="h-3 w-3" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                                <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                              </svg>
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                    <div className="flex items-center gap-2">
                      <input
                        ref={aliasInputRef}
                        type="email"
                        value={aliasInput}
                        onChange={(e) => { setAliasInput(e.target.value); setAliasError(null); }}
                        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); handleAddAlias(); } }}
                        placeholder="alias@example.com..."
                        spellCheck={false}
                        autoComplete="off"
                        className="flex-1 min-w-0 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-2.5 py-1 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                      />
                      <Button
                        type="button"
                        size="sm"
                        onClick={handleAddAlias}
                        disabled={!aliasInput.trim()}
                        isLoading={addAliasMutation.isPending}
                        className="shrink-0"
                      >
                        Add
                      </Button>
                    </div>
                    {aliasError && (
                      <p role="alert" aria-live="polite" className="mt-1 text-xs text-red-600 dark:text-red-400">{aliasError}</p>
                    )}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Phone</dt>
                  <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                    {contact.phone ? (
                      <a href={`tel:${contact.phone}`} className="text-primary-600 hover:text-primary-500">
                        {formatPhoneNumber(contact.phone)}
                      </a>
                    ) : '-'}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Company</dt>
                  <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                    {contact.company ? (
                      <Link
                        to={`/companies/${contact.company.id}`}
                        className="text-primary-600 hover:text-primary-500 focus-visible:underline focus-visible:outline-none"
                      >
                        {contact.company.name}
                      </Link>
                    ) : '-'}
                  </dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Job Title</dt>
                  <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">{contact.job_title || '-'}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Sales Code</dt>
                  <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">{contact.sales_code || '-'}</dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Address</dt>
                  <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">
                    {contact.address_line1 ? (
                      <>
                        {contact.address_line1}
                        {contact.address_line2 && <><br />{contact.address_line2}</>}
                        <br />
                        {[contact.city, contact.state, contact.postal_code].filter(Boolean).join(', ')}
                        {contact.country && <><br />{contact.country}</>}
                      </>
                    ) : '-'}
                  </dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Notes</dt>
                  <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">{contact.description || 'No notes'}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Created</dt>
                  <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">{formatDate(contact.created_at)}</dd>
                </div>
                <div>
                  <dt className="text-sm font-medium text-gray-500 dark:text-gray-400">Last Updated</dt>
                  <dd className="mt-1 text-sm text-gray-900 dark:text-gray-100">{formatDate(contact.updated_at)}</dd>
                </div>
              </dl>
            </div>
          </div>
        </>
      )}

      {activeTab === 'activities' && contactId && (
        <ActivitiesTab entityType="contact" entityId={contactId} />
      )}

      {activeTab === 'emails' && contactId && (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            <GmailReconnectBanner />
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Email Thread</h3>
              <div className="flex items-center gap-3">
                <HelpLink anchor="tutorial-email-thread" label="How email threads work" />
                <Button
                  variant="primary"
                  onClick={() => { setReplyToEmail(null); setShowEmailCompose(true); }}
                  disabled={gmailNeedsReconnect || !contact.email}
                  title={
                    !contact.email
                      ? 'Add an email address to this contact before composing'
                      : undefined
                  }
                  aria-describedby={gmailNeedsReconnect ? 'gmail-reconnect-banner' : undefined}
                >
                  Compose Email
                </Button>
              </div>
            </div>
            <EmailThread
              entityType="contacts"
              entityId={contactId}
              onReply={(email) => { setReplyToEmail(email); setShowEmailCompose(true); }}
              onCompose={() => { setReplyToEmail(null); setShowEmailCompose(true); }}
              highlightTarget={targetEmail}
            />
          </div>
        </div>
      )}

      {activeTab === 'contracts' && contactId && (
        <Suspense fallback={<SuspenseFallback />}>
          <ContractsList entityType="contact" entityId={contactId} />
        </Suspense>
      )}

      {activeTab === 'quotes' && contactId && (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700">
          {quotes.length === 0 ? (
            <div className="text-center py-12 px-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">No quotes for this contact.</p>
              <Link
                to={`/quotes/new?contact_id=${contactId}`}
                className="mt-2 inline-block text-sm text-primary-600 hover:text-primary-900 dark:hover:text-primary-300"
              >
                Create a Quote
              </Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-900">
                  <tr>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Quote</th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                    <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Total</th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Date</th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {quotes.map((quote: Quote) => (
                    <tr key={quote.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                      <td className="px-6 py-4 whitespace-nowrap text-sm">
                        <Link to={`/quotes/${quote.id}`} className="text-primary-600 hover:text-primary-900 dark:hover:text-primary-300">
                          {quote.title} ({quote.quote_number})
                        </Link>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <StatusBadge status={quote.status} size="sm" showDot={false} />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-right font-medium text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
                        {formatCurrency(quote.total)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {formatDate(quote.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === 'proposals' && contactId && (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700">
          {proposals.length === 0 ? (
            <div className="text-center py-12 px-4">
              <p className="text-sm text-gray-500 dark:text-gray-400">No proposals for this contact.</p>
              <Link
                to="/proposals"
                className="mt-2 inline-block text-sm text-primary-600 hover:text-primary-900 dark:hover:text-primary-300"
              >
                View Proposals
              </Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-900">
                  <tr>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Proposal</th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Status</th>
                    <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Date</th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {proposals.map((proposal: Proposal) => (
                    <tr key={proposal.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                      <td className="px-6 py-4 whitespace-nowrap text-sm">
                        <Link to={`/proposals/${proposal.id}`} className="text-primary-600 hover:text-primary-900 dark:hover:text-primary-300">
                          {proposal.title} ({proposal.proposal_number})
                        </Link>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <StatusBadge status={proposal.status} size="sm" showDot={false} />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {formatDate(proposal.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {activeTab === 'payments' && contactId && (
        <Suspense fallback={<SuspenseFallback />}>
          <EntityPaymentsTab entityType="contact" entityId={contactId} />
        </Suspense>
      )}

      {activeTab === 'documents' && contactId && (
        <Suspense fallback={<SuspenseFallback />}>
          <DocumentsTab entityType="contacts" entityId={contactId} />
        </Suspense>
      )}

      {contactId && (
        <CommonTabContent
          activeTab={activeTab}
          entityType="contacts"
          entityId={contactId}
          enabledTabs={['notes', 'attachments', 'history', 'sharing']}
        />
      )}

      {/* Email Compose Modal */}
      <EmailComposeModal
        isOpen={showEmailCompose}
        onClose={() => { setShowEmailCompose(false); setReplyToEmail(null); }}
        defaultTo={contact.email || ''}
        entityType="contacts"
        entityId={contactId}
        replyTo={replyToEmail}
      />

      {/* Edit Form Modal */}
      <Modal isOpen={showEditForm} onClose={() => setShowEditForm(false)} title="Edit Contact" size="lg">
        <ContactForm
          initialData={getInitialFormData()}
          onSubmit={handleEditSubmit}
          onCancel={() => setShowEditForm(false)}
          isLoading={updateContactMutation.isPending}
          submitLabel="Update Contact"
        />
      </Modal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleDeleteConfirm}
        title="Delete Contact"
        message={`Are you sure you want to delete ${contact.first_name} ${contact.last_name}? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteContactMutation.isPending}
      />

      {/* Send Invoice Modal */}
      <Suspense fallback={null}>
        <SendInvoiceModal
          isOpen={showInvoiceModal}
          onClose={() => setShowInvoiceModal(false)}
          contactId={contactId}
          contactEmail={contact.email ?? undefined}
        />
      </Suspense>
    </div>
  );
}

export default ContactDetailPage;
