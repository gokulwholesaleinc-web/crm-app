/**
 * AI Assistant chat interface page
 */

import { useEffect, useRef, useState } from 'react';
import clsx from 'clsx';
import {
  SparklesIcon,
  ArrowPathIcon,
  TrashIcon,
  LightBulbIcon,
  ChartBarIcon,
  ClockIcon,
} from '@heroicons/react/24/outline';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import { ChatMessage } from './components/ChatMessage';
import { ChatInput } from './components/ChatInput';
import { RecommendationCard } from './components/RecommendationCard';
import {
  useChat,
  useRecommendations,
  useDailySummary,
  useRefreshAIData,
} from '../../hooks/useAI';

const suggestedPrompts = [
  'What are my top priorities today?',
  'Show me high-value opportunities closing this month',
  'Which leads should I follow up with?',
  'Give me a summary of recent activities',
  'What tasks are overdue?',
  'Find contacts in the technology industry',
];

function QuickAction({
  icon: Icon,
  label,
  onClick,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 sm:gap-2 px-2 sm:px-3 py-1.5 sm:py-2 rounded-lg border border-gray-200 hover:bg-gray-50 hover:border-gray-300 transition-colors text-xs sm:text-sm text-gray-700 whitespace-nowrap flex-shrink-0"
    >
      <Icon className="h-3.5 w-3.5 sm:h-4 sm:w-4 text-gray-500" />
      {label}
    </button>
  );
}

export function AIAssistantPage() {
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [activeTab, setActiveTab] = useState<'chat' | 'recommendations' | 'summary'>('chat');

  // Chat state
  const { messages, sendMessage, clearChat, isLoading: isChatLoading } = useChat();

  // Recommendations and summary
  const { data: recommendationsData, isLoading: isLoadingRecs } = useRecommendations();
  const { data: summaryData, isLoading: isLoadingSummary } = useDailySummary();
  const refreshAIData = useRefreshAIData();

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const handleSendMessage = async (content: string) => {
    try {
      await sendMessage(content);
    } catch (error) {
      console.error('Failed to send message:', error);
    }
  };

  const handleSuggestedPrompt = (prompt: string) => {
    handleSendMessage(prompt);
  };

  const recommendations = recommendationsData?.recommendations || [];

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 border-b">
        <div className="flex items-center gap-2 sm:gap-3">
          <div className="p-1.5 sm:p-2 bg-purple-100 rounded-lg">
            <SparklesIcon className="h-5 w-5 sm:h-6 sm:w-6 text-purple-600" />
          </div>
          <div>
            <h1 className="text-lg sm:text-xl font-bold text-gray-900">AI Assistant</h1>
            <p className="text-xs sm:text-sm text-gray-500 hidden sm:block">
              Your intelligent CRM companion
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<ArrowPathIcon className="h-4 w-4" />}
            onClick={refreshAIData}
          >
            <span className="hidden sm:inline">Refresh</span>
          </Button>
        </div>
      </div>

      {/* Tabs - scrollable on mobile */}
      <div className="flex items-center gap-2 sm:gap-4 py-3 border-b overflow-x-auto scrollbar-hide -mx-4 px-4 sm:mx-0 sm:px-0">
        <button
          onClick={() => setActiveTab('chat')}
          className={clsx(
            'flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-colors whitespace-nowrap flex-shrink-0',
            activeTab === 'chat'
              ? 'bg-primary-100 text-primary-700'
              : 'text-gray-600 hover:bg-gray-100'
          )}
        >
          <SparklesIcon className="h-4 w-4" />
          Chat
        </button>
        <button
          onClick={() => setActiveTab('recommendations')}
          className={clsx(
            'flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-colors whitespace-nowrap flex-shrink-0',
            activeTab === 'recommendations'
              ? 'bg-primary-100 text-primary-700'
              : 'text-gray-600 hover:bg-gray-100'
          )}
        >
          <LightBulbIcon className="h-4 w-4" />
          <span className="hidden sm:inline">Recommendations</span>
          <span className="sm:hidden">Recs</span>
          {recommendations.length > 0 && (
            <span className="bg-primary-500 text-white text-xs px-1.5 py-0.5 rounded-full">
              {recommendations.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab('summary')}
          className={clsx(
            'flex items-center gap-1.5 sm:gap-2 px-2.5 sm:px-3 py-1.5 rounded-lg text-xs sm:text-sm font-medium transition-colors whitespace-nowrap flex-shrink-0',
            activeTab === 'summary'
              ? 'bg-primary-100 text-primary-700'
              : 'text-gray-600 hover:bg-gray-100'
          )}
        >
          <ChartBarIcon className="h-4 w-4" />
          <span className="hidden sm:inline">Daily Summary</span>
          <span className="sm:hidden">Summary</span>
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'chat' && (
          <div className="h-full flex flex-col">
            {/* Messages Area - full width on mobile */}
            <div className="flex-1 overflow-y-auto p-2 sm:p-4 space-y-3 sm:space-y-4">
              {messages.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-center px-4">
                  <div className="p-3 sm:p-4 bg-purple-50 rounded-full mb-3 sm:mb-4">
                    <SparklesIcon className="h-8 w-8 sm:h-10 sm:w-10 text-purple-500" />
                  </div>
                  <h2 className="text-base sm:text-lg font-semibold text-gray-900 mb-2">
                    How can I help you today?
                  </h2>
                  <p className="text-xs sm:text-sm text-gray-500 max-w-md mb-4 sm:mb-6">
                    I can help you find information, analyze data, and provide insights about your
                    CRM. Try asking me something!
                  </p>

                  {/* Suggested Prompts - single column on mobile */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-lg">
                    {suggestedPrompts.map((prompt, index) => (
                      <button
                        key={index}
                        onClick={() => handleSuggestedPrompt(prompt)}
                        className="text-left px-3 sm:px-4 py-2 sm:py-2.5 rounded-lg border border-gray-200 hover:bg-gray-50 hover:border-gray-300 transition-colors text-xs sm:text-sm text-gray-700"
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                <>
                  {/* Message bubbles - appropriate width on mobile */}
                  {messages.map((message) => (
                    <div key={message.id || `${message.role}-${message.content.slice(0, 20)}`} className="max-w-full sm:max-w-[85%]">
                      <ChatMessage message={message} />
                    </div>
                  ))}
                  {isChatLoading && (
                    <div className="flex items-center gap-2 sm:gap-3">
                      <div className="h-7 w-7 sm:h-8 sm:w-8 rounded-full bg-purple-100 flex items-center justify-center flex-shrink-0">
                        <SparklesIcon className="h-4 w-4 sm:h-5 sm:w-5 text-purple-600" />
                      </div>
                      <div className="bg-gray-100 rounded-2xl rounded-bl-sm px-3 sm:px-4 py-2 sm:py-3">
                        <div className="flex items-center gap-2">
                          <Spinner size="sm" />
                          <span className="text-xs sm:text-sm text-gray-500">Thinking...</span>
                        </div>
                      </div>
                    </div>
                  )}
                  <div ref={messagesEndRef} />
                </>
              )}
            </div>

            {/* Input Area - fixed at bottom on mobile */}
            <div className="p-2 sm:p-4 border-t bg-white sticky bottom-0 left-0 right-0">
              {messages.length > 0 && (
                <div className="flex items-center justify-between mb-2 sm:mb-3">
                  <div className="flex items-center gap-1.5 sm:gap-2 overflow-x-auto scrollbar-hide">
                    <QuickAction
                      icon={ClockIcon}
                      label="My tasks"
                      onClick={() => handleSendMessage('What are my pending tasks?')}
                    />
                    <QuickAction
                      icon={LightBulbIcon}
                      label="Suggestions"
                      onClick={() => handleSendMessage('Give me actionable suggestions')}
                    />
                  </div>
                  <button
                    onClick={clearChat}
                    className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 transition-colors flex-shrink-0 ml-2"
                  >
                    <TrashIcon className="h-3.5 w-3.5" />
                    <span className="hidden sm:inline">Clear chat</span>
                  </button>
                </div>
              )}
              <ChatInput
                onSend={handleSendMessage}
                isLoading={isChatLoading}
                placeholder="Ask me anything about your CRM..."
              />
            </div>
          </div>
        )}

        {activeTab === 'recommendations' && (
          <div className="h-full overflow-y-auto p-4">
            {isLoadingRecs ? (
              <div className="flex items-center justify-center py-12">
                <Spinner size="lg" />
              </div>
            ) : recommendations.length === 0 ? (
              <div className="text-center py-12">
                <LightBulbIcon className="mx-auto h-12 w-12 text-gray-400" />
                <h3 className="mt-2 text-sm font-medium text-gray-900">No recommendations</h3>
                <p className="mt-1 text-sm text-gray-500">
                  Check back later for AI-powered suggestions
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                <p className="text-sm text-gray-500 mb-4">
                  Prioritized actions based on your CRM data
                </p>
                {recommendations.map((rec, index) => (
                  <RecommendationCard key={index} recommendation={rec} />
                ))}
              </div>
            )}
          </div>
        )}

        {activeTab === 'summary' && (
          <div className="h-full overflow-y-auto p-4">
            {isLoadingSummary ? (
              <div className="flex items-center justify-center py-12">
                <Spinner size="lg" />
              </div>
            ) : !summaryData ? (
              <div className="text-center py-12">
                <ChartBarIcon className="mx-auto h-12 w-12 text-gray-400" />
                <h3 className="mt-2 text-sm font-medium text-gray-900">No summary available</h3>
                <p className="mt-1 text-sm text-gray-500">
                  The daily summary will appear here
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                <div className="bg-white rounded-lg shadow-sm border p-6">
                  <h3 className="text-lg font-semibold text-gray-900 mb-4">Today's Summary</h3>
                  <div className="prose prose-sm max-w-none text-gray-600">
                    <p className="whitespace-pre-wrap">{summaryData.summary}</p>
                  </div>
                </div>

                {summaryData.data && Object.keys(summaryData.data).length > 0 && (
                  <div className="bg-white rounded-lg shadow-sm border p-6">
                    <h3 className="text-lg font-semibold text-gray-900 mb-4">Key Metrics</h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 sm:gap-4">
                      {Object.entries(summaryData.data).map(([key, value]) => (
                        <div
                          key={key}
                          className="p-3 bg-gray-50 rounded-lg"
                        >
                          <p className="text-xs text-gray-500 capitalize">
                            {key.replace(/_/g, ' ')}
                          </p>
                          <p className="text-lg font-semibold text-gray-900">
                            {typeof value === 'number' ? value.toLocaleString() : String(value)}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default AIAssistantPage;
