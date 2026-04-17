import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders, screen, fireEvent } from '../../test-utils/renderWithProviders';
import { DuplicateWarningModal } from './DuplicateWarningModal';
import type { DuplicateMatch } from '../../api/dedup';

const makeDup = (overrides: Partial<DuplicateMatch> = {}): DuplicateMatch => ({
  id: 1,
  entity_type: 'contacts',
  display_name: 'Acme Corp',
  email: 'hello@acme.test',
  phone: '555-0100',
  match_reason: 'Email match',
  ...overrides,
});

const baseProps = {
  isOpen: true,
  onClose: vi.fn(),
  onCreateAnyway: vi.fn(),
  onViewDuplicate: vi.fn(),
  duplicates: [makeDup()],
  entityType: 'contacts',
};

function renderModal(props: Partial<typeof baseProps> = {}) {
  return renderWithProviders(
    <DuplicateWarningModal {...baseProps} {...props} />,
  );
}

describe('DuplicateWarningModal', () => {
  it('does not render duplicate list when isOpen is false', () => {
    renderModal({ isOpen: false });
    expect(screen.queryByText('Acme Corp')).toBeNull();
  });

  it('shows singular "potential duplicate" for 1 match', () => {
    renderModal({ duplicates: [makeDup()] });
    expect(screen.getByText(/1 potential duplicate[^s]/)).toBeTruthy();
  });

  it('shows plural "potential duplicates" for 2 matches', () => {
    renderModal({
      duplicates: [makeDup({ id: 1 }), makeDup({ id: 2, display_name: 'Beta Ltd' })],
    });
    expect(screen.getByText(/2 potential duplicates/)).toBeTruthy();
  });

  it('shows "contact" entity label when entityType is contacts', () => {
    renderModal({ entityType: 'contacts' });
    expect(screen.getByText(/new contact/)).toBeTruthy();
  });

  it('shows "company" entity label when entityType is companies', () => {
    renderModal({ entityType: 'companies' });
    expect(screen.getByText(/new company/)).toBeTruthy();
  });

  it('shows "lead" entity label for any other entityType', () => {
    renderModal({ entityType: 'leads' });
    expect(screen.getByText(/new lead/)).toBeTruthy();
  });

  it('renders each duplicate display_name, email, phone, and match_reason', () => {
    renderModal({
      duplicates: [makeDup({ display_name: 'Test Corp', email: 'test@test.com', phone: '999-1234', match_reason: 'Phone match' })],
    });
    expect(screen.getByText('Test Corp')).toBeTruthy();
    expect(screen.getByText('test@test.com')).toBeTruthy();
    expect(screen.getByText('999-1234')).toBeTruthy();
    expect(screen.getByText('Phone match')).toBeTruthy();
  });

  it('calls onViewDuplicate with the correct id when View is clicked', () => {
    const onViewDuplicate = vi.fn();
    renderModal({
      duplicates: [makeDup({ id: 42 })],
      onViewDuplicate,
    });
    fireEvent.click(screen.getByRole('button', { name: /view/i }));
    expect(onViewDuplicate).toHaveBeenCalledWith(42);
  });

  it('calls onClose when Cancel is clicked', () => {
    const onClose = vi.fn();
    renderModal({ onClose });
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onCreateAnyway when Create Anyway is clicked', () => {
    const onCreateAnyway = vi.fn();
    renderModal({ onCreateAnyway });
    fireEvent.click(screen.getByRole('button', { name: /create anyway/i }));
    expect(onCreateAnyway).toHaveBeenCalledTimes(1);
  });
});
