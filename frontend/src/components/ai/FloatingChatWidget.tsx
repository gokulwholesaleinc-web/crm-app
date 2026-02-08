/**
 * Floating AI chat widget available on all pages.
 * Opens a mini chat interface at the bottom-right corner.
 */

import { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import clsx from 'clsx';
import {
  SparklesIcon,
  XMarkIcon,
  MinusIcon,
} from '@heroicons/react/24/outline';
import { ChatMessage } from '../../features/ai-assistant/components/ChatMessage';
import { ChatInput } from '../../features/ai-assistant/components/ChatInput';
import { AIFeedbackButtons } from './AIFeedbackButtons';
import { Spinner } from '../ui/Spinner';
import { useChat } from '../../hooks/useAI';

/** Derive page context from current route for AI pre-population */
function getPageContext(pathname: string): string | undefined {
  const parts = pathname.split('/').filter(Boolean);
  if (parts.length === 0) return 'Viewing the dashboard';
  if (parts[0] === 'leads' && parts[1]) return `Viewing lead #${parts[1]}`;
  if (parts[0] === 'leads') return 'Browsing leads list';
  if (parts[0] === 'contacts' && parts[1]) return `Viewing contact #${parts[1]}`;
  if (parts[0] === 'contacts') return 'Browsing contacts list';
  if (parts[0] === 'opportunities') return 'Viewing opportunities pipeline';
  if (parts[0] === 'companies' && parts[1]) return `Viewing company #${parts[1]}`;
  if (parts[0] === 'companies') return 'Browsing companies list';
  if (parts[0] === 'activities') return 'Viewing activities';
  if (parts[0] === 'campaigns' && parts[1]) return `Viewing campaign #${parts[1]}`;
  if (parts[0] === 'campaigns') return 'Browsing campaigns';
  return undefined;
}

export function FloatingChatWidget() {
  const [isOpen, setIsOpen] = useState(false);
  const [isMinimized, setIsMinimized] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const location = useLocation();

  const pageContext = getPageContext(location.pathname);

  const isAIAssistantPage = location.pathname === '/ai-assistant';

  const {
    messages,
    sendMessage,
    clearChat,
    confirmAction,
    isLoading,
    pendingConfirmation,
    sessionId,
  } = useChat(pageContext);

  // Scroll to bottom when messages change
  useEffect(() => {
    if (messagesEndRef.current && isOpen && !isMinimized) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen, isMinimized]);

  // Don't show floating widget on the AI Assistant page (it has its own full chat)
  if (isAIAssistantPage) {
    return null;
  }

  const handleSend = async (content: string) => {
    try {
      await sendMessage(content);
    } catch {
      // Error handled in hook
    }
  };

  const handleClose = () => {
    setIsOpen(false);
    setIsMinimized(false);
  };

  const handleToggle = () => {
    if (isOpen && isMinimized) {
      setIsMinimized(false);
    } else {
      setIsOpen(!isOpen);
      setIsMinimized(false);
    }
  };

  return (
    <>
      {/* Chat Panel */}
      {isOpen && (
        <div
          className={clsx(
            'fixed bottom-20 right-4 sm:right-6 z-50 bg-white rounded-xl shadow-2xl border border-gray-200 flex flex-col transition-all duration-200',
            isMinimized
              ? 'w-72 h-12'
              : 'w-[calc(100vw-2rem)] sm:w-96 h-[min(500px,calc(100vh-10rem))]'
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b bg-gradient-to-r from-purple-500 to-indigo-600 rounded-t-xl">
            <div className="flex items-center gap-2 text-white">
              <SparklesIcon className="h-5 w-5" />
              <span className="text-sm font-medium">AI Assistant</span>
            </div>
            <div className="flex items-center gap-1">
              <button
                onClick={() => setIsMinimized(!isMinimized)}
                className="p-1 text-white/80 hover:text-white rounded transition-colors"
              >
                <MinusIcon className="h-4 w-4" />
              </button>
              <button
                onClick={handleClose}
                className="p-1 text-white/80 hover:text-white rounded transition-colors"
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Messages */}
          {!isMinimized && (
            <>
              <div className="flex-1 overflow-y-auto p-3 space-y-3">
                {messages.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-center px-4">
                    <SparklesIcon className="h-8 w-8 text-purple-400 mb-2" />
                    <p className="text-sm text-gray-500">
                      Ask me anything about your CRM
                    </p>
                    {pageContext && (
                      <p className="text-xs text-gray-400 mt-1">
                        {pageContext}
                      </p>
                    )}
                  </div>
                ) : (
                  <>
                    {messages.map((msg, idx) => (
                      <div key={msg.id}>
                        <ChatMessage message={msg} showTimestamp={false} />
                        {msg.role === 'assistant' && (
                          <div className="flex items-center gap-2 mt-1 ml-11">
                            <AIFeedbackButtons
                              query={
                                // Find the preceding user message as the query
                                messages
                                  .slice(0, idx)
                                  .filter((m) => m.role === 'user')
                                  .pop()?.content ?? ''
                              }
                              response={msg.content}
                              sessionId={sessionId}
                              size="sm"
                            />
                          </div>
                        )}
                        {msg.confirmationRequired && pendingConfirmation && (
                          <div className="flex items-center gap-2 mt-2 ml-11">
                            <button
                              onClick={() => confirmAction(true)}
                              disabled={isLoading}
                              className="px-3 py-1 text-xs font-medium bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors"
                            >
                              Confirm
                            </button>
                            <button
                              onClick={() => confirmAction(false)}
                              disabled={isLoading}
                              className="px-3 py-1 text-xs font-medium bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors"
                            >
                              Cancel
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                    {isLoading && (
                      <div className="flex items-center gap-2 ml-1">
                        <div className="h-6 w-6 rounded-full bg-purple-100 flex items-center justify-center">
                          <SparklesIcon className="h-3.5 w-3.5 text-purple-600" />
                        </div>
                        <div className="bg-gray-100 rounded-xl px-3 py-2">
                          <Spinner size="sm" />
                        </div>
                      </div>
                    )}
                    <div ref={messagesEndRef} />
                  </>
                )}
              </div>

              {/* Input */}
              <div className="p-3 border-t">
                {messages.length > 0 && (
                  <div className="flex justify-end mb-2">
                    <button
                      onClick={clearChat}
                      className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
                    >
                      Clear chat
                    </button>
                  </div>
                )}
                <ChatInput
                  onSend={handleSend}
                  isLoading={isLoading}
                  placeholder="Ask AI..."
                />
              </div>
            </>
          )}
        </div>
      )}

      {/* Floating Button */}
      <button
        onClick={handleToggle}
        className={clsx(
          'fixed bottom-4 right-4 sm:right-6 z-50 p-3.5 rounded-full shadow-lg transition-all duration-200',
          'bg-gradient-to-r from-purple-500 to-indigo-600 text-white',
          'hover:shadow-xl hover:scale-105 active:scale-95',
          isOpen && 'ring-2 ring-purple-300'
        )}
        title="AI Assistant"
      >
        {isOpen ? (
          <XMarkIcon className="h-6 w-6" />
        ) : (
          <SparklesIcon className="h-6 w-6" />
        )}
      </button>
    </>
  );
}
