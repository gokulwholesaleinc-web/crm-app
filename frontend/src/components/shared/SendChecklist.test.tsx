import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { SendChecklist } from './SendChecklist';
import { ChecklistItem, isChecklistReady } from './checklist';

const passedItem: ChecklistItem = { key: 'recipient', label: 'Recipient set', state: true };
const failedItem: ChecklistItem = {
  key: 'email',
  label: 'Contact has email',
  state: false,
  hint: 'Add a contact with an email.',
};
const optionalItem: ChecklistItem = { key: 'note', label: 'Cover note', state: 'optional' };

describe('SendChecklist rendering', () => {
  it('renders passed item with green check icon and normal label', () => {
    render(<SendChecklist items={[passedItem]} />);
    expect(screen.getByText('Recipient set')).toBeTruthy();
    const label = screen.getByText('Recipient set');
    expect(label.className).not.toMatch(/text-red/);
  });

  it('renders failed item with red label and hint text', () => {
    render(<SendChecklist items={[failedItem]} />);
    const label = screen.getByText('Contact has email');
    expect(label.className).toMatch(/text-red/);
    expect(screen.getByText('Add a contact with an email.')).toBeTruthy();
  });

  it('renders optional item without red styling', () => {
    render(<SendChecklist items={[optionalItem]} />);
    const label = screen.getByText('Cover note');
    expect(label.className).not.toMatch(/text-red/);
    expect(label.className).toMatch(/text-gray/);
  });

  it('renders custom title when provided', () => {
    render(<SendChecklist items={[passedItem]} title="Pre-flight check" />);
    expect(screen.getByText('Pre-flight check')).toBeTruthy();
  });

  it('renders default title when no title prop given', () => {
    render(<SendChecklist items={[passedItem]} />);
    expect(screen.getByText('Ready to send')).toBeTruthy();
  });
});

describe('SendChecklist hideWhenAllGreen', () => {
  it('returns null when hideWhenAllGreen is true and all required items pass', () => {
    const { container } = render(
      <SendChecklist
        items={[passedItem, optionalItem]}
        hideWhenAllGreen
      />
    );
    expect(container.firstChild).toBeNull();
  });

  it('still renders when hideWhenAllGreen is true but one required item fails', () => {
    render(
      <SendChecklist
        items={[passedItem, failedItem]}
        hideWhenAllGreen
      />
    );
    expect(screen.getByText('Ready to send')).toBeTruthy();
  });

  it('renders when hideWhenAllGreen is false even if all items pass', () => {
    render(
      <SendChecklist
        items={[passedItem]}
        hideWhenAllGreen={false}
      />
    );
    expect(screen.getByText('Ready to send')).toBeTruthy();
  });
});

describe('SendChecklist action button', () => {
  it('renders action button for an item with action prop', () => {
    const onClick = vi.fn();
    const item: ChecklistItem = {
      key: 'signer',
      label: 'Signer assigned',
      state: false,
      action: { label: 'Add signer', onClick },
    };
    render(<SendChecklist items={[item]} />);
    const btn = screen.getByRole('button', { name: 'Add signer' });
    expect(btn).toBeTruthy();
    fireEvent.click(btn);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it('does not render action button when action is not provided', () => {
    render(<SendChecklist items={[failedItem]} />);
    expect(screen.queryByRole('button')).toBeNull();
  });
});

describe('isChecklistReady', () => {
  it('returns true when all required items are true', () => {
    expect(isChecklistReady([passedItem])).toBe(true);
  });

  it('returns true when all required items pass and optional items are present', () => {
    expect(isChecklistReady([passedItem, optionalItem])).toBe(true);
  });

  it('returns true when all items are optional', () => {
    expect(isChecklistReady([optionalItem])).toBe(true);
  });

  it('returns false when one required item is false', () => {
    expect(isChecklistReady([passedItem, failedItem])).toBe(false);
  });

  it('returns false when a required item is false even with optional items', () => {
    expect(isChecklistReady([passedItem, failedItem, optionalItem])).toBe(false);
  });

  it('returns true for an empty list', () => {
    expect(isChecklistReady([])).toBe(true);
  });
});

describe('SendChecklist accessibility', () => {
  it('has aria-live="polite" on the container', () => {
    render(<SendChecklist items={[passedItem]} />);
    const region = screen.getByText('Ready to send').closest('[aria-live]');
    expect(region).toBeTruthy();
    expect(region?.getAttribute('aria-live')).toBe('polite');
  });
});
