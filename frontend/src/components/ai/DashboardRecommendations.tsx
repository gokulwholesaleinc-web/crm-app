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

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border dark:border-gray-700 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 sm:px-6 py-4 border-b dark:border-gray-700 bg-gradient-to-r from-purple-50 to-indigo-50 dark:from-purple-900/20 dark:to-indigo-900/20">
        <div className="flex items-center gap-2">
          <SparklesIcon className="h-5 w-5 text-purple-600 dark:text-purple-400" />
          <h3 className="text-sm sm:text-base font-semibold text-gray-900 dark:text-gray-100">
            AI Suggestions
          </h3>
        </div>
        <Link
          to="/ai-assistant"
          className="flex items-center gap-1 text-xs sm:text-sm text-purple-600 dark:text-purple-400 hover:text-purple-800 dark:hover:text-purple-300 font-medium transition-colors"
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
        ) : recommendations.length === 0 ? (
          <div className="text-center py-4">
            <SparklesIcon className="mx-auto h-8 w-8 text-gray-300 dark:text-gray-600 mb-2" />
            <p className="text-sm text-gray-500 dark:text-gray-400">No suggestions right now. All caught up!</p>
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
