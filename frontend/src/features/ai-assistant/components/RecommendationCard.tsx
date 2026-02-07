/**
 * AI recommendation card
 */

import { Link } from 'react-router-dom';
import clsx from 'clsx';
import {
  LightBulbIcon,
  PhoneIcon,
  EnvelopeIcon,
  CalendarIcon,
  ExclamationTriangleIcon,
  ArrowTrendingUpIcon,
  UserGroupIcon,
  CurrencyDollarIcon,
  ArrowRightIcon,
} from '@heroicons/react/24/outline';
import type { Recommendation } from '../../../types';

interface RecommendationCardProps {
  recommendation: Recommendation;
  onAction?: (recommendation: Recommendation) => void;
  feedbackSlot?: React.ReactNode;
}

const defaultPriorityColor = { bg: 'bg-blue-50', text: 'text-blue-600', border: 'border-blue-200' };

const priorityColors: Record<string, { bg: string; text: string; border: string }> = {
  low: { bg: 'bg-gray-50', text: 'text-gray-600', border: 'border-gray-200' },
  medium: defaultPriorityColor,
  high: { bg: 'bg-orange-50', text: 'text-orange-600', border: 'border-orange-200' },
};

const typeIcons: Record<string, React.ComponentType<{ className?: string }>> = {
  follow_up: PhoneIcon,
  email: EnvelopeIcon,
  meeting: CalendarIcon,
  overdue_task: ExclamationTriangleIcon,
  hot_lead: ArrowTrendingUpIcon,
  at_risk: ExclamationTriangleIcon,
  engagement: UserGroupIcon,
  revenue: CurrencyDollarIcon,
  insight: LightBulbIcon,
};

function getEntityLink(recommendation: Recommendation): string | null {
  if (!recommendation.entity_type || !recommendation.entity_id) return null;

  const entityRoutes: Record<string, string> = {
    lead: '/leads',
    contact: '/contacts',
    opportunity: '/opportunities',
    company: '/companies',
    activity: '/activities',
  };

  const baseRoute = entityRoutes[recommendation.entity_type];
  if (!baseRoute) return null;

  return `${baseRoute}/${recommendation.entity_id}`;
}

export function RecommendationCard({ recommendation, onAction, feedbackSlot }: RecommendationCardProps) {
  const priorityStyle = priorityColors[recommendation.priority] ?? defaultPriorityColor;
  const Icon = typeIcons[recommendation.type] || LightBulbIcon;
  const entityLink = getEntityLink(recommendation);

  const handleClick = () => {
    if (onAction) {
      onAction(recommendation);
    }
  };

  const cardContent = (
    <div
      className={clsx(
        'rounded-lg border p-4 transition-all hover:shadow-md cursor-pointer',
        priorityStyle.border,
        priorityStyle.bg
      )}
      onClick={handleClick}
    >
      <div className="flex items-start gap-3">
        <div className={clsx('p-2 rounded-lg', `bg-white/50`)}>
          <Icon className={clsx('h-5 w-5', priorityStyle.text)} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h4 className="text-sm font-medium text-gray-900 truncate">
              {recommendation.title}
            </h4>
            <span
              className={clsx(
                'text-xs font-medium px-2 py-0.5 rounded-full capitalize',
                recommendation.priority === 'high' && 'bg-orange-100 text-orange-700',
                recommendation.priority === 'medium' && 'bg-blue-100 text-blue-700',
                recommendation.priority === 'low' && 'bg-gray-100 text-gray-700'
              )}
            >
              {recommendation.priority}
            </span>
          </div>
          <p className="text-sm text-gray-600 mt-1 line-clamp-2">{recommendation.description}</p>

          {/* Additional Info */}
          <div className="flex items-center justify-between mt-3">
            <div className="flex items-center gap-3 text-xs text-gray-500">
              {recommendation.amount && (
                <span className="flex items-center gap-1">
                  <CurrencyDollarIcon className="h-3.5 w-3.5" />
                  {new Intl.NumberFormat('en-US', {
                    style: 'currency',
                    currency: 'USD',
                    minimumFractionDigits: 0,
                  }).format(recommendation.amount)}
                </span>
              )}
              {recommendation.score && (
                <span>Score: {recommendation.score}</span>
              )}
              {feedbackSlot}
            </div>
            <span
              className={clsx(
                'flex items-center gap-1 text-xs font-medium',
                priorityStyle.text
              )}
            >
              {recommendation.action}
              <ArrowRightIcon className="h-3 w-3" />
            </span>
          </div>
        </div>
      </div>
    </div>
  );

  if (entityLink) {
    return (
      <Link to={entityLink} className="block">
        {cardContent}
      </Link>
    );
  }

  return cardContent;
}

export default RecommendationCard;
