import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, waitFor, fireEvent } from '../../test-utils/renderWithProviders';
import { EmailSearchModal } from './EmailSearchModal';

describe('EmailSearchModal', () => {
  it('renders the search input when isOpen is true', () => {
    renderWithProviders(<EmailSearchModal isOpen={true} onClose={vi.fn()} />);
    expect(screen.getByPlaceholderText(/search emails/i)).toBeInTheDocument();
  });

  it('does not render when isOpen is false', () => {
    renderWithProviders(<EmailSearchModal isOpen={false} onClose={vi.fn()} />);
    expect(screen.queryByPlaceholderText(/search emails/i)).not.toBeInTheDocument();
  });

  it('shows prompt text when no query is entered', () => {
    renderWithProviders(<EmailSearchModal isOpen={true} onClose={vi.fn()} />);
    expect(screen.getByText(/type to search across your emails/i)).toBeInTheDocument();
  });

  it('close button calls onClose', () => {
    const onClose = vi.fn();
    renderWithProviders(<EmailSearchModal isOpen={true} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: /close search/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('ESC key closes the modal via Headless UI Dialog', async () => {
    const onClose = vi.fn();
    renderWithProviders(<EmailSearchModal isOpen={true} onClose={onClose} />);
    fireEvent.keyDown(document.body, { key: 'Escape' });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('shows entity-scope toggle when entityType and entityId are provided', () => {
    renderWithProviders(
      <EmailSearchModal isOpen={true} onClose={vi.fn()} entityType="contacts" entityId={42} />
    );
    expect(screen.getByText(/search across all emails/i)).toBeInTheDocument();
  });

  it('does not show entity-scope toggle when no entity context is provided', () => {
    renderWithProviders(<EmailSearchModal isOpen={true} onClose={vi.fn()} />);
    expect(screen.queryByText(/search across all emails/i)).not.toBeInTheDocument();
  });
});
