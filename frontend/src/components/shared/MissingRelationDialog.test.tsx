import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MissingRelationDialog } from './MissingRelationDialog';

describe('MissingRelationDialog', () => {
  it('renders the entity-typed title and message when open', () => {
    render(
      <MissingRelationDialog
        isOpen
        entityType="proposal"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(
      screen.getByText(/Create proposal without a contact or company\?/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/no contact or company attached/i)
    ).toBeInTheDocument();
  });

  it('does not render when closed', () => {
    render(
      <MissingRelationDialog
        isOpen={false}
        entityType="quote"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('fires onConfirm when "Save anyway" is clicked', () => {
    const onConfirm = vi.fn();
    render(
      <MissingRelationDialog
        isOpen
        entityType="contract"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /save anyway/i }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('fires onCancel when "Back to form" is clicked', () => {
    const onCancel = vi.fn();
    render(
      <MissingRelationDialog
        isOpen
        entityType="proposal"
        onConfirm={vi.fn()}
        onCancel={onCancel}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /back to form/i }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it('uses the entityType in copy across all three variants', () => {
    const types = ['proposal', 'contract', 'quote'] as const;
    for (const t of types) {
      const { unmount } = render(
        <MissingRelationDialog
          isOpen
          entityType={t}
          onConfirm={vi.fn()}
          onCancel={vi.fn()}
        />
      );
      expect(
        screen.getByText(new RegExp(`Create ${t} without a contact or company\\?`, 'i'))
      ).toBeInTheDocument();
      unmount();
    }
  });
});
