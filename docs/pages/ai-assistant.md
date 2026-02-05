# AI Assistant Page

## Overview

| Property | Value |
|----------|-------|
| **Page Name** | AI Assistant |
| **File Path** | `/frontend/src/features/ai-assistant/AIAssistantPage.tsx` |
| **Route** | `/ai-assistant` (assumed based on feature structure) |
| **Description** | Intelligent CRM companion providing chat interface, recommendations, and daily summaries |

---

## UI Components

### External UI Components

| Component | Source | Usage |
|-----------|--------|-------|
| `Button` | `../../components/ui/Button` | Refresh button in header |
| `Spinner` | `../../components/ui/Spinner` | Loading indicators for chat and tabs |

### Feature-Specific Components

| Component | Source | Purpose |
|-----------|--------|---------|
| `ChatMessage` | `./components/ChatMessage` | Renders individual chat message bubbles |
| `ChatInput` | `./components/ChatInput` | Text input with send button for chat |
| `RecommendationCard` | `./components/RecommendationCard` | Displays AI-generated action recommendations |

### Internal Component: QuickAction

A local component defined within the page for rendering quick action buttons.

```typescript
function QuickAction({
  icon: Icon,
  label,
  onClick,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  onClick: () => void;
})
```

### Icons (Heroicons)

| Icon | Usage |
|------|-------|
| `SparklesIcon` | Page header, chat tab, AI avatar, empty state |
| `ArrowPathIcon` | Refresh button |
| `TrashIcon` | Clear chat button |
| `LightBulbIcon` | Recommendations tab, suggestion quick action, empty recommendations state |
| `ChartBarIcon` | Daily summary tab, empty summary state |
| `ClockIcon` | Tasks quick action |

---

## Functions and Handlers

### handleSendMessage

Sends a user message to the AI assistant.

```typescript
const handleSendMessage = async (content: string) => {
  try {
    await sendMessage(content);
  } catch (error) {
    console.error('Failed to send message:', error);
  }
};
```

- **Trigger**: ChatInput form submission, suggested prompt click, quick action click
- **Behavior**: Calls the `sendMessage` function from `useChat` hook

### handleSuggestedPrompt

Convenience wrapper for sending suggested prompts.

```typescript
const handleSuggestedPrompt = (prompt: string) => {
  handleSendMessage(prompt);
};
```

- **Trigger**: Click on suggested prompt buttons in empty chat state

### clearChat

Clears all chat messages and resets the session.

```typescript
clearChat(); // From useChat hook
```

- **Trigger**: Click on "Clear chat" button
- **Behavior**: Resets messages array and session ID to null

### refreshAIData

Refreshes recommendations and daily summary data.

```typescript
const refreshAIData = useRefreshAIData();
```

- **Trigger**: Click on "Refresh" button in header
- **Behavior**: Invalidates TanStack Query cache for recommendations and daily summary

### setActiveTab

State setter for switching between tabs.

```typescript
setActiveTab('chat' | 'recommendations' | 'summary')
```

- **Trigger**: Click on tab buttons
- **Behavior**: Switches visible content area

---

## Hooks Used

### React Hooks

| Hook | Purpose |
|------|---------|
| `useEffect` | Auto-scroll to bottom when new messages arrive |
| `useRef` | Reference to messages container end for scroll behavior |
| `useState` | Manage active tab state |

### Custom AI Hooks (from `../../hooks/useAI`)

| Hook | Purpose | Return Values |
|------|---------|---------------|
| `useChat` | Manages chat state and messaging | `{ messages, sendMessage, clearChat, isLoading }` |
| `useRecommendations` | Fetches AI recommendations | `{ data, isLoading }` |
| `useDailySummary` | Fetches daily summary | `{ data, isLoading }` |
| `useRefreshAIData` | Returns function to refresh AI data | `() => void` |

### Hook Implementation Details

#### useChat

```typescript
interface ChatMessageWithId extends ChatMessage {
  id: string;
  timestamp: string;
}

// Returns:
{
  messages: ChatMessageWithId[];
  sendMessage: (content: string) => Promise<void>;
  clearChat: () => void;
  isLoading: boolean;
  error: Error | null;
  sessionId: string | null;
}
```

- Uses TanStack Query's `useMutation` for API calls
- Maintains session ID for conversation continuity
- Adds user messages optimistically before API response

#### useRecommendations

- **Stale Time**: 5 minutes
- **Query Key**: `['ai', 'recommendations']`

#### useDailySummary

- **Stale Time**: 30 minutes
- **Query Key**: `['ai', 'daily-summary']`

---

## API Calls

### Endpoints Used

| Endpoint | Method | Purpose | Hook |
|----------|--------|---------|------|
| `POST /api/ai/chat` | POST | Send chat message | `useChat` |
| `GET /api/ai/recommendations` | GET | Fetch recommendations | `useRecommendations` |
| `GET /api/ai/summary/daily` | GET | Fetch daily summary | `useDailySummary` |

### Request/Response Types

#### Chat API

**Request (`ChatRequest`):**
```typescript
interface ChatRequest {
  message: string;
  session_id?: string | null;
}
```

**Response (`ChatResponse`):**
```typescript
interface ChatResponse {
  response: string;
  data?: Record<string, unknown> | null;
  function_called?: string | null;
  session_id?: string | null;
}
```

#### Recommendations API

**Response (`RecommendationsResponse`):**
```typescript
interface RecommendationsResponse {
  recommendations: Recommendation[];
}
```

#### Daily Summary API

**Response (`DailySummaryResponse`):**
```typescript
interface DailySummaryResponse {
  data: Record<string, unknown>;
  summary: string;
}
```

---

## Chat Interface Structure

### Layout

```
+--------------------------------------------------+
|  [Icon] AI Assistant                    [Refresh] |
|          Your intelligent CRM companion           |
+--------------------------------------------------+
|  [Chat] [Recommendations (badge)] [Daily Summary] |
+--------------------------------------------------+
|                                                   |
|              Chat Messages Area                   |
|              (scrollable)                         |
|                                                   |
|  - User messages (right-aligned, primary color)   |
|  - AI messages (left-aligned, gray background)    |
|  - Loading indicator (Spinner + "Thinking...")    |
|                                                   |
+--------------------------------------------------+
|  [My tasks] [Suggestions]         [Clear chat]    |
|  +--------------------------------------------+   |
|  |  Ask me anything about your CRM...    [>]  |   |
|  +--------------------------------------------+   |
+--------------------------------------------------+
```

### Empty State (No Messages)

When no messages exist, displays:
- Purple sparkles icon
- "How can I help you today?" heading
- Descriptive text
- 2-column grid of suggested prompts

### Active Chat State

When messages exist, displays:
- Scrollable message history
- Quick action buttons (My tasks, Suggestions)
- Clear chat button
- Chat input

### Tab Views

1. **Chat Tab**: Full chat interface
2. **Recommendations Tab**: List of RecommendationCards with badge count
3. **Daily Summary Tab**: Summary text and key metrics grid

---

## Message Types and Formatting

### ChatMessage Type

```typescript
interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

// Extended with UI metadata:
interface ChatMessageWithId extends ChatMessage {
  id: string;
  timestamp: string;
}
```

### Message Display

| Role | Alignment | Background | Avatar |
|------|-----------|------------|--------|
| User | Right | `bg-primary-500` (blue) | `UserIcon` in blue circle |
| Assistant | Left | `bg-gray-100` | `SparklesIcon` in purple circle |

### Message Bubble Styling

- **Border Radius**: `rounded-2xl` with corner cut (`rounded-br-sm` for user, `rounded-bl-sm` for AI)
- **Width**: Max 80% of container
- **Text**: `text-sm whitespace-pre-wrap break-words`
- **Timestamp**: Displayed below message in `text-xs text-gray-400`

### Recommendation Type

```typescript
interface Recommendation {
  type: string;
  priority: 'low' | 'medium' | 'high';
  title: string;
  description: string;
  action: string;
  entity_type?: string | null;
  entity_id?: number | null;
  activity_id?: number | null;
  amount?: number | null;
  score?: number | null;
}
```

### Recommendation Types & Icons

| Type | Icon |
|------|------|
| `follow_up` | PhoneIcon |
| `email` | EnvelopeIcon |
| `meeting` | CalendarIcon |
| `overdue_task` | ExclamationTriangleIcon |
| `hot_lead` | ArrowTrendingUpIcon |
| `at_risk` | ExclamationTriangleIcon |
| `engagement` | UserGroupIcon |
| `revenue` | CurrencyDollarIcon |
| `insight` | LightBulbIcon |

### Priority Colors

| Priority | Background | Text | Border |
|----------|------------|------|--------|
| Low | `bg-gray-50` | `text-gray-600` | `border-gray-200` |
| Medium | `bg-blue-50` | `text-blue-600` | `border-blue-200` |
| High | `bg-orange-50` | `text-orange-600` | `border-orange-200` |

---

## AI Capabilities

### 1. Conversational Chat

- Natural language queries about CRM data
- Session-based conversation continuity
- Real-time responses with loading states

### 2. Suggested Prompts

Pre-configured prompts to help users get started:

1. "What are my top priorities today?"
2. "Show me high-value opportunities closing this month"
3. "Which leads should I follow up with?"
4. "Give me a summary of recent activities"
5. "What tasks are overdue?"
6. "Find contacts in the technology industry"

### 3. Quick Actions

Contextual shortcuts available during active chat:
- **My tasks**: "What are my pending tasks?"
- **Suggestions**: "Give me actionable suggestions"

### 4. AI Recommendations

Prioritized action recommendations including:
- Follow-up calls
- Email outreach
- Meeting scheduling
- Overdue task alerts
- Hot lead notifications
- At-risk opportunity warnings
- Engagement suggestions
- Revenue opportunities
- General insights

Recommendations link to relevant entities (leads, contacts, opportunities, companies, activities).

### 5. Daily Summary

Automated daily briefing with:
- Text summary of CRM activity
- Key metrics displayed in a grid format
- Metrics are dynamically rendered based on available data

### 6. Additional AI Capabilities (Available via Hooks)

| Capability | Hook | Description |
|------------|------|-------------|
| Lead Insights | `useLeadInsights` | AI analysis of specific leads |
| Opportunity Insights | `useOpportunityInsights` | AI analysis of opportunities |
| Next Best Action | `useNextBestAction` | Recommended action for any entity |
| Semantic Search | `useSemanticSearch` | Natural language search across CRM |

---

## Component Files

| File | Path |
|------|------|
| Main Page | `/frontend/src/features/ai-assistant/AIAssistantPage.tsx` |
| Chat Message | `/frontend/src/features/ai-assistant/components/ChatMessage.tsx` |
| Chat Input | `/frontend/src/features/ai-assistant/components/ChatInput.tsx` |
| Recommendation Card | `/frontend/src/features/ai-assistant/components/RecommendationCard.tsx` |
| Index Export | `/frontend/src/features/ai-assistant/index.ts` |
| AI Hooks | `/frontend/src/hooks/useAI.ts` |
| AI API | `/frontend/src/api/ai.ts` |
| Types | `/frontend/src/types/index.ts` |

---

## Dependencies

### External Libraries

| Library | Usage |
|---------|-------|
| `react` | Core React hooks (useState, useEffect, useRef) |
| `clsx` | Conditional class name joining |
| `@heroicons/react` | Icon components |
| `@tanstack/react-query` | Data fetching and caching |
| `date-fns` | Timestamp formatting in ChatMessage |
| `react-router-dom` | Navigation links in RecommendationCard |
