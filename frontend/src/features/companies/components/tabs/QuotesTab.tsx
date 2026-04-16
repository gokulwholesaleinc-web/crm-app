import { Link } from 'react-router-dom';
import { formatCurrency, formatDate } from '../../../../utils/formatters';
import { StatusBadge } from '../../../../components/ui/Badge';
import type { StatusType } from '../../../../components/ui/Badge';
import type { Quote } from '../../../../types';

interface QuotesTabProps {
  companyId: number;
  quotes: Quote[];
}

export function QuotesTab({ companyId, quotes }: QuotesTabProps) {
  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700">
      {quotes.length === 0 ? (
        <div className="text-center py-12 px-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">No quotes for this company.</p>
          <Link
            to={`/quotes?company_id=${companyId}`}
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
              {quotes.map((quote) => (
                <tr key={quote.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <Link to={`/quotes/${quote.id}`} className="text-primary-600 hover:text-primary-900 dark:hover:text-primary-300">
                      {quote.title} ({quote.quote_number})
                    </Link>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap">
                    <StatusBadge status={quote.status as StatusType} size="sm" showDot={false} />
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
  );
}
