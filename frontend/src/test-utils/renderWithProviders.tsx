import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { createElement } from 'react';

export { screen, within, waitFor, fireEvent, act } from '@testing-library/react';

interface RenderOptions {
  initialRoute?: string;
  queryClient?: QueryClient;
}

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

export function renderWithProviders(
  ui: React.ReactElement,
  { initialRoute = '/', queryClient }: RenderOptions = {}
) {
  const client = queryClient ?? makeQueryClient();
  const wrapped = createElement(
    QueryClientProvider,
    { client },
    createElement(MemoryRouter, { initialEntries: [initialRoute] }, ui)
  );
  return { ...render(wrapped), queryClient: client };
}
