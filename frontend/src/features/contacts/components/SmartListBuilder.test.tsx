import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen } from '../../../test-utils/renderWithProviders';
import userEvent from '@testing-library/user-event';
import { SmartListBuilder } from './SmartListBuilder';

const createSavedFilterMutateAsync = vi.fn();
const aggregateMutateAsync = vi.fn();

vi.mock('../../../hooks/useFilters', () => ({
  useCreateSavedFilter: () => ({
    mutateAsync: createSavedFilterMutateAsync,
    isPending: false,
  }),
  useFilterAggregate: () => ({
    mutateAsync: aggregateMutateAsync,
    isPending: false,
  }),
}));

vi.mock('../../../utils/toast', () => ({
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

describe('SmartListBuilder', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('keeps numeric-looking contact text values as strings', async () => {
    const user = userEvent.setup();
    const onApplyFilters = vi.fn();

    renderWithProviders(
      <SmartListBuilder entityType="contacts" onApplyFilters={onApplyFilters} onClose={vi.fn()} />,
    );

    await user.selectOptions(screen.getByLabelText('Field'), 'first_name');
    await user.type(screen.getByLabelText('Value'), '00123');
    await user.click(screen.getByRole('button', { name: 'Apply Filters' }));

    expect(onApplyFilters).toHaveBeenCalledWith({
      operator: 'and',
      conditions: [{ field: 'first_name', op: 'eq', value: '00123' }],
    });
  });

  it('requires a non-empty value before applying or saving value-based conditions', async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <SmartListBuilder entityType="contacts" onApplyFilters={vi.fn()} onClose={vi.fn()} />,
    );

    await user.selectOptions(screen.getByLabelText('Field'), 'email');

    expect(screen.getByRole('button', { name: 'Apply Filters' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Save as Smart List' })).toBeDisabled();

    await user.selectOptions(screen.getByLabelText('Operator'), 'is_empty');

    expect(screen.getByRole('button', { name: 'Apply Filters' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Save as Smart List' })).toBeEnabled();
  });

  it('limits operators to choices that match the selected field type', async () => {
    const user = userEvent.setup();

    renderWithProviders(
      <SmartListBuilder entityType="contacts" onApplyFilters={vi.fn()} onClose={vi.fn()} />,
    );

    await user.selectOptions(screen.getByLabelText('Field'), 'first_name');
    expect(screen.getByRole('option', { name: 'Contains' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Greater Than' })).not.toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Between' })).not.toBeInTheDocument();
  });

  it('parses number fields as numbers for company filters', async () => {
    const user = userEvent.setup();
    const onApplyFilters = vi.fn();

    renderWithProviders(
      <SmartListBuilder entityType="companies" onApplyFilters={onApplyFilters} onClose={vi.fn()} />,
    );

    await user.selectOptions(screen.getByLabelText('Field'), 'annual_revenue');
    await user.selectOptions(screen.getByLabelText('Operator'), 'gt');
    await user.type(screen.getByLabelText('Value'), '500000');
    await user.click(screen.getByRole('button', { name: 'Apply Filters' }));

    expect(onApplyFilters).toHaveBeenCalledWith({
      operator: 'and',
      conditions: [{ field: 'annual_revenue', op: 'gt', value: 500000 }],
    });
  });
});
