import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, waitFor } from '../../test-utils/renderWithProviders';
import userEvent from '@testing-library/user-event';

// Mock hooks before importing the component
vi.mock('../../hooks/useLeads', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../hooks/useLeads')>();
  return {
    ...actual,
    useLeadKanban: vi.fn(),
    useMoveLeadStage: vi.fn(),
  };
});

vi.mock('../../hooks/useAuth', () => ({
  useUsers: vi.fn(),
}));

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

vi.mock('../../utils/toast', () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
  showInfo: vi.fn(),
}));

import { useLeadKanban, useMoveLeadStage } from '../../hooks/useLeads';
import { useUsers } from '../../hooks/useAuth';
import PipelinePage from './PipelinePage';
import type { KanbanLeadStage } from '../../types';

const mockMoveLeadMutate = vi.fn();

function makeLeadStage(
  stageId: number,
  name: string,
  leads: Array<{ id: number; full_name: string; company_name?: string | null }> = [],
): KanbanLeadStage {
  return {
    stage_id: stageId,
    stage_name: name,
    color: '#000',
    probability: 0,
    is_won: false,
    is_lost: false,
    count: leads.length,
    leads: leads.map((l) => ({
      id: l.id,
      first_name: null,
      last_name: null,
      full_name: l.full_name,
      email: null,
      company_name: l.company_name ?? null,
      score: 50,
      owner_id: null,
      owner_name: null,
    })),
  };
}

beforeEach(() => {
  vi.clearAllMocks();

  vi.mocked(useLeadKanban).mockReturnValue({
    data: { stages: [] },
    isLoading: false,
    error: null,
  } as unknown as ReturnType<typeof useLeadKanban>);
  vi.mocked(useMoveLeadStage).mockReturnValue({
    mutate: mockMoveLeadMutate,
  } as unknown as ReturnType<typeof useMoveLeadStage>);
  vi.mocked(useUsers).mockReturnValue({
    data: [],
  } as unknown as ReturnType<typeof useUsers>);
});

describe('PipelinePage', () => {
  it('renders the Pipeline heading', () => {
    renderWithProviders(<PipelinePage />);
    expect(screen.getByRole('heading', { name: 'Pipeline' })).toBeInTheDocument();
  });

  it('shows empty state when no stages are configured', () => {
    renderWithProviders(<PipelinePage />);
    expect(screen.getByText(/No pipeline stages configured/i)).toBeInTheDocument();
  });

  it('renders lead cards for each stage', () => {
    vi.mocked(useLeadKanban).mockReturnValue({
      data: {
        stages: [
          makeLeadStage(1, 'Discovery', [
            { id: 10, full_name: 'Alice Acme', company_name: 'Acme' },
          ]),
          makeLeadStage(2, 'Proposal', [
            { id: 11, full_name: 'Bob Globex', company_name: 'Globex' },
          ]),
        ],
      },
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useLeadKanban>);

    renderWithProviders(<PipelinePage />);

    expect(screen.getByText('Discovery')).toBeInTheDocument();
    expect(screen.getByText('Proposal')).toBeInTheDocument();
    expect(screen.getByText('Alice Acme')).toBeInTheDocument();
    expect(screen.getByText('Bob Globex')).toBeInTheDocument();
  });

  it('shows total lead count in toolbar', () => {
    vi.mocked(useLeadKanban).mockReturnValue({
      data: {
        stages: [
          makeLeadStage(1, 'Discovery', [
            { id: 10, full_name: 'Alice', company_name: 'Acme' },
            { id: 12, full_name: 'Carol', company_name: 'Carol Co' },
          ]),
          makeLeadStage(2, 'Proposal', [
            { id: 11, full_name: 'Bob', company_name: 'Globex' },
          ]),
        ],
      },
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useLeadKanban>);

    renderWithProviders(<PipelinePage />);

    expect(screen.getByText(/3 leads on board/i)).toBeInTheDocument();
  });

  it('filters leads in-memory when the search input is typed into', async () => {
    vi.mocked(useLeadKanban).mockReturnValue({
      data: {
        stages: [
          makeLeadStage(1, 'Discovery', [
            { id: 10, full_name: 'Alice Acme', company_name: 'Acme' },
            { id: 11, full_name: 'Bob Globex', company_name: 'Globex' },
          ]),
        ],
      },
      isLoading: false,
      error: null,
    } as unknown as ReturnType<typeof useLeadKanban>);

    renderWithProviders(<PipelinePage />);
    expect(screen.getByText('Alice Acme')).toBeInTheDocument();
    expect(screen.getByText('Bob Globex')).toBeInTheDocument();

    const user = userEvent.setup();
    const search = screen.getByLabelText('Search pipeline');
    await user.type(search, 'globex');

    // useDeferredValue resolves after userEvent drains its microtask
    // queue, but we still wait on the visible-DOM transition.
    await waitFor(() =>
      expect(screen.queryByText('Alice Acme')).not.toBeInTheDocument(),
    );
    expect(screen.getByText('Bob Globex')).toBeInTheDocument();
    expect(screen.getByText(/1 of 2 match/i)).toBeInTheDocument();
  });

  it('renders a Back to Leads link', () => {
    renderWithProviders(<PipelinePage />);
    expect(
      screen.getByRole('link', { name: /Back to Leads/i }),
    ).toHaveAttribute('href', '/leads');
  });
});
