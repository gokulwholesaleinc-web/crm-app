/**
 * AI hooks using TanStack Query
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useCallback } from 'react';
import { aiApi } from '../api/ai';
import type { ChatMessage, ChatRequest, FeedbackRequest, ConfirmActionRequest, ChatResponse } from '../types';

// Query keys
export const aiKeys = {
  all: ['ai'] as const,
  recommendations: () => [...aiKeys.all, 'recommendations'] as const,
  dailySummary: () => [...aiKeys.all, 'daily-summary'] as const,
  leadInsights: (id: number) => [...aiKeys.all, 'insights', 'lead', id] as const,
  opportunityInsights: (id: number) => [...aiKeys.all, 'insights', 'opportunity', id] as const,
  nextAction: (entityType: string, entityId: number) =>
    [...aiKeys.all, 'next-action', entityType, entityId] as const,
  search: (query: string, entityTypes?: string) =>
    [...aiKeys.all, 'search', query, entityTypes] as const,
};

/**
 * Hook to get AI recommendations
 */
export function useRecommendations() {
  return useQuery({
    queryKey: aiKeys.recommendations(),
    queryFn: () => aiApi.getRecommendations(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Hook to get daily summary
 */
export function useDailySummary() {
  return useQuery({
    queryKey: aiKeys.dailySummary(),
    queryFn: () => aiApi.getDailySummary(),
    staleTime: 30 * 60 * 1000, // 30 minutes
  });
}

/**
 * Hook to get lead insights
 */
export function useLeadInsights(leadId: number | undefined) {
  return useQuery({
    queryKey: aiKeys.leadInsights(leadId!),
    queryFn: () => aiApi.getLeadInsights(leadId!),
    enabled: !!leadId,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });
}

/**
 * Hook to get opportunity insights
 */
export function useOpportunityInsights(opportunityId: number | undefined) {
  return useQuery({
    queryKey: aiKeys.opportunityInsights(opportunityId!),
    queryFn: () => aiApi.getOpportunityInsights(opportunityId!),
    enabled: !!opportunityId,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });
}

/**
 * Hook to get next best action for an entity
 */
export function useNextBestAction(entityType: string, entityId: number) {
  return useQuery({
    queryKey: aiKeys.nextAction(entityType, entityId),
    queryFn: () => aiApi.getNextBestAction(entityType, entityId),
    enabled: !!entityType && !!entityId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Hook for semantic search
 */
export function useSemanticSearch(query: string, entityTypes?: string, limit = 5) {
  return useQuery({
    queryKey: aiKeys.search(query, entityTypes),
    queryFn: () => aiApi.semanticSearch(query, entityTypes, limit),
    enabled: query.length >= 3,
    staleTime: 60 * 1000, // 1 minute
  });
}

/**
 * Custom message type with id for UI
 */
interface ChatMessageWithId extends ChatMessage {
  id: string;
  timestamp: string;
  confirmationRequired?: boolean;
  pendingAction?: Record<string, unknown> | null;
  actionsTaken?: Array<Record<string, unknown>>;
  query?: string;
}

/**
 * Hook for AI chat functionality with confirmation flow support
 */
export function useChat(initialContext?: string) {
  const [messages, setMessages] = useState<ChatMessageWithId[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [pendingConfirmation, setPendingConfirmation] = useState<{
    functionName: string;
    arguments: Record<string, unknown>;
  } | null>(null);

  const chatMutation = useMutation({
    mutationFn: (data: ChatRequest) => aiApi.chat(data),
    onSuccess: (response: ChatResponse) => {
      // Add assistant message
      setMessages((prev) => [
        ...prev,
        {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: response.response,
          timestamp: new Date().toISOString(),
          confirmationRequired: response.confirmation_required,
          pendingAction: response.pending_action,
          actionsTaken: response.actions_taken,
        },
      ]);
      // Update session ID if provided
      if (response.session_id) {
        setSessionId(response.session_id);
      }
      // Track pending confirmation
      if (response.confirmation_required && response.pending_action) {
        setPendingConfirmation({
          functionName: response.pending_action.function_name as string,
          arguments: response.pending_action.arguments as Record<string, unknown>,
        });
      }
    },
  });

  const confirmMutation = useMutation({
    mutationFn: (data: ConfirmActionRequest) => aiApi.confirmAction(data),
    onSuccess: (response) => {
      setMessages((prev) => [
        ...prev,
        {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: response.response,
          timestamp: new Date().toISOString(),
          actionsTaken: response.actions_taken,
        },
      ]);
      setPendingConfirmation(null);
    },
  });

  const sendMessage = useCallback(
    async (content: string) => {
      // Add user message immediately
      const userMessage: ChatMessageWithId = {
        id: `user-${Date.now()}`,
        role: 'user',
        content,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);

      // Prepend context if provided and this is the first message
      const messageToSend = initialContext && messages.length === 0
        ? `[Context: ${initialContext}] ${content}`
        : content;

      // Send to API
      await chatMutation.mutateAsync({
        message: messageToSend,
        session_id: sessionId,
      });
    },
    [chatMutation, sessionId, initialContext, messages.length]
  );

  const confirmAction = useCallback(
    async (confirmed: boolean) => {
      if (!pendingConfirmation || !sessionId) return;

      // Add user confirmation message
      setMessages((prev) => [
        ...prev,
        {
          id: `user-${Date.now()}`,
          role: 'user',
          content: confirmed ? 'Yes, proceed.' : 'No, cancel.',
          timestamp: new Date().toISOString(),
        },
      ]);

      await confirmMutation.mutateAsync({
        session_id: sessionId,
        function_name: pendingConfirmation.functionName,
        arguments: pendingConfirmation.arguments,
        confirmed,
      });
    },
    [confirmMutation, pendingConfirmation, sessionId]
  );

  const clearChat = useCallback(() => {
    setMessages([]);
    setSessionId(null);
    setPendingConfirmation(null);
  }, []);

  return {
    messages,
    sendMessage,
    clearChat,
    confirmAction,
    isLoading: chatMutation.isPending || confirmMutation.isPending,
    error: chatMutation.error || confirmMutation.error,
    sessionId,
    pendingConfirmation,
  };
}

/**
 * Hook for submitting AI feedback
 */
export function useFeedback() {
  return useMutation({
    mutationFn: (data: FeedbackRequest) => aiApi.submitFeedback(data),
  });
}

/**
 * Hook for refreshing AI data
 */
export function useRefreshAIData() {
  const queryClient = useQueryClient();

  return useCallback(() => {
    queryClient.invalidateQueries({ queryKey: aiKeys.recommendations() });
    queryClient.invalidateQueries({ queryKey: aiKeys.dailySummary() });
  }, [queryClient]);
}

/**
 * Convenience hook combining insights for easy use
 */
export function useInsights(entityType: 'lead' | 'opportunity', entityId: number | undefined) {
  const leadInsights = useLeadInsights(entityType === 'lead' ? entityId : undefined);
  const opportunityInsights = useOpportunityInsights(
    entityType === 'opportunity' ? entityId : undefined
  );

  if (entityType === 'lead') {
    return leadInsights;
  }
  return opportunityInsights;
}
