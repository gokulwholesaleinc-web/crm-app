import { useState } from 'react';
import { Modal, ModalFooter, Button } from '../../../components/ui';
import {
  useStripeCustomers,
  useSyncCustomer,
  useCreateAndSendInvoice,
  useCreateAndSendSubscription,
} from '../../../hooks/usePayments';
import { useStripeMode } from '../../../hooks/useStripeMode';
import { showSuccess, showError } from '../../../utils/toast';
import type { StripeCustomer } from '../../../types';
import type { PaymentType } from '../../../types/proposals';
import { OneTimeInvoiceForm } from './OneTimeInvoiceForm';
import { SubscriptionForm, INTERVAL_PRESETS } from './SubscriptionForm';

interface SendInvoiceModalProps {
  isOpen: boolean;
  onClose: () => void;
  contactId?: number;
  contactEmail?: string;
  defaultAmount?: number;
}

const PAYMENT_TYPE_OPTIONS: Array<{ value: PaymentType; title: string; subtitle: string }> = [
  { value: 'one_time', title: 'One-time', subtitle: 'Single invoice, paid once' },
  { value: 'subscription', title: 'Subscription', subtitle: 'Recurring on a schedule' },
];

interface RadioCardProps {
  name: string;
  value: string;
  checked: boolean;
  title: string;
  subtitle: string;
  onChange: () => void;
}

function RadioCard({ name, value, checked, title, subtitle, onChange }: RadioCardProps) {
  return (
    <label
      className={`flex items-start gap-2 cursor-pointer rounded-md border p-3 ${
        checked
          ? 'border-primary-500 ring-1 ring-primary-500 bg-primary-50 dark:bg-primary-900/20'
          : 'border-gray-300 dark:border-gray-600'
      }`}
    >
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={onChange}
        className="mt-0.5 text-primary-600 focus-visible:ring-primary-500"
      />
      <div>
        <span className="block text-sm font-medium text-gray-900 dark:text-gray-100">{title}</span>
        <span className="block text-xs text-gray-500 dark:text-gray-400">{subtitle}</span>
      </div>
    </label>
  );
}

export function SendInvoiceModal({
  isOpen,
  onClose,
  contactId,
  contactEmail,
  defaultAmount,
}: SendInvoiceModalProps) {
  const [paymentType, setPaymentType] = useState<PaymentType>('one_time');
  const [amount, setAmount] = useState(defaultAmount?.toString() ?? '');
  const [description, setDescription] = useState('');
  const [selectedCustomerId, setSelectedCustomerId] = useState<number | ''>('');
  // one_time-specific
  const [dueDays, setDueDays] = useState(30);
  const [paymentMethodCard, setPaymentMethodCard] = useState(true);
  const [paymentMethodAch, setPaymentMethodAch] = useState(false);
  // subscription-specific
  const [intervalPreset, setIntervalPreset] = useState<number>(0);

  const { data: customersData, isLoading: loadingCustomers } = useStripeCustomers({ page_size: 100 });
  const syncMutation = useSyncCustomer();
  const invoiceMutation = useCreateAndSendInvoice();
  const subscriptionMutation = useCreateAndSendSubscription();
  const { mode: stripeMode } = useStripeMode();

  const customers = customersData?.items ?? [];
  const isSubmitting = invoiceMutation.isPending || subscriptionMutation.isPending;
  const stripeDisabled = stripeMode === 'unconfigured';

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

  const resetForm = () => {
    setAmount('');
    setDescription('');
    setDueDays(30);
    setSelectedCustomerId('');
    setPaymentMethodCard(true);
    setPaymentMethodAch(false);
    setPaymentType('one_time');
    setIntervalPreset(0);
  };

  const copyToClipboardWithFeedback = async (url: string, recipientEmail: string, kind: 'Invoice' | 'Subscription link') => {
    if (!url) {
      showSuccess(`${kind} emailed to ${recipientEmail}`);
      return;
    }
    try {
      await navigator.clipboard.writeText(url);
      showSuccess(`${kind} emailed to ${recipientEmail} — link also copied to clipboard`);
    } catch {
      showSuccess(`${kind} emailed to ${recipientEmail}`);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const customerId = selectedCustomerId;
    if (!customerId || !amount || !description) return;

    const recipientEmail =
      customers.find((c: StripeCustomer) => c.id === customerId)?.email ?? contactEmail ?? 'customer';

    if (paymentType === 'one_time') {
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
        await copyToClipboardWithFeedback(result.invoice_url ?? '', recipientEmail, 'Invoice');
        resetForm();
        onClose();
      } catch {
        showError('Failed to create and send invoice');
      }
      return;
    }

    // Out-of-range intervalPreset shouldn't happen — the <select> only
    // emits valid indexes — but tsc with noUncheckedIndexedAccess sees
    // the array access as possibly-undefined, so default explicitly.
    const preset = INTERVAL_PRESETS[intervalPreset] ?? { interval: 'month' as const, count: 1 };
    try {
      const result = await subscriptionMutation.mutateAsync({
        customer_id: customerId as number,
        amount: parseFloat(amount),
        description,
        currency: 'USD',
        interval: preset.interval,
        interval_count: preset.count,
        success_url: `${window.location.origin}/payments?subscription=success`,
        cancel_url: `${window.location.origin}/payments?subscription=cancelled`,
      });
      await copyToClipboardWithFeedback(result.checkout_url, recipientEmail, 'Subscription link');
      resetForm();
      onClose();
    } catch {
      showError('Failed to create subscription checkout');
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Send Invoice" size="lg">
      <form onSubmit={handleSubmit} className="space-y-4">
        {stripeDisabled && (
          <div
            role="alert"
            aria-live="polite"
            className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-200"
          >
            <p className="font-medium">Stripe is not configured.</p>
            <p className="mt-1 text-xs">
              Invoices cannot be sent until an admin sets the
              {' '}<code className="font-mono">STRIPE_SECRET_KEY</code>{' '}
              environment variable.
            </p>
          </div>
        )}
        <fieldset>
          <legend className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Payment Type
          </legend>
          <div className="grid grid-cols-2 gap-2">
            {PAYMENT_TYPE_OPTIONS.map((opt) => (
              <RadioCard
                key={opt.value}
                name="payment-type"
                value={opt.value}
                checked={paymentType === opt.value}
                title={opt.title}
                subtitle={opt.subtitle}
                onChange={() => setPaymentType(opt.value)}
              />
            ))}
          </div>
        </fieldset>

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
                disabled={stripeDisabled}
                title={stripeDisabled ? 'Stripe is not configured' : undefined}
                aria-label="Sync current contact to Stripe"
              >
                {loadingCustomers ? 'Loading...' : 'Sync Contact'}
              </Button>
            )}
          </div>
        </div>

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

        {paymentType === 'one_time' ? (
          <OneTimeInvoiceForm
            dueDays={dueDays}
            setDueDays={setDueDays}
            paymentMethodCard={paymentMethodCard}
            setPaymentMethodCard={setPaymentMethodCard}
            paymentMethodAch={paymentMethodAch}
            setPaymentMethodAch={setPaymentMethodAch}
          />
        ) : (
          <SubscriptionForm
            intervalPreset={intervalPreset}
            setIntervalPreset={setIntervalPreset}
          />
        )}

        <ModalFooter>
          <Button type="button" variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="submit"
            isLoading={isSubmitting}
            disabled={!selectedCustomerId || !amount || !description || isSubmitting || stripeDisabled}
            title={stripeDisabled ? 'Stripe is not configured' : undefined}
          >
            {paymentType === 'one_time' ? 'Send Invoice' : 'Send Subscription Link'}
          </Button>
        </ModalFooter>
      </form>
    </Modal>
  );
}
