/**
 * AI Recommendations section for the Dashboard page.
 * Shows top prioritized action recommendations.
 */

import { Link } from 'react-router-dom';
import { SparklesIcon, ArrowRightIcon } from '@heroicons/react/24/outline';
import { Spinner } from '../ui/Spinner';
import { RecommendationCard } from '../../features/ai-assistant/components/RecommendationCard';
import { AIFeedbackButtons } from './AIFeedbackButtons';
import { useRecommendations } from '../../hooks/useAI';

interface DashboardRecommendationsProps {
  maxItems?: number;
}

export function DashboardRecommendations({ maxItems = 3 }: DashboardRecommendationsProps) {
  const { data, isLoading, error } = useRecommendations();
  const recommendations = data?.recommendations ?? [];

  // Don't render anything on error (non-intrusive)
  if (error) return null;

  // Don't render if loading is done and there's nothing to show
  if (!isLoading && recommendations.length === 0) return null;

  return (
    <div className="bg-white rounded-lg shadow-sm border overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b bg-gradient-to-r from-purple-50 to-indigo-50">
        <div className="flex items-center gap-2">
          <SparklesIcon className="h-5 w-5 text-purple-600" />
          <h3 className="text-sm sm:text-base font-semibold text-gray-900">
            AI Suggestions
          </h3>
        </div>
        <Link
          to="/ai-assistant"
          className="flex items-center gap-1 text-xs sm:text-sm text-purple-600 hover:text-purple-800 font-medium transition-colors"
        >
          View all
          <ArrowRightIcon className="h-3.5 w-3.5" />
        </Link>
      </div>

      {/* Content */}
      <div className="p-4 sm:p-6">
        {isLoading ? (
          <div className="flex items-center justify-center py-6">
            <Spinner size="md" />
          </div>
        ) : (
          <div className="space-y-3">
            {recommendations.slice(0, maxItems).map((rec, index) => (
              <RecommendationCard
                key={index}
                recommendation={rec}
                feedbackSlot={
                  <AIFeedbackButtons
                    query={`Recommendation: ${rec.title}`}
                    response={rec.description}
                    size="sm"
                  />
                }
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
