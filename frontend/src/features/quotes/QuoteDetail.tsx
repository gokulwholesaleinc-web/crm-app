import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import {
  ArrowLeftIcon,
  PaperAirplaneIcon,
  CheckIcon,
  XMarkIcon,
  PlusIcon,
  TrashIcon,
  PencilIcon,
  CubeIcon,
} from '@heroicons/react/24/outline';
import { Button, Modal, ConfirmDialog, StatusBadge } from '../../components/ui';
import type { StatusType } from '../../components/ui/Badge';
import {
  useQuote,
  useUpdateQuote,
  useDeleteQuote,
  useSendQuote,
  useAcceptQuote,
  useRejectQuote,
  useAddLineItem,
  useRemoveLineItem,
  useBundles,
  useAddBundleToQuote,
} from '../../hooks/useQuotes';
import { formatCurrency, formatDate } from '../../utils/formatters';
import { usePageTitle } from '../../hooks/usePageTitle';
import { showSuccess, showError } from '../../utils/toast';
import type { QuoteUpdate, QuoteLineItemCreate, ProductBundle } from '../../types';

function QuoteDetailPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const quoteId = id ? parseInt(id, 10) : undefined;

  const { data: quote, isLoading, error } = useQuote(quoteId);
  usePageTitle(quote ? `Quote - ${quote.title}` : 'Quote');

  const updateQuoteMutation = useUpdateQuote();
  const deleteQuoteMutation = useDeleteQuote();
  const sendQuoteMutation = useSendQuote();
  const acceptQuoteMutation = useAcceptQuote();
  const rejectQuoteMutation = useRejectQuote();
  const addLineItemMutation = useAddLineItem();
  const removeLineItemMutation = useRemoveLineItem();
  const addBundleMutation = useAddBundleToQuote();
  const { data: bundlesData } = useBundles({ is_active: true });
  const bundles = bundlesData?.items ?? [];

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [showBundleDropdown, setShowBundleDropdown] = useState(false);
  const [showAddLineItem, setShowAddLineItem] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editTitle, setEditTitle] = useState('');
  const [editDescription, setEditDescription] = useState('');

  // Line item form state
  const [newItemDescription, setNewItemDescription] = useState('');
  const [newItemQuantity, setNewItemQuantity] = useState(1);
  const [newItemPrice, setNewItemPrice] = useState(0);
  const [newItemDiscount, setNewItemDiscount] = useState(0);

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

  if (error || !quote) {
    return (
      <div className="text-center py-12">
        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">Quote not found</h3>
        <Link to="/quotes" className="mt-2 text-primary-600 hover:text-primary-900">
          Back to Quotes
        </Link>
      </div>
    );
  }

  const handleSend = async () => {
    try {
      await sendQuoteMutation.mutateAsync(quote.id);
      showSuccess('Quote sent');
    } catch {
      showError('Failed to send quote');
    }
  };

  const handleAccept = async () => {
    try {
      await acceptQuoteMutation.mutateAsync(quote.id);
      showSuccess('Quote accepted');
    } catch {
      showError('Failed to accept quote');
    }
  };

  const handleReject = async () => {
    try {
      await rejectQuoteMutation.mutateAsync(quote.id);
      showSuccess('Quote rejected');
    } catch {
      showError('Failed to reject quote');
    }
  };

  const handleDelete = async () => {
    try {
      await deleteQuoteMutation.mutateAsync(quote.id);
      showSuccess('Quote deleted');
      navigate('/quotes');
    } catch {
      showError('Failed to delete quote');
    }
  };

  const handleAddLineItem = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const data: QuoteLineItemCreate = {
        description: newItemDescription,
        quantity: newItemQuantity,
        unit_price: newItemPrice,
        discount: newItemDiscount,
        sort_order: quote.line_items.length,
      };
      await addLineItemMutation.mutateAsync({ quoteId: quote.id, data });
      setShowAddLineItem(false);
      setNewItemDescription('');
      setNewItemQuantity(1);
      setNewItemPrice(0);
      setNewItemDiscount(0);
      showSuccess('Line item added');
    } catch {
      showError('Failed to add line item');
    }
  };

  const handleRemoveLineItem = async (itemId: number) => {
    try {
      await removeLineItemMutation.mutateAsync({ quoteId: quote.id, itemId });
      showSuccess('Line item removed');
    } catch {
      showError('Failed to remove line item');
    }
  };

  const handleAddBundle = async (bundle: ProductBundle) => {
    setShowBundleDropdown(false);
    try {
      await addBundleMutation.mutateAsync({ quoteId: quote.id, bundleId: bundle.id });
      showSuccess(`Added bundle "${bundle.name}"`);
    } catch {
      showError('Failed to add bundle');
    }
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const data: QuoteUpdate = {
        title: editTitle,
        description: editDescription || null,
      };
      await updateQuoteMutation.mutateAsync({ id: quote.id, data });
      setShowEditModal(false);
      showSuccess('Quote updated');
    } catch {
      showError('Failed to update quote');
    }
  };

  const openEditModal = () => {
    setEditTitle(quote.title);
    setEditDescription(quote.description ?? '');
    setShowEditModal(true);
  };

  const isDraft = quote.status === 'draft';
  const canSend = isDraft;
  const canAcceptReject = quote.status === 'sent' || quote.status === 'viewed';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          <Link
            to="/quotes"
            className="p-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
            aria-label="Back to quotes"
          >
            <ArrowLeftIcon className="h-5 w-5" aria-hidden="true" />
          </Link>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-gray-100">
                {quote.title}
              </h1>
              <StatusBadge status={quote.status as StatusType} size="sm" showDot={false} />
            </div>
            <p className="text-sm text-gray-500 dark:text-gray-400">{quote.quote_number}</p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {isDraft && (
            <Button variant="secondary" onClick={openEditModal} leftIcon={<PencilIcon className="h-4 w-4" />}>
              Edit
            </Button>
          )}
          {canSend && (
            <Button
              onClick={handleSend}
              leftIcon={<PaperAirplaneIcon className="h-4 w-4" />}
              disabled={sendQuoteMutation.isPending}
            >
              {sendQuoteMutation.isPending ? 'Sending...' : 'Send'}
            </Button>
          )}
          {canAcceptReject && (
            <>
              <Button
                onClick={handleAccept}
                leftIcon={<CheckIcon className="h-4 w-4" />}
                disabled={acceptQuoteMutation.isPending}
              >
                Accept
              </Button>
              <Button
                variant="secondary"
                onClick={handleReject}
                leftIcon={<XMarkIcon className="h-4 w-4" />}
                disabled={rejectQuoteMutation.isPending}
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

      {/* Quote Details Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main Content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Description */}
          {quote.description && (
            <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
              <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Description</h2>
              <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap">{quote.description}</p>
            </div>
          )}

          {/* Line Items */}
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg border border-transparent dark:border-gray-700">
            <div className="px-6 py-4 flex items-center justify-between border-b border-gray-200 dark:border-gray-700">
              <h2 className="text-lg font-medium text-gray-900 dark:text-gray-100">Line Items</h2>
              {isDraft && (
                <div className="flex items-center gap-3">
                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setShowBundleDropdown((v) => !v)}
                      className="inline-flex items-center text-sm text-primary-600 hover:text-primary-900 dark:hover:text-primary-300"
                      disabled={addBundleMutation.isPending}
                    >
                      <CubeIcon className="h-4 w-4 mr-1" aria-hidden="true" />
                      {addBundleMutation.isPending ? 'Adding...' : 'Add Bundle'}
                    </button>
                    {showBundleDropdown && bundles.length > 0 && (
                      <div className="absolute right-0 mt-1 w-56 rounded-md shadow-lg bg-white dark:bg-gray-700 ring-1 ring-black ring-opacity-5 z-10">
                        <div className="py-1 max-h-60 overflow-y-auto">
                          {bundles.map((bundle: ProductBundle) => (
                            <button
                              key={bundle.id}
                              type="button"
                              onClick={() => handleAddBundle(bundle)}
                              className="block w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600"
                            >
                              <span className="font-medium">{bundle.name}</span>
                              <span className="ml-2 text-xs text-gray-400">
                                {bundle.items.length} item{bundle.items.length !== 1 ? 's' : ''}
                              </span>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowAddLineItem(true)}
                    className="inline-flex items-center text-sm text-primary-600 hover:text-primary-900 dark:hover:text-primary-300"
                  >
                    <PlusIcon className="h-4 w-4 mr-1" aria-hidden="true" />
                    Add Item
                  </button>
                </div>
              )}
            </div>

            {quote.line_items.length === 0 ? (
              <div className="px-6 py-8 text-center text-sm text-gray-500 dark:text-gray-400">
                No line items yet.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead className="bg-gray-50 dark:bg-gray-900">
                    <tr>
                      <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                      <th scope="col" className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Qty</th>
                      <th scope="col" className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Unit Price</th>
                      <th scope="col" className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Discount</th>
                      <th scope="col" className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase">Total</th>
                      {isDraft && (
                        <th scope="col" className="px-4 py-3 w-10">
                          <span className="sr-only">Actions</span>
                        </th>
                      )}
                    </tr>
                  </thead>
                  <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                    {quote.line_items.map((item) => (
                      <tr key={item.id}>
                        <td className="px-6 py-4 text-sm text-gray-900 dark:text-gray-100">{item.description}</td>
                        <td className="px-4 py-4 text-sm text-right text-gray-500 dark:text-gray-400" style={{ fontVariantNumeric: 'tabular-nums' }}>{item.quantity}</td>
                        <td className="px-4 py-4 text-sm text-right text-gray-500 dark:text-gray-400" style={{ fontVariantNumeric: 'tabular-nums' }}>{formatCurrency(item.unit_price, quote.currency)}</td>
                        <td className="px-4 py-4 text-sm text-right text-gray-500 dark:text-gray-400" style={{ fontVariantNumeric: 'tabular-nums' }}>{formatCurrency(item.discount, quote.currency)}</td>
                        <td className="px-4 py-4 text-sm text-right font-medium text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>{formatCurrency(item.total, quote.currency)}</td>
                        {isDraft && (
                          <td className="px-4 py-4">
                            <button
                              type="button"
                              onClick={() => handleRemoveLineItem(item.id)}
                              className="p-1 text-gray-400 hover:text-red-600 dark:hover:text-red-400"
                              aria-label={`Remove ${item.description}`}
                              disabled={removeLineItemMutation.isPending}
                            >
                              <TrashIcon className="h-4 w-4" aria-hidden="true" />
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {/* Totals */}
            <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 space-y-1" style={{ fontVariantNumeric: 'tabular-nums' }}>
              <div className="flex justify-between text-sm text-gray-600 dark:text-gray-400">
                <span>Subtotal</span>
                <span>{formatCurrency(quote.subtotal, quote.currency)}</span>
              </div>
              {quote.discount_type && quote.discount_value > 0 && (
                <div className="flex justify-between text-sm text-gray-600 dark:text-gray-400">
                  <span>Discount ({quote.discount_type === 'percent' ? `${quote.discount_value}%` : 'fixed'})</span>
                  <span>
                    -{formatCurrency(
                      quote.discount_type === 'percent'
                        ? quote.subtotal * (quote.discount_value / 100)
                        : quote.discount_value,
                      quote.currency
                    )}
                  </span>
                </div>
              )}
              {quote.tax_amount > 0 && (
                <div className="flex justify-between text-sm text-gray-600 dark:text-gray-400">
                  <span>Tax ({quote.tax_rate}%)</span>
                  <span>{formatCurrency(quote.tax_amount, quote.currency)}</span>
                </div>
              )}
              <div className="flex justify-between text-base font-semibold text-gray-900 dark:text-gray-100 pt-2 border-t border-gray-200 dark:border-gray-700">
                <span>Total</span>
                <span>{formatCurrency(quote.total, quote.currency)}</span>
              </div>
            </div>
          </div>

          {/* Terms and Conditions */}
          {quote.terms_and_conditions && (
            <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
              <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Terms and Conditions</h2>
              <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap">{quote.terms_and_conditions}</p>
            </div>
          )}
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Quote Info */}
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
            <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-4">Details</h2>
            <dl className="space-y-3">
              <div>
                <dt className="text-xs text-gray-500 dark:text-gray-400">Payment Type</dt>
                <dd className="mt-0.5">
                  <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                    quote.payment_type === 'subscription'
                      ? 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300'
                      : 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300'
                  }`}>
                    {quote.payment_type === 'subscription' ? 'Subscription' : 'One-Time'}
                  </span>
                  {quote.payment_type === 'subscription' && quote.recurring_interval && (
                    <span className="ml-2 text-sm text-gray-500 dark:text-gray-400 capitalize">
                      {quote.recurring_interval}
                    </span>
                  )}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500 dark:text-gray-400">Currency</dt>
                <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{quote.currency}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500 dark:text-gray-400">Valid Until</dt>
                <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{formatDate(quote.valid_until)}</dd>
              </div>
              <div>
                <dt className="text-xs text-gray-500 dark:text-gray-400">Created</dt>
                <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{formatDate(quote.created_at)}</dd>
              </div>
              {quote.sent_at && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Sent</dt>
                  <dd className="text-sm font-medium text-gray-900 dark:text-gray-100">{formatDate(quote.sent_at)}</dd>
                </div>
              )}
              {quote.accepted_at && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Accepted</dt>
                  <dd className="text-sm font-medium text-green-600 dark:text-green-400">{formatDate(quote.accepted_at)}</dd>
                </div>
              )}
              {quote.rejected_at && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Rejected</dt>
                  <dd className="text-sm font-medium text-red-600 dark:text-red-400">{formatDate(quote.rejected_at)}</dd>
                </div>
              )}
            </dl>
          </div>

          {/* Related Entities */}
          <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
            <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-4">Related</h2>
            <dl className="space-y-3">
              {quote.contact && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Contact</dt>
                  <dd className="text-sm font-medium">
                    <Link to={`/contacts/${quote.contact.id}`} className="text-primary-600 hover:text-primary-900">
                      {quote.contact.full_name}
                    </Link>
                  </dd>
                </div>
              )}
              {quote.company && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Company</dt>
                  <dd className="text-sm font-medium">
                    <Link to={`/companies/${quote.company.id}`} className="text-primary-600 hover:text-primary-900">
                      {quote.company.name}
                    </Link>
                  </dd>
                </div>
              )}
              {quote.opportunity && (
                <div>
                  <dt className="text-xs text-gray-500 dark:text-gray-400">Opportunity</dt>
                  <dd className="text-sm font-medium">
                    <Link to={`/opportunities/${quote.opportunity.id}`} className="text-primary-600 hover:text-primary-900">
                      {quote.opportunity.name}
                    </Link>
                  </dd>
                </div>
              )}
              {!quote.contact && !quote.company && !quote.opportunity && (
                <p className="text-sm text-gray-500 dark:text-gray-400">No related entities</p>
              )}
            </dl>
          </div>

          {/* Notes */}
          {quote.notes && (
            <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-6 border border-transparent dark:border-gray-700">
              <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-2">Notes</h2>
              <p className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap">{quote.notes}</p>
            </div>
          )}
        </div>
      </div>

      {/* Add Line Item Modal */}
      <Modal
        isOpen={showAddLineItem}
        onClose={() => setShowAddLineItem(false)}
        title="Add Line Item"
        size="md"
      >
        <form onSubmit={handleAddLineItem} className="space-y-4">
          <div>
            <label htmlFor="new-item-desc" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Description *
            </label>
            <input
              type="text"
              id="new-item-desc"
              required
              value={newItemDescription}
              onChange={(e) => setNewItemDescription(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
              placeholder="Item description..."
            />
          </div>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label htmlFor="new-item-qty" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Quantity</label>
              <input
                type="number"
                id="new-item-qty"
                value={newItemQuantity}
                onChange={(e) => setNewItemQuantity(parseFloat(e.target.value) || 0)}
                min="0"
                step="any"
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
              />
            </div>
            <div>
              <label htmlFor="new-item-price" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Unit Price</label>
              <input
                type="number"
                id="new-item-price"
                value={newItemPrice}
                onChange={(e) => setNewItemPrice(parseFloat(e.target.value) || 0)}
                min="0"
                step="any"
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
              />
            </div>
            <div>
              <label htmlFor="new-item-disc" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Discount</label>
              <input
                type="number"
                id="new-item-disc"
                value={newItemDiscount}
                onChange={(e) => setNewItemDiscount(parseFloat(e.target.value) || 0)}
                min="0"
                step="any"
                className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
              />
            </div>
          </div>
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <Button type="button" variant="secondary" onClick={() => setShowAddLineItem(false)}>Cancel</Button>
            <Button type="submit" disabled={addLineItemMutation.isPending || !newItemDescription.trim()}>
              {addLineItemMutation.isPending ? 'Adding...' : 'Add Item'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Edit Quote Modal */}
      <Modal
        isOpen={showEditModal}
        onClose={() => setShowEditModal(false)}
        title="Edit Quote"
        size="md"
      >
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
          <div>
            <label htmlFor="edit-desc" className="block text-sm font-medium text-gray-700 dark:text-gray-300">Description</label>
            <textarea
              id="edit-desc"
              rows={3}
              value={editDescription}
              onChange={(e) => setEditDescription(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            />
          </div>
          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
            <Button type="button" variant="secondary" onClick={() => setShowEditModal(false)}>Cancel</Button>
            <Button type="submit" disabled={updateQuoteMutation.isPending || !editTitle.trim()}>
              {updateQuoteMutation.isPending ? 'Saving...' : 'Save'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleDelete}
        title="Delete Quote"
        message={`Are you sure you want to delete "${quote.title}"? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteQuoteMutation.isPending}
      />
    </div>
  );
}

export default QuoteDetailPage;
