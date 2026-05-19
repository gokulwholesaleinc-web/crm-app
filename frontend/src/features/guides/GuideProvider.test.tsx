import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { accountApi, type AccountPreferences } from '../../api/account';
import { useAuthStore, type User } from '../../store/authStore';
import { GuideProvider, GuideTourOverlay, useGuides } from './GuideProvider';
import type { Guide } from './guideContent';

vi.mock('../../api/account', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/account')>();
  return {
    ...actual,
    accountApi: {
      ...actual.accountApi,
      getAccountPreferences: vi.fn(),
      updateAccountPreferences: vi.fn(),
    },
  };
});

const TEST_USER: User = {
  id: 7,
  email: 'admin@example.com',
  full_name: 'Admin User',
  is_active: true,
  is_superuser: true,
  role: 'admin',
  created_at: '2026-05-18T00:00:00.000Z',
};

const ACCOUNT_PREFS: AccountPreferences = {
  timezone: 'America/Chicago',
  locale: 'en-US',
  date_format: 'MM/DD/YYYY',
  time_format: '12h',
  week_start: 'sunday',
  currency_display: 'USD',
  theme: 'system',
  default_landing: '/dashboard',
  guide_progress: {},
};

const MISSING_TARGET_GUIDE: Guide = {
  id: 'missing-target',
  title: 'Missing target',
  description: 'Test guide',
  roles: ['sales_rep'],
  path: '/',
  steps: [
    {
      title: 'Still useful',
      body: 'This step should render without a matching selector.',
      selector: '[data-guide="does-not-exist"]',
    },
  ],
};

const ACTION_STEP_GUIDE: Guide = {
  id: 'action-step',
  title: 'Action step tour',
  description: 'Test guide',
  roles: ['sales_rep'],
  path: '/',
  steps: [
    {
      title: 'Use the control',
      body: 'This step should expose action styling and progress.',
      action: 'click the visible control.',
      selector: '[data-guide="action-target"]',
    },
    {
      title: 'Confirm the result',
      body: 'This step finishes the guide.',
      selector: '[data-guide="action-target"]',
    },
  ],
};

describe('GuideTourOverlay', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: TEST_USER,
      token: 'token',
      isAuthenticated: true,
      isLoading: false,
    });
    vi.mocked(accountApi.getAccountPreferences).mockResolvedValue(ACCOUNT_PREFS);
    vi.mocked(accountApi.updateAccountPreferences).mockResolvedValue(ACCOUNT_PREFS);
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows text and warns in dev when a selector is missing', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});

    render(
      <GuideTourOverlay
        guide={MISSING_TARGET_GUIDE}
        stepIndex={0}
        onStepChange={() => {}}
        onClose={() => {}}
        onComplete={() => {}}
      />,
    );

    expect(screen.getByRole('dialog', { name: 'Still useful' })).toBeInTheDocument();
    expect(screen.getByText('This step should render without a matching selector.')).toBeInTheDocument();
    expect(screen.getByText(/You can keep going/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(warn).toHaveBeenCalledWith(
        expect.stringContaining('[guides] Missing selector "[data-guide="does-not-exist"]"'),
      );
    });
  });

  it('shows guide progress and action-step treatment', () => {
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      x: 16,
      y: 24,
      top: 24,
      right: 160,
      bottom: 72,
      left: 16,
      width: 144,
      height: 48,
      toJSON: () => ({}),
    } as DOMRect);

    render(
      <>
        <button type="button" data-guide="action-target">
          Target
        </button>
        <GuideTourOverlay
          guide={ACTION_STEP_GUIDE}
          stepIndex={0}
          onStepChange={() => {}}
          onClose={() => {}}
          onComplete={() => {}}
        />
      </>,
    );

    expect(screen.getByText('Action step')).toBeInTheDocument();
    expect(screen.getByText('Step 1 of 2')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
    expect(screen.getByText(/click the visible control/i)).toBeInTheDocument();
    expect(
      screen.getByRole('progressbar', { name: 'Action step tour progress' }),
    ).toHaveAttribute('aria-valuenow', '1');
  });
});

function GuideHarness() {
  const guides = useGuides();
  return (
    <>
      <div data-guide="dashboard-header" style={{ width: 1, height: 1 }} />
      <div data-testid="completed">{guides.completedGuideIds.join(',') || 'none'}</div>
      <div data-testid="active">{guides.activeGuide?.id ?? 'none'}</div>
      <button type="button" onClick={() => guides.startGuide('dashboard-tour')}>
        Start dashboard
      </button>
      <button type="button" onClick={guides.completeGuide}>
        Complete current
      </button>
    </>
  );
}

function renderGuideProvider() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/']}>
        <GuideProvider>
          <GuideHarness />
        </GuideProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('GuideProvider account persistence', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: TEST_USER,
      token: 'token',
      isAuthenticated: true,
      isLoading: false,
    });
    vi.mocked(accountApi.getAccountPreferences).mockResolvedValue({
      ...ACCOUNT_PREFS,
      guide_progress: { completed_guide_ids: ['pipeline-tour'] },
    });
    vi.mocked(accountApi.updateAccountPreferences).mockResolvedValue({
      ...ACCOUNT_PREFS,
      guide_progress: { completed_guide_ids: ['dashboard-tour', 'pipeline-tour'] },
    });
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('hydrates guide completion from account preferences', async () => {
    renderGuideProvider();

    await waitFor(() => {
      expect(screen.getByTestId('completed')).toHaveTextContent('pipeline-tour');
    });
  });

  it('saves completed guides back to account preferences', async () => {
    const user = userEvent.setup();
    renderGuideProvider();

    await waitFor(() => {
      expect(screen.getByTestId('completed')).toHaveTextContent('pipeline-tour');
    });

    await user.click(screen.getByRole('button', { name: 'Start dashboard' }));
    await waitFor(() => {
      expect(screen.getByTestId('active')).toHaveTextContent('dashboard-tour');
    });

    await user.click(screen.getByRole('button', { name: 'Complete current' }));

    await waitFor(() => {
      expect(accountApi.updateAccountPreferences).toHaveBeenCalledWith({
        guide_progress: {
          completed_guide_ids: ['dashboard-tour', 'pipeline-tour'],
          first_run_dismissed_at: null,
          disabled_at: null,
          last_reset_at: null,
        },
      });
    });
  });
});
