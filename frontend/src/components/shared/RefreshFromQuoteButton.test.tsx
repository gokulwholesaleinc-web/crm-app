import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, fireEvent, waitFor } from '../../test-utils/renderWithProviders';
import { RefreshFromQuoteButton } from './RefreshFromQuoteButton';

// Mock the hook so tests don't need a server
vi.mock('../../hooks/useProposals', () => ({
  useRefreshProposalFromQuote: vi.fn(),
}));

// Mock toast
vi.mock('../../utils/toast', () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

import { useRefreshProposalFromQuote } from '../../hooks/useProposals';
import { showSuccess, showError } from '../../utils/toast';

const mockMutate = vi.fn();

function setupMutation(isPending = false) {
  (useRefreshProposalFromQuote as ReturnType<typeof vi.fn>).mockReturnValue({
    mutate: mockMutate,
    isPending,
  });
}

function renderButton(
  props: Partial<React.ComponentProps<typeof RefreshFromQuoteButton>> = {}
) {
  return renderWithProviders(
    <RefreshFromQuoteButton
      proposalId={1}
      hasQuoteLink={true}
      isLocked={false}
      {...props}
    />,
  );
}

describe('RefreshFromQuoteButton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupMutation();
  });

  it('renders nothing when hasQuoteLink is false', () => {
    renderButton({ hasQuoteLink: false });
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('renders the button when hasQuoteLink is true', () => {
    renderButton();
    expect(screen.getByRole('button', { name: /refresh from quote/i })).toBeTruthy();
  });

  it('is disabled when isLocked is true', () => {
    renderButton({ isLocked: true });
    const btn = screen.getByRole('button', { name: /refresh from quote/i });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it('is not disabled when isLocked is false', () => {
    renderButton({ isLocked: false });
    const btn = screen.getByRole('button', { name: /refresh from quote/i });
    expect((btn as HTMLButtonElement).disabled).toBe(false);
  });

  it('is disabled while mutation is pending', () => {
    setupMutation(true);
    renderButton();
    const btn = screen.getByRole('button', { name: /refresh from quote/i });
    expect((btn as HTMLButtonElement).disabled).toBe(true);
  });

  it('opens confirmation dialog on click', () => {
    renderButton();
    fireEvent.click(screen.getByRole('button', { name: /refresh from quote/i }));
    expect(screen.getByText(/refresh from quote\?/i)).toBeTruthy();
  });

  it('shows the correct confirmation message', () => {
    renderButton();
    fireEvent.click(screen.getByRole('button', { name: /refresh from quote/i }));
    expect(
      screen.getByText(/this replaces the proposal's amount with the current quote total/i)
    ).toBeTruthy();
  });

  it('does not call mutate before confirmation', () => {
    renderButton();
    fireEvent.click(screen.getByRole('button', { name: /refresh from quote/i }));
    // Dialog is open but mutate not called yet
    expect(mockMutate).not.toHaveBeenCalled();
  });

  it('calls mutate with proposalId when Refresh is confirmed', () => {
    renderButton({ proposalId: 42 });
    fireEvent.click(screen.getByRole('button', { name: /refresh from quote/i }));
    fireEvent.click(screen.getByRole('button', { name: /^refresh$/i }));
    expect(mockMutate).toHaveBeenCalledWith(42, expect.any(Object));
  });

  it('closes dialog on Cancel', () => {
    renderButton();
    fireEvent.click(screen.getByRole('button', { name: /refresh from quote/i }));
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByText(/refresh from quote\?/i)).toBeNull();
  });

  it('calls showSuccess and onRefreshed on successful mutation', async () => {
    const onRefreshed = vi.fn();
    mockMutate.mockImplementation((_id: number, { onSuccess }: { onSuccess: () => void }) => {
      onSuccess();
    });

    renderButton({ proposalId: 7, onRefreshed });
    fireEvent.click(screen.getByRole('button', { name: /refresh from quote/i }));
    fireEvent.click(screen.getByRole('button', { name: /^refresh$/i }));

    await waitFor(() => {
      expect(showSuccess).toHaveBeenCalledWith('Proposal synced from quote.');
      expect(onRefreshed).toHaveBeenCalledTimes(1);
    });
  });

  it('calls showError on failed mutation', async () => {
    mockMutate.mockImplementation(
      (_id: number, { onError }: { onError: (e: Error) => void }) => {
        onError(new Error('Quote deleted'));
      }
    );

    renderButton();
    fireEvent.click(screen.getByRole('button', { name: /refresh from quote/i }));
    fireEvent.click(screen.getByRole('button', { name: /^refresh$/i }));

    await waitFor(() => {
      expect(showError).toHaveBeenCalledWith('Quote deleted');
    });
  });
});
