import { LightBulbIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import { Spinner } from '../ui';
import { useNextBestAction } from '../../hooks/useAI';

interface NextBestActionCardProps {
  entityType: 'lead' | 'opportunity' | 'contact';
  entityId: number;
  className?: string;
}

/**
 * A subtle suggestion card that displays the AI-recommended next action
 * for a given entity (lead, opportunity, or contact).
 */
export function NextBestActionCard({
  entityType,
  entityId,
  className = '',
}: NextBestActionCardProps) {
  const { data, isLoading, error, refetch } = useNextBestAction(entityType, entityId);

  // Don't render anything if there's an error (silent fail for non-intrusive UX)
  if (error) {
    return null;
  }

  if (isLoading) {
    return (
      <div className={`bg-blue-50 rounded-lg p-4 border border-blue-100 ${className}`}>
        <div className="flex items-center gap-3">
          <Spinner size="sm" />
          <span className="text-sm text-blue-600">Loading suggestion...</span>
        </div>
      </div>
    );
  }

  if (!data?.action) {
    return null;
  }

  // Map activity types to friendly icons/colors
  const getActivityIcon = (activityType?: string | null) => {
    switch (activityType) {
      case 'call':
        return (
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
          </svg>
        );
      case 'email':
        return (
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
          </svg>
        );
      case 'meeting':
        return (
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
          </svg>
        );
      case 'task':
        return (
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
          </svg>
        );
      default:
        return <LightBulbIcon className="h-5 w-5" />;
    }
  };

  return (
    <div className={`bg-gradient-to-r from-blue-50 to-cyan-50 rounded-lg p-4 border border-blue-100 ${className}`}>
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 p-2 bg-blue-100 rounded-lg text-blue-600">
          {getActivityIcon(data.activity_type)}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h4 className="text-sm font-medium text-blue-900">
              Suggested Next Action
            </h4>
            <button
              onClick={() => refetch()}
              className="p-1 text-blue-400 hover:text-blue-600 rounded"
              title="Refresh suggestion"
            >
              <ArrowPathIcon className="h-3.5 w-3.5" />
            </button>
          </div>
          <p className="text-sm font-medium text-gray-900 mb-1">
            {data.action}
          </p>
          {data.reason && (
            <p className="text-xs text-gray-600">
              {data.reason}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
