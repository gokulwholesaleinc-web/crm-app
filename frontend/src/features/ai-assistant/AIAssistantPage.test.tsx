import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../../hooks/useAI', () => ({
  useChat: () => ({
    messages: [],
    sendMessage: vi.fn(),
    clearChat: vi.fn(),
    confirmAction: vi.fn(),
    isLoading: false,
    pendingConfirmation: null,
    sessionId: 'test-session',
  }),
  useRecommendations: () => ({ data: undefined, isLoading: false }),
  useDailySummary: () => ({ data: undefined, isLoading: false }),
  useRefreshAIData: () => vi.fn(),
  useAILearnings: () => ({ data: undefined, isLoading: false }),
  useDeleteAILearning: () => ({ mutate: vi.fn() }),
  useSmartSuggestions: () => ({ data: undefined, isLoading: false }),
}));

vi.mock('../../utils/toast', () => ({ showError: vi.fn() }));
vi.mock('../../components/ai/AIFeedbackButtons', () => ({ AIFeedbackButtons: () => null }));
vi.mock('./components/ChatMessage', () => ({
  ChatMessage: ({ message }: { message: { content: string } }) => (
    <div data-testid="chat-message">{message.content}</div>
  ),
}));
vi.mock('./components/ChatInput', () => ({
  ChatInput: ({ placeholder }: { placeholder?: string }) => (
    <input data-testid="chat-input" placeholder={placeholder} />
  ),
}));
vi.mock('./components/RecommendationCard', () => ({ RecommendationCard: () => null }));

import { AIAssistantPage } from './AIAssistantPage';

const AUTO_SCROLL_KEY = 'crm:ai-assistant:autoscroll:v1';

// Minimal localStorage stub compatible with the jsdom environment used by vitest
const lsStore: Record<string, string> = {};
const localStorageMock = {
  getItem: (k: string) => lsStore[k] ?? null,
  setItem: (k: string, v: string) => { lsStore[k] = v; },
  removeItem: (k: string) => { delete lsStore[k]; },
  clear: () => { Object.keys(lsStore).forEach((k) => delete lsStore[k]); },
};
vi.stubGlobal('localStorage', localStorageMock);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AIAssistantPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('AIAssistantPage', () => {
  beforeEach(() => {
    localStorageMock.clear();
  });

  it('renders streaming container with aria-live="polite" and aria-atomic="false"', () => {
    renderPage();
    const liveRegion = document.querySelector('[aria-live="polite"]');
    expect(liveRegion).not.toBeNull();
    expect(liveRegion?.getAttribute('aria-atomic')).toBe('false');
  });

  it('auto-scroll toggle is on by default with aria-pressed=true', () => {
    renderPage();
    const toggle = screen.getByRole('button', { name: /auto-scroll on/i });
    expect(toggle.getAttribute('aria-pressed')).toBe('true');
    expect(toggle.getAttribute('data-autoscroll')).toBe('true');
  });

  it('flips data-autoscroll to false when toggle is clicked', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /auto-scroll on/i }));
    const off = screen.getByRole('button', { name: /auto-scroll off/i });
    expect(off.getAttribute('data-autoscroll')).toBe('false');
    expect(off.getAttribute('aria-pressed')).toBe('false');
  });

  it('persists preference in localStorage under versioned key', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: /auto-scroll on/i }));
    expect(localStorageMock.getItem(AUTO_SCROLL_KEY)).toBe('false');
    fireEvent.click(screen.getByRole('button', { name: /auto-scroll off/i }));
    expect(localStorageMock.getItem(AUTO_SCROLL_KEY)).toBe('true');
  });

  it('reads initial auto-scroll state from localStorage', () => {
    localStorageMock.setItem(AUTO_SCROLL_KEY, 'false');
    renderPage();
    const toggle = screen.getByRole('button', { name: /auto-scroll off/i });
    expect(toggle.getAttribute('aria-pressed')).toBe('false');
  });
});
