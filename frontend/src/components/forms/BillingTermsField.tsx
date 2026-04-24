import { useId } from 'react';

/**
 * Compound field shared by ProposalForm + QuoteForm.
 *
 * Lets the CRM user pick between a one-time charge and a recurring
 * subscription, and — when recurring — the billing cadence
 * (monthly, quarterly, bi-yearly, yearly). The cadence values are
 * serialized into Stripe-native shape: recurring_interval ('month'|'year')
 * plus recurring_interval_count (1 for monthly/yearly, 3 for quarterly,
 * 6 for bi-yearly).
 *
 * Rendering this component is cheap; the parent owns all state so the
 * form's submit handler can pull values directly without hoisting them
 * through callbacks.
 */

export type PaymentType = 'one_time' | 'subscription';
export type RecurringInterval = 'month' | 'year';

export interface BillingTermsValue {
  payment_type: PaymentType;
  recurring_interval: RecurringInterval | null;
  recurring_interval_count: number | null;
  amount: string;
  currency: string;
}

interface CadencePreset {
  key: string;
  label: string;
  interval: RecurringInterval;
  interval_count: number;
}

const CADENCE_PRESETS: CadencePreset[] = [
  { key: 'monthly', label: 'Monthly', interval: 'month', interval_count: 1 },
  { key: 'quarterly', label: 'Quarterly (every 3 months)', interval: 'month', interval_count: 3 },
  { key: 'bi_yearly', label: 'Bi-yearly (every 6 months)', interval: 'month', interval_count: 6 },
  { key: 'yearly', label: 'Yearly', interval: 'year', interval_count: 1 },
];

function cadenceKey(value: BillingTermsValue): string {
  const match = CADENCE_PRESETS.find(
    (p) =>
      p.interval === value.recurring_interval &&
      p.interval_count === value.recurring_interval_count,
  );
  return match?.key ?? 'monthly';
}

interface BillingTermsFieldProps {
  value: BillingTermsValue;
  onChange: (next: BillingTermsValue) => void;
  disabled?: boolean;
  /** Helper text rendered under the amount input. */
  amountHelpText?: string;
  /** When 'hidden' (the QuoteForm case), the amount input disappears —
   *  line items drive the quote total instead. Default: 'required'. */
  amountMode?: 'required' | 'hidden';
}

function BillingTermsField({
  value,
  onChange,
  disabled = false,
  amountHelpText,
  amountMode = 'required',
}: BillingTermsFieldProps) {
  const groupId = useId();

  const handleTypeChange = (nextType: PaymentType) => {
    if (nextType === 'one_time') {
      onChange({
        ...value,
        payment_type: 'one_time',
        recurring_interval: null,
        recurring_interval_count: null,
      });
    } else {
      // Default to monthly when flipping into subscription mode.
      onChange({
        ...value,
        payment_type: 'subscription',
        recurring_interval: 'month',
        recurring_interval_count: 1,
      });
    }
  };

  const handleCadenceChange = (key: string) => {
    const preset = CADENCE_PRESETS.find((p) => p.key === key);
    if (!preset) return;
    onChange({
      ...value,
      recurring_interval: preset.interval,
      recurring_interval_count: preset.interval_count,
    });
  };

  const oneTimeId = `${groupId}-one-time`;
  const subId = `${groupId}-subscription`;
  const cadenceId = `${groupId}-cadence`;
  const amountId = `${groupId}-amount`;
  const currencyId = `${groupId}-currency`;

  return (
    <div className="space-y-4">
      <fieldset>
        <legend className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
          Billing type
        </legend>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          <label
            htmlFor={oneTimeId}
            className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
              value.payment_type === 'one_time'
                ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20'
                : 'border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700/50'
            } ${disabled ? 'opacity-60 cursor-not-allowed' : ''}`}
          >
            <input
              id={oneTimeId}
              type="radio"
              name={`${groupId}-payment-type`}
              value="one_time"
              checked={value.payment_type === 'one_time'}
              onChange={() => handleTypeChange('one_time')}
              disabled={disabled}
              className="mt-0.5"
            />
            <span className="flex-1">
              <span className="block text-sm font-medium text-gray-900 dark:text-gray-100">
                One-time charge
              </span>
              <span className="block text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                Single invoice sent on acceptance.
              </span>
            </span>
          </label>

          <label
            htmlFor={subId}
            className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
              value.payment_type === 'subscription'
                ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-900/20'
                : 'border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700/50'
            } ${disabled ? 'opacity-60 cursor-not-allowed' : ''}`}
          >
            <input
              id={subId}
              type="radio"
              name={`${groupId}-payment-type`}
              value="subscription"
              checked={value.payment_type === 'subscription'}
              onChange={() => handleTypeChange('subscription')}
              disabled={disabled}
              className="mt-0.5"
            />
            <span className="flex-1">
              <span className="block text-sm font-medium text-gray-900 dark:text-gray-100">
                Subscription
              </span>
              <span className="block text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                Recurring charge on a cadence.
              </span>
            </span>
          </label>
        </div>
      </fieldset>

      {value.payment_type === 'subscription' && (
        <div>
          <label
            htmlFor={cadenceId}
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            Cadence
          </label>
          <select
            id={cadenceId}
            value={cadenceKey(value)}
            onChange={(e) => handleCadenceChange(e.target.value)}
            disabled={disabled}
            className="w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm px-3 py-2 shadow-sm"
          >
            {CADENCE_PRESETS.map((preset) => (
              <option key={preset.key} value={preset.key}>
                {preset.label}
              </option>
            ))}
          </select>
        </div>
      )}

      {amountMode === 'required' && (
        <div className="grid grid-cols-[1fr_auto] gap-3">
          <div>
            <label
              htmlFor={amountId}
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Amount
            </label>
            <input
              id={amountId}
              type="number"
              inputMode="decimal"
              min="0"
              step="0.01"
              value={value.amount}
              onChange={(e) => onChange({ ...value, amount: e.target.value })}
              disabled={disabled}
              placeholder="0.00"
              className="w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm px-3 py-2 shadow-sm"
            />
            {amountHelpText ? (
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{amountHelpText}</p>
            ) : null}
          </div>
          <div>
            <label
              htmlFor={currencyId}
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Currency
            </label>
            <select
              id={currencyId}
              value={value.currency}
              onChange={(e) => onChange({ ...value, currency: e.target.value.toUpperCase() })}
              disabled={disabled}
              className="rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-900 text-sm px-3 py-2 shadow-sm"
            >
              <option value="USD">USD</option>
              <option value="EUR">EUR</option>
              <option value="GBP">GBP</option>
              <option value="CAD">CAD</option>
            </select>
          </div>
        </div>
      )}
    </div>
  );
}

export default BillingTermsField;
