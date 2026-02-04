/**
 * AI hooks using TanStack Query
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useCallback } from 'react';
import { aiApi } from '../api/ai';
import type { ChatMessage, ChatRequest } from '../types';

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
}

/**
 * Hook for AI chat functionality
 */
export function useChat() {
  const [messages, setMessages] = useState<ChatMessageWithId[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);

  const chatMutation = useMutation({
    mutationFn: (data: ChatRequest) => aiApi.chat(data),
    onSuccess: (response) => {
      // Add assistant message
      setMessages((prev) => [
        ...prev,
        {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: response.response,
          timestamp: new Date().toISOString(),
        },
      ]);
      // Update session ID if provided
      if (response.session_id) {
        setSessionId(response.session_id);
      }
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

      // Send to API
      await chatMutation.mutateAsync({
        message: content,
        session_id: sessionId,
      });
    },
    [chatMutation, sessionId]
  );

  const clearChat = useCallback(() => {
    setMessages([]);
    setSessionId(null);
  }, []);

  return {
    messages,
    sendMessage,
    clearChat,
    isLoading: chatMutation.isPending,
    error: chatMutation.error,
    sessionId,
  };
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
