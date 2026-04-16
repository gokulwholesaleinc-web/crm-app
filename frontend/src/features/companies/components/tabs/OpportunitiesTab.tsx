import { Link } from 'react-router-dom';
import { formatCurrency, formatDate } from '../../../../utils/formatters';
import type { Opportunity } from '../../../../types';

interface OpportunitiesTabProps {
  companyId: number;
  opportunities: Opportunity[];
}

export function OpportunitiesTab({ companyId, opportunities }: OpportunitiesTabProps) {
  return (
    <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700">
      {opportunities.length === 0 ? (
        <div className="text-center py-12 px-4">
          <p className="text-sm text-gray-500 dark:text-gray-400">No opportunities for this company.</p>
          <Link
            to={`/opportunities?company_id=${companyId}`}
            className="mt-2 inline-block text-sm text-primary-600 hover:text-primary-900 dark:hover:text-primary-300"
          >
            View Opportunities
          </Link>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-900">
              <tr>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Name</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Stage</th>
                <th scope="col" className="px-6 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Amount</th>
                <th scope="col" className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Date</th>
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
              {opportunities.map((opp) => (
                <tr key={opp.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                  <td className="px-6 py-4 whitespace-nowrap text-sm">
                    <Link to={`/opportunities/${opp.id}`} className="text-primary-600 hover:text-primary-900 dark:hover:text-primary-300">
                      {opp.name}
                    </Link>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                    {opp.pipeline_stage?.name ?? '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-right font-medium text-gray-900 dark:text-gray-100" style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {opp.amount ? formatCurrency(opp.amount) : '-'}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                    {formatDate(opp.created_at)}
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
