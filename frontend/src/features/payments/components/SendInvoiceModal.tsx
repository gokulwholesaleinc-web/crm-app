import { useState } from 'react';
import { Modal, ModalFooter, Button } from '../../../components/ui';
import { useStripeCustomers, useSyncCustomer, useCreateAndSendInvoice } from '../../../hooks/usePayments';
import { showSuccess, showError } from '../../../utils/toast';
import type { StripeCustomer } from '../../../types';

interface SendInvoiceModalProps {
  isOpen: boolean;
  onClose: () => void;
  contactId?: number;
  contactEmail?: string;
  defaultAmount?: number;
}

const DUE_DAY_OPTIONS = [
  { value: 15, label: '15 days' },
  { value: 30, label: '30 days' },
  { value: 45, label: '45 days' },
  { value: 60, label: '60 days' },
];

export function SendInvoiceModal({
  isOpen,
  onClose,
  contactId,
  contactEmail,
  defaultAmount,
}: SendInvoiceModalProps) {
  const [amount, setAmount] = useState(defaultAmount?.toString() ?? '');
  const [description, setDescription] = useState('');
  const [dueDays, setDueDays] = useState(30);
  const [selectedCustomerId, setSelectedCustomerId] = useState<number | ''>('');
  const [paymentMethodCard, setPaymentMethodCard] = useState(true);
  const [paymentMethodAch, setPaymentMethodAch] = useState(false);

  const { data: customersData, isLoading: loadingCustomers } = useStripeCustomers({ page_size: 100 });
  const syncMutation = useSyncCustomer();
  const invoiceMutation = useCreateAndSendInvoice();

  const customers = customersData?.items ?? [];

  const handleSyncAndSelect = async () => {
    if (!contactId) return;
    try {
      const customer = await syncMutation.mutateAsync({ contact_id: contactId });
      setSelectedCustomerId(customer.id);
      showSuccess('Customer synced to Stripe');
    } catch {
      showError('Failed to sync customer to Stripe');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const customerId = selectedCustomerId;
    if (!customerId || !amount || !description) return;

    const paymentMethodTypes: string[] = [];
    if (paymentMethodCard) paymentMethodTypes.push('card');
    if (paymentMethodAch) paymentMethodTypes.push('us_bank_account');

    if (paymentMethodTypes.length === 0) {
      showError('Select at least one payment method');
      return;
    }

    try {
      const result = await invoiceMutation.mutateAsync({
        customer_id: customerId as number,
        amount: parseFloat(amount),
        description,
        due_days: dueDays,
        payment_method_types: paymentMethodTypes,
      });

      const recipientEmail = customers.find((c: StripeCustomer) => c.id === customerId)?.email ?? contactEmail ?? 'customer';
      // Stripe already emails the customer; copy the URL instead of
      // opening it (auto-open confused admins into thinking nothing
      // had been sent).
      if (result.invoice_url) {
        try {
          await navigator.clipboard.writeText(result.invoice_url);
          showSuccess(`Invoice emailed to ${recipientEmail} — link also copied to clipboard`);
        } catch {
          showSuccess(`Invoice emailed to ${recipientEmail}`);
        }
      } else {
        showSuccess(`Invoice emailed to ${recipientEmail}`);
      }

      setAmount('');
      setDescription('');
      setDueDays(30);
      setSelectedCustomerId('');
      setPaymentMethodCard(true);
      setPaymentMethodAch(false);
      onClose();
    } catch {
      showError('Failed to create and send invoice');
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Send Invoice" size="lg">
      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Customer Selector */}
        <div>
          <label htmlFor="invoice-customer" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Customer
          </label>
          <div className="mt-1 flex gap-2">
            <select
              id="invoice-customer"
              value={selectedCustomerId}
              onChange={(e) => setSelectedCustomerId(e.target.value ? Number(e.target.value) : '')}
              required
              className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm text-sm focus-visible:outline-none focus-visible:border-primary-500 focus-visible:ring-1 focus-visible:ring-primary-500"
            >
              <option value="">Select a Stripe customer...</option>
              {customers.map((c: StripeCustomer) => (
                <option key={c.id} value={c.id}>
                  {c.name ?? c.email ?? c.stripe_customer_id}
                </option>
              ))}
            </select>
            {contactId && (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={handleSyncAndSelect}
                isLoading={syncMutation.isPending}
                aria-label="Sync current contact to Stripe"
              >
                {loadingCustomers ? 'Loading...' : 'Sync Contact'}
              </Button>
            )}
          </div>
        </div>

        {/* Amount */}
        <div>
          <label htmlFor="invoice-amount" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Amount ($)
          </label>
          <input
            id="invoice-amount"
            type="number"
            name="amount"
            required
            min="0.01"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 shadow-sm text-sm focus-visible:outline-none focus-visible:border-primary-500 focus-visible:ring-1 focus-visible:ring-primary-500"
            placeholder="0.00"
            autoComplete="off"
            style={{ fontVariantNumeric: 'tabular-nums' }}
          />
        </div>

        {/* Description */}
        <div>
          <label htmlFor="invoice-description" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Description
          </label>
          <input
            id="invoice-description"
            type="text"
            name="description"
            required
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 shadow-sm text-sm focus-visible:outline-none focus-visible:border-primary-500 focus-visible:ring-1 focus-visible:ring-primary-500"
            placeholder="Invoice for services rendered..."
            autoComplete="off"
          />
        </div>

        {/* Due Days */}
        <div>
          <label htmlFor="invoice-due-days" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Due in
          </label>
          <select
            id="invoice-due-days"
            value={dueDays}
            onChange={(e) => setDueDays(Number(e.target.value))}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm text-sm focus-visible:outline-none focus-visible:border-primary-500 focus-visible:ring-1 focus-visible:ring-primary-500"
          >
            {DUE_DAY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Payment Methods */}
        <fieldset>
          <legend className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Payment Methods
          </legend>
          <div className="mt-2 space-y-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={paymentMethodCard}
                onChange={(e) => setPaymentMethodCard(e.target.checked)}
                className="rounded border-gray-300 dark:border-gray-600 text-primary-600 focus-visible:ring-primary-500"
              />
              <span className="text-sm text-gray-700 dark:text-gray-300">Card</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={paymentMethodAch}
                onChange={(e) => setPaymentMethodAch(e.target.checked)}
                className="rounded border-gray-300 dark:border-gray-600 text-primary-600 focus-visible:ring-primary-500"
              />
              <span className="text-sm text-gray-700 dark:text-gray-300">ACH Bank Transfer</span>
            </label>
          </div>
        </fieldset>

        <ModalFooter>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            isLoading={invoiceMutation.isPending}
            disabled={!selectedCustomerId || !amount || !description}
          >
            Send Invoice
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}
