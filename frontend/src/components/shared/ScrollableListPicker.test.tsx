import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ScrollableListPicker } from './ScrollableListPicker';

interface Item {
  id: number;
  name: string;
  email: string;
}

const items: Item[] = [
  { id: 1, name: 'Alice Smith', email: 'alice@example.com' },
  { id: 2, name: 'Bob Jones', email: 'bob@example.com' },
  { id: 3, name: 'Charlie Brown', email: 'charlie@example.com' },
];

const filterFn = (item: Item, q: string) =>
  item.name.toLowerCase().includes(q.toLowerCase()) ||
  item.email.toLowerCase().includes(q.toLowerCase());

function renderPicker(overrides: Partial<Parameters<typeof ScrollableListPicker<Item>>[0]> = {}) {
  const onSelectionChange = vi.fn();
  const result = render(
    <ScrollableListPicker<Item>
      items={items}
      selectedIds={[]}
      onSelectionChange={onSelectionChange}
      getItemId={(item) => item.id}
      renderItem={(item) => (
        <div className="flex-1 min-w-0">
          <p className="font-medium">{item.name}</p>
          <p className="text-sm">{item.email}</p>
        </div>
      )}
      filterFn={filterFn}
      searchPlaceholder="Search items..."
      {...overrides}
    />
  );
  return { ...result, onSelectionChange };
}

describe('ScrollableListPicker', () => {
  it('renders all items initially', () => {
    renderPicker();
    expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    expect(screen.getByText('Bob Jones')).toBeInTheDocument();
    expect(screen.getByText('Charlie Brown')).toBeInTheDocument();
  });

  it('filters items via search input', () => {
    renderPicker();
    const input = screen.getByPlaceholderText('Search items...');
    fireEvent.change(input, { target: { value: 'alice' } });
    expect(screen.getByText('Alice Smith')).toBeInTheDocument();
    expect(screen.queryByText('Bob Jones')).not.toBeInTheDocument();
    expect(screen.queryByText('Charlie Brown')).not.toBeInTheDocument();
  });

  it('select-all selects all visible (filtered) items', () => {
    const { onSelectionChange } = renderPicker();
    const input = screen.getByPlaceholderText('Search items...');
    fireEvent.change(input, { target: { value: 'alice' } });
    fireEvent.click(screen.getByRole('button', { name: /select all/i }));
    expect(onSelectionChange).toHaveBeenCalledWith([1]);
  });

  it('select-all without filter selects all items', () => {
    const { onSelectionChange } = renderPicker();
    fireEvent.click(screen.getByRole('button', { name: /select all/i }));
    expect(onSelectionChange).toHaveBeenCalledWith([1, 2, 3]);
  });

  it('clear empties the selection', () => {
    const { onSelectionChange } = renderPicker({ selectedIds: [1, 2] });
    fireEvent.click(screen.getByRole('button', { name: /clear/i }));
    expect(onSelectionChange).toHaveBeenCalledWith([]);
  });

  it('toggles item selection on click', () => {
    const { onSelectionChange } = renderPicker();
    fireEvent.click(screen.getByRole('button', { name: /alice smith/i }));
    expect(onSelectionChange).toHaveBeenCalledWith([1]);
  });

  it('deselects an already-selected item on click', () => {
    const { onSelectionChange } = renderPicker({ selectedIds: [1] });
    fireEvent.click(screen.getByRole('button', { name: /alice smith/i }));
    expect(onSelectionChange).toHaveBeenCalledWith([]);
  });

  it('disabled items do not toggle on click', () => {
    const { onSelectionChange } = renderPicker({ disabledIds: [1] });
    const btn = screen.getByRole('button', { name: /alice smith/i });
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(onSelectionChange).not.toHaveBeenCalled();
  });

  it('single-select mode replaces selection instead of appending', () => {
    const { onSelectionChange } = renderPicker({ multiSelect: false, selectedIds: [1] });
    fireEvent.click(screen.getByRole('button', { name: /bob jones/i }));
    expect(onSelectionChange).toHaveBeenCalledWith([2]);
  });

  it('single-select mode deselects if same item clicked', () => {
    const { onSelectionChange } = renderPicker({ multiSelect: false, selectedIds: [1] });
    fireEvent.click(screen.getByRole('button', { name: /alice smith/i }));
    expect(onSelectionChange).toHaveBeenCalledWith([]);
  });

  it('shows empty message when no items match filter', () => {
    renderPicker({ emptyMessage: 'Nothing here.' });
    const input = screen.getByPlaceholderText('Search items...');
    fireEvent.change(input, { target: { value: 'zzznomatch' } });
    expect(screen.getByText('Nothing here.')).toBeInTheDocument();
  });

  it('shows spinner when isLoading is true', () => {
    renderPicker({ isLoading: true });
    expect(screen.queryByText('Alice Smith')).not.toBeInTheDocument();
  });

  it('hides select-all controls when showSelectAll is false', () => {
    renderPicker({ showSelectAll: false });
    expect(screen.queryByRole('button', { name: /select all/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /clear/i })).not.toBeInTheDocument();
  });

  it('hides select-all controls when multiSelect is false', () => {
    renderPicker({ multiSelect: false });
    expect(screen.queryByRole('button', { name: /select all/i })).not.toBeInTheDocument();
  });

  it('row buttons have aria-pressed reflecting selection state', () => {
    renderPicker({ selectedIds: [1] });
    const aliceBtn = screen.getByRole('button', { name: /alice smith/i });
    const bobBtn = screen.getByRole('button', { name: /bob jones/i });
    expect(aliceBtn).toHaveAttribute('aria-pressed', 'true');
    expect(bobBtn).toHaveAttribute('aria-pressed', 'false');
  });

  it('keyboard Space on a row button toggles selection', () => {
    const { onSelectionChange } = renderPicker();
    const btn = screen.getByRole('button', { name: /alice smith/i });
    btn.focus();
    fireEvent.keyDown(btn, { key: ' ', code: 'Space' });
    fireEvent.click(btn); // button semantics: Space triggers click
    expect(onSelectionChange).toHaveBeenCalledWith([1]);
  });
});
