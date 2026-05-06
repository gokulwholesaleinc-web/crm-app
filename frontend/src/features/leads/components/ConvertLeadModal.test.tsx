import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, fireEvent, waitFor } from '../../../test-utils/renderWithProviders';
import { ConvertLeadModal } from './ConvertLeadModal';

vi.mock('../../../hooks/useOpportunities', () => ({
  usePipelineStages: () => ({ data: null, isLoading: false }),
}));

const onClose = vi.fn();
const onConvert = vi.fn();

const BASE_PROPS = {
  isOpen: true,
  leadId: 'lead-1',
  leadName: 'Acme Corp',
  onClose,
  onConvert,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ConvertLeadModal', () => {
  it('renders the modal with lead name', () => {
    renderWithProviders(<ConvertLeadModal {...BASE_PROPS} />);
    expect(screen.getByText(/Convert "Acme Corp"/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();
  });

  it('Cancel while form is clean calls onClose immediately', () => {
    renderWithProviders(<ConvertLeadModal {...BASE_PROPS} />);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Discard changes?')).not.toBeInTheDocument();
  });

  it('Cancel while form is dirty shows confirm dialog', async () => {
    renderWithProviders(<ConvertLeadModal {...BASE_PROPS} />);
    // Uncheck createContact (default is true) — makes form dirty
    fireEvent.click(screen.getByRole('checkbox', { name: /Create Contact/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onClose).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.getByText('Discard changes?')).toBeInTheDocument();
    });
  });

  it('confirming discard resets form and calls onClose', async () => {
    renderWithProviders(<ConvertLeadModal {...BASE_PROPS} />);
    // Dirty the form
    fireEvent.click(screen.getByRole('checkbox', { name: /Create Contact/i }));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => screen.getByText('Discard changes?'));
    fireEvent.click(screen.getByRole('button', { name: 'Discard' }));
    await waitFor(() => {
      expect(onClose).toHaveBeenCalledTimes(1);
    });
  });

  it('Keep editing in confirm dialog closes confirm and keeps modal open with values', async () => {
    renderWithProviders(<ConvertLeadModal {...BASE_PROPS} />);
    // Dirty the form by unchecking createContact
    const createContactCheckbox = screen.getByRole('checkbox', { name: /Create Contact/i });
    fireEvent.click(createContactCheckbox);
    expect(createContactCheckbox).not.toBeChecked();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => screen.getByText('Discard changes?'));

    fireEvent.click(screen.getByRole('button', { name: 'Keep editing' }));
    await waitFor(() => {
      expect(screen.queryByText('Discard changes?')).not.toBeInTheDocument();
    });
    // Modal still open, value still reflects user's edit
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole('checkbox', { name: /Create Contact/i })).not.toBeChecked();
  });
});
