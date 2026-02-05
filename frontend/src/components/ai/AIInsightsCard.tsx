import { useState } from 'react';
import { SparklesIcon, ArrowPathIcon } from '@heroicons/react/24/outline';
import { Button, Spinner, Modal } from '../ui';
import { useLeadInsights, useOpportunityInsights } from '../../hooks/useAI';

interface AIInsightsCardProps {
  entityType: 'lead' | 'opportunity';
  entityId: number;
  entityName?: string;
  variant?: 'button' | 'inline';
}

/**
 * A component that displays AI-powered insights for leads or opportunities.
 * Can be rendered as a button that opens a modal, or inline within a page.
 */
export function AIInsightsCard({
  entityType,
  entityId,
  entityName,
  variant = 'button',
}: AIInsightsCardProps) {
  const [showModal, setShowModal] = useState(false);
  const [fetchEnabled, setFetchEnabled] = useState(variant === 'inline');

  // Use the appropriate hook based on entity type
  const leadInsights = useLeadInsights(
    entityType === 'lead' && fetchEnabled ? entityId : undefined
  );
  const opportunityInsights = useOpportunityInsights(
    entityType === 'opportunity' && fetchEnabled ? entityId : undefined
  );

  const insights = entityType === 'lead' ? leadInsights : opportunityInsights;
  const { data, isLoading, error, refetch } = insights;

  const handleOpenModal = () => {
    setFetchEnabled(true);
    setShowModal(true);
  };

  const handleCloseModal = () => {
    setShowModal(false);
  };

  const handleRefresh = () => {
    refetch();
  };

  // Check if OpenAI is not configured (common error message)
  const isOpenAINotConfigured =
    error instanceof Error &&
    (error.message.toLowerCase().includes('openai') ||
      error.message.toLowerCase().includes('api key') ||
      error.message.toLowerCase().includes('not configured'));

  const renderInsightsContent = () => {
    if (isLoading) {
      return (
        <div className="flex flex-col items-center justify-center py-8">
          <Spinner size="lg" />
          <p className="mt-4 text-sm text-gray-500">
            Analyzing {entityType} data...
          </p>
        </div>
      );
    }

    if (error) {
      if (isOpenAINotConfigured) {
        return (
          <div className="rounded-lg bg-yellow-50 p-4">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg
                  className="h-5 w-5 text-yellow-400"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                    clipRule="evenodd"
                  />
                </svg>
              </div>
              <div className="ml-3">
                <h3 className="text-sm font-medium text-yellow-800">
                  AI Not Configured
                </h3>
                <p className="mt-2 text-sm text-yellow-700">
                  AI insights require OpenAI API configuration. Please contact your
                  administrator to enable this feature.
                </p>
              </div>
            </div>
          </div>
        );
      }

      return (
        <div className="rounded-lg bg-red-50 p-4">
          <div className="flex">
            <div className="flex-shrink-0">
              <svg
                className="h-5 w-5 text-red-400"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                  clipRule="evenodd"
                />
              </svg>
            </div>
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800">
                Failed to load insights
              </h3>
              <p className="mt-2 text-sm text-red-700">
                {error instanceof Error ? error.message : 'An error occurred'}
              </p>
              <Button
                variant="secondary"
                size="sm"
                className="mt-3"
                onClick={handleRefresh}
              >
                Try Again
              </Button>
            </div>
          </div>
        </div>
      );
    }

    if (data?.insights) {
      return (
        <div className="space-y-4">
          <div className="prose prose-sm max-w-none">
            <div className="whitespace-pre-wrap text-gray-700">
              {data.insights}
            </div>
          </div>
        </div>
      );
    }

    return (
      <div className="text-center py-8 text-gray-500">
        <SparklesIcon className="mx-auto h-12 w-12 text-gray-400" />
        <p className="mt-2">No insights available</p>
      </div>
    );
  };

  if (variant === 'inline') {
    return (
      <div className="bg-gradient-to-r from-purple-50 to-indigo-50 rounded-lg p-4 sm:p-6 border border-purple-100">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <SparklesIcon className="h-5 w-5 text-purple-600" />
            <h3 className="text-lg font-medium text-gray-900">AI Insights</h3>
          </div>
          {data && !isLoading && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleRefresh}
              leftIcon={<ArrowPathIcon className="h-4 w-4" />}
            >
              Refresh
            </Button>
          )}
        </div>
        {renderInsightsContent()}
      </div>
    );
  }

  return (
    <>
      <Button
        variant="secondary"
        onClick={handleOpenModal}
        leftIcon={<SparklesIcon className="h-5 w-5 text-purple-600" />}
        className="border-purple-200 hover:border-purple-300 hover:bg-purple-50"
      >
        <span className="hidden sm:inline">AI Insights</span>
        <span className="sm:hidden">AI</span>
      </Button>

      <Modal
        isOpen={showModal}
        onClose={handleCloseModal}
        title={`AI Insights${entityName ? `: ${entityName}` : ''}`}
        size="lg"
        fullScreenOnMobile
      >
        <div className="min-h-[200px]">
          <div className="flex items-center justify-between mb-4 pb-4 border-b border-gray-200">
            <div className="flex items-center gap-2 text-purple-600">
              <SparklesIcon className="h-5 w-5" />
              <span className="text-sm font-medium">
                Powered by AI
              </span>
            </div>
            {data && !isLoading && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleRefresh}
                leftIcon={<ArrowPathIcon className="h-4 w-4" />}
              >
                Refresh
              </Button>
            )}
          </div>
          {renderInsightsContent()}
        </div>
      </Modal>
    </>
  );
}
