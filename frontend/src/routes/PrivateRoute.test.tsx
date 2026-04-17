import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import { Route, Routes, useLocation } from 'react-router-dom';
import type { User } from '../store/authStore';

vi.mock('../store/authStore', () => {
  let _state: {
    isAuthenticated: boolean;
    isLoading: boolean;
    user: User | null;
    logout: () => void;
  } = {
    isAuthenticated: false,
    isLoading: false,
    user: null,
    logout: vi.fn(),
  };
  return {
    useAuthStore: () => _state,
    __setAuthState: (s: typeof _state) => {
      _state = s;
    },
  };
});

vi.mock('../components/layout/Layout', () => ({
  Layout: ({
    children,
    onLogout,
  }: {
    children: React.ReactNode;
    onLogout?: () => void;
  }) => (
    <div data-testid="layout">
      {children}
      {onLogout && (
        <button data-testid="logout-btn" onClick={onLogout}>
          Logout
        </button>
      )}
    </div>
  ),
}));

vi.mock('../components/ai/FloatingChatWidget', () => ({
  FloatingChatWidget: () => <div data-testid="floating-chat-widget" />,
}));

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const { __setAuthState } = await import('../store/authStore') as any;

import { renderWithProviders } from '../test-utils/renderWithProviders';
import { PrivateRoute } from './PrivateRoute';

const BASE_USER: User = {
  id: 1,
  email: 'test@example.com',
  full_name: 'Test User',
  is_active: true,
  is_superuser: false,
  role: 'sales_rep',
  created_at: '2026-01-01T00:00:00Z',
};

const mockLogout = vi.fn();

beforeEach(() => {
  vi.clearAllMocks();
  mockLogout.mockReset();
  __setAuthState({
    isAuthenticated: false,
    isLoading: false,
    user: null,
    logout: mockLogout,
  });
});

function renderPrivateRoute(child = <div data-testid="sentinel-child">protected content</div>) {
  return renderWithProviders(
    <Routes>
      <Route path="/" element={<PrivateRoute>{child}</PrivateRoute>} />
      <Route path="/login" element={<div data-testid="login-page">Login Page</div>} />
    </Routes>,
    { initialRoute: '/' }
  );
}

describe('PrivateRoute', () => {
  it('renders spinner while isLoading is true', () => {
    __setAuthState({ isAuthenticated: false, isLoading: true, user: null, logout: mockLogout });

    renderPrivateRoute();

    // Spinner renders an SVG with aria-hidden; assert wrapper div is present via its class
    const spinner = document.querySelector('svg.animate-spin');
    expect(spinner).toBeInTheDocument();
    expect(screen.queryByTestId('sentinel-child')).not.toBeInTheDocument();
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument();
  });

  it('redirects to /login when not authenticated', async () => {
    __setAuthState({ isAuthenticated: false, isLoading: false, user: null, logout: mockLogout });

    renderPrivateRoute();

    await screen.findByTestId('login-page');
    expect(screen.queryByTestId('sentinel-child')).not.toBeInTheDocument();
  });

  it('renders children inside Layout when authenticated', () => {
    __setAuthState({ isAuthenticated: true, isLoading: false, user: BASE_USER, logout: mockLogout });

    renderPrivateRoute();

    expect(screen.getByTestId('layout')).toBeInTheDocument();
    expect(screen.getByTestId('sentinel-child')).toBeInTheDocument();
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument();
  });

  it('passes current location in Navigate state when redirecting', async () => {
    __setAuthState({ isAuthenticated: false, isLoading: false, user: null, logout: mockLogout });

    function LoginWithState() {
      const loc = useLocation();
      const from = (loc.state as { from?: { pathname: string } } | null)?.from?.pathname ?? 'no-state';
      return <div data-testid="login-state">{from}</div>;
    }

    renderWithProviders(
      <Routes>
        <Route path="/" element={<PrivateRoute><div>protected</div></PrivateRoute>} />
        <Route path="/login" element={<LoginWithState />} />
      </Routes>,
      { initialRoute: '/' }
    );

    const stateEl = await screen.findByTestId('login-state');
    expect(stateEl.textContent).toBe('/');
  });

  it('calls logout when Layout onLogout is triggered', async () => {
    __setAuthState({ isAuthenticated: true, isLoading: false, user: BASE_USER, logout: mockLogout });

    renderPrivateRoute();

    fireEvent.click(screen.getByTestId('logout-btn'));

    await waitFor(() => expect(mockLogout).toHaveBeenCalledTimes(1));
  });
});
