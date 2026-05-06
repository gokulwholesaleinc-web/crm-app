import type { Dispatch, SetStateAction } from 'react';
import { INTERVAL_PRESETS } from './subscriptionConstants';

export { INTERVAL_PRESETS } from './subscriptionConstants';

export interface SubscriptionFormProps {
  intervalPreset: number;
  setIntervalPreset: Dispatch<SetStateAction<number>>;
}

export function SubscriptionForm({ intervalPreset, setIntervalPreset }: SubscriptionFormProps) {
  return (
    <div>
      <label htmlFor="invoice-interval" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
        Billing schedule
      </label>
      <select
        id="invoice-interval"
        value={intervalPreset}
        onChange={(e) => setIntervalPreset(Number(e.target.value))}
        className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm text-sm focus-visible:outline-none focus-visible:border-primary-500 focus-visible:ring-1 focus-visible:ring-primary-500"
      >
        {INTERVAL_PRESETS.map((preset, idx) => (
          <option key={preset.label} value={idx}>
            {preset.label}
          </option>
        ))}
      </select>
      <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
        Stripe will email the customer a Checkout link. They enter their card or bank once; the
        first charge runs immediately and subsequent charges run automatically on the schedule
        you picked. Cancel anytime from the customer's record.
      </p>
    </div>
  );
}
