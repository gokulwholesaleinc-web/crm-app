import type { Dispatch, SetStateAction } from 'react';

const DUE_DAY_OPTIONS = [
  { value: 15, label: '15 days' },
  { value: 30, label: '30 days' },
  { value: 45, label: '45 days' },
  { value: 60, label: '60 days' },
];

export interface OneTimeInvoiceFormProps {
  dueDays: number;
  setDueDays: Dispatch<SetStateAction<number>>;
  paymentMethodCard: boolean;
  setPaymentMethodCard: Dispatch<SetStateAction<boolean>>;
  paymentMethodAch: boolean;
  setPaymentMethodAch: Dispatch<SetStateAction<boolean>>;
}

export function OneTimeInvoiceForm({
  dueDays,
  setDueDays,
  paymentMethodCard,
  setPaymentMethodCard,
  paymentMethodAch,
  setPaymentMethodAch,
}: OneTimeInvoiceFormProps) {
  return (
    <>
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
    </>
  );
}
