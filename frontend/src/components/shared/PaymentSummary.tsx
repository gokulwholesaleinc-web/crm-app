/**
 * Payment Summary card component for contacts.
 * Fetches and displays payment statistics from the API.
 */

import { useAuthQuery } from '../../hooks/useAuthQuery';
import { apiClient } from '../../api/client';
import { Spinner } from '../ui';
import { formatCurrency } from '../../utils/formatters';

interface PaymentSummaryData {
  total_paid: number;
  payment_count: number;
  late_payments: number;
  on_time_rate: number;
  last_payment_date: string | null;
}

interface PaymentSummaryProps {
  contactId: number;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function PaymentSummary({ contactId }: PaymentSummaryProps) {
  const { data, isLoading, error } = useAuthQuery({
    queryKey: ['contacts', contactId, 'payment-summary'],
    queryFn: async () => {
      const response = await apiClient.get<PaymentSummaryData>(
        `/api/contacts/${contactId}/payment-summary`,
      );
      return response.data;
    },
    enabled: !!contactId,
  });

  if (isLoading) {
    return (
      <div className="bg-white shadow rounded-lg p-6">
        <div className="flex items-center justify-center py-4">
          <Spinner />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white shadow rounded-lg p-6">
        <p className="text-sm text-red-500 text-center">
          Failed to load payment summary.
        </p>
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="bg-white shadow rounded-lg overflow-hidden">
      <div className="px-4 py-5 sm:px-6 border-b border-gray-200">
        <h3 className="text-base font-semibold text-gray-900">
          Payment Summary
        </h3>
      </div>
      <div className="px-4 py-5 sm:p-6">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
          <div>
            <dt className="text-sm font-medium text-gray-500">Total Paid</dt>
            <dd
              className="mt-1 text-lg font-semibold text-gray-900"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              {formatCurrency(data.total_paid)}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Payments</dt>
            <dd
              className="mt-1 text-lg font-semibold text-gray-900"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              {data.payment_count}
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">On-Time Rate</dt>
            <dd className="mt-1 text-lg font-semibold text-gray-900">
              <span
                className={
                  data.on_time_rate >= 90
                    ? 'text-green-600'
                    : data.on_time_rate >= 70
                      ? 'text-yellow-600'
                      : 'text-red-600'
                }
              >
                {data.on_time_rate}%
              </span>
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Late Payments</dt>
            <dd
              className="mt-1 text-lg font-semibold text-gray-900"
              style={{ fontVariantNumeric: 'tabular-nums' }}
            >
              <span className={data.late_payments > 0 ? 'text-red-600' : ''}>
                {data.late_payments}
              </span>
            </dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Last Payment</dt>
            <dd className="mt-1 text-lg font-semibold text-gray-900">
              {data.last_payment_date
                ? formatDate(data.last_payment_date)
                : 'N/A'}
            </dd>
          </div>
        </div>
      </div>
    </div>
  );
}

export default PaymentSummary;
