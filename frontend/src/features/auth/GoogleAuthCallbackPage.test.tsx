import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

vi.mock('../../api/auth', () => ({
  authApi: {
    googleCallback: vi.fn(),
    getMe: vi.fn(),
  },
}));

vi.mock('../../providers/TenantProvider', () => ({
  setTenantSlugOnLogin: vi.fn(),
  useTenant: () => ({ tenant: null }),
}));

const MOCK_AUTH = { login: vi.fn() };
vi.mock('../../store/authStore', () => ({
  useAuthStore: vi.fn((selector?: (s: typeof MOCK_AUTH) => unknown) =>
    selector ? selector(MOCK_AUTH) : MOCK_AUTH
  ),
}));

vi.mock('./GoogleSignInButton', () => ({
  GOOGLE_OAUTH_CALLBACK_PATH: '/auth/google/callback',
  default: () => <button>Sign in with Google</button>,
  AuthDivider: () => <hr />,
}));

import { authApi } from '../../api/auth';
import GoogleAuthCallbackPage from './GoogleAuthCallbackPage';

function renderPage(search: string) {
  return render(
    <MemoryRouter initialEntries={[`/auth/google/callback${search}`]}>
      <GoogleAuthCallbackPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('GoogleAuthCallbackPage', () => {
  it('renders pending state when callback returns pending_approval=true', async () => {
    const err = { detail: { pending_approval: true, detail: 'pending' } };
    vi.mocked(authApi.googleCallback).mockRejectedValue(err);

    renderPage('?code=abc&state=xyz');

    await screen.findByText(/pending admin approval/i);
    expect(screen.getByRole('button', { name: /back to sign in/i })).toBeInTheDocument();
  });

  it('renders rejected state when callback returns rejected=true', async () => {
    const err = { detail: { rejected: true, detail: 'rejected' } };
    vi.mocked(authApi.googleCallback).mockRejectedValue(err);

    renderPage('?code=abc&state=xyz');

    await screen.findByText(/access denied/i);
    expect(screen.getByRole('button', { name: /back to sign in/i })).toBeInTheDocument();
  });

  it('renders generic error for non-approval 403s', async () => {
    vi.mocked(authApi.googleCallback).mockRejectedValue(new Error('Something went wrong'));

    renderPage('?code=abc&state=xyz');

    await screen.findByText(/something went wrong/i);
  });

  it('shows error when code is missing', () => {
    renderPage('?state=xyz');
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});
