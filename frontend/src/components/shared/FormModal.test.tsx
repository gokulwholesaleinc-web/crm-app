import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderWithProviders, screen, fireEvent, act } from '../../test-utils/renderWithProviders';
import { FormModal, FormModalProps } from './FormModal';

interface TestForm {
  name: string;
}

const TEST_DEFAULTS: TestForm = { name: '' };

// Typed wrapper to avoid explicit generic syntax in JSX
function TestFormModal(props: Partial<FormModalProps<TestForm>> & { initialName?: string }) {
  const {
    isOpen = true,
    onClose = vi.fn(),
    onSubmit = vi.fn<[TestForm], Promise<void>>().mockResolvedValue(undefined),
    isPending = false,
    isError = false,
    initialName = '',
    ...rest
  } = props;

  return (
    <FormModal
      isOpen={isOpen}
      onClose={onClose}
      title="Test Modal"
      defaultValues={{ name: initialName || TEST_DEFAULTS.name }}
      onSubmit={onSubmit}
      isPending={isPending}
      isError={isError}
      errorMessage="Save failed. Please try again."
      {...rest}
    >
      {({ register }) => (
        <input
          data-testid="name-input"
          {...register('name')}
          placeholder="Enter name"
        />
      )}
    </FormModal>
  );
}

describe('FormModal', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders title and input when open', () => {
    renderWithProviders(<TestFormModal />);
    expect(screen.getByText('Test Modal')).toBeTruthy();
    expect(screen.getByTestId('name-input')).toBeTruthy();
  });

  it('does not show content when closed', () => {
    renderWithProviders(<TestFormModal isOpen={false} />);
    expect(screen.queryByText('Test Modal')).toBeNull();
  });

  it('calls onClose when Cancel is clicked', async () => {
    const onClose = vi.fn();
    renderWithProviders(<TestFormModal onClose={onClose} />);
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('calls onSubmit with form data on submit', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(<TestFormModal onSubmit={onSubmit} />);

    fireEvent.change(screen.getByTestId('name-input'), { target: { value: 'Hello' } });

    await act(async () => {
      fireEvent.submit(screen.getByRole('button', { name: /save/i }).closest('form')!);
    });

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ name: 'Hello' }));
  });

  it('shows success banner after successful submit', async () => {
    const onClose = vi.fn();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(<TestFormModal onClose={onClose} onSubmit={onSubmit} />);

    await act(async () => {
      fireEvent.submit(screen.getByRole('button', { name: /save/i }).closest('form')!);
    });

    expect(screen.getByText('Saved successfully!')).toBeTruthy();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('auto-closes after 800ms following successful submit', async () => {
    const onClose = vi.fn();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderWithProviders(<TestFormModal onClose={onClose} onSubmit={onSubmit} />);

    await act(async () => {
      fireEvent.submit(screen.getByRole('button', { name: /save/i }).closest('form')!);
    });

    expect(onClose).not.toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(800);
    });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('shows error banner when isError is true', () => {
    renderWithProviders(<TestFormModal isError={true} />);
    expect(screen.getByText('Save failed. Please try again.')).toBeTruthy();
  });

  it('keeps modal open on submit error (onSubmit throws)', async () => {
    const onClose = vi.fn();
    const onSubmit = vi.fn().mockRejectedValue(new Error('fail'));
    renderWithProviders(<TestFormModal onClose={onClose} onSubmit={onSubmit} />);

    await act(async () => {
      fireEvent.submit(screen.getByRole('button', { name: /save/i }).closest('form')!);
    });

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(onClose).not.toHaveBeenCalled();
  });

  it('resets form to defaultValues when isOpen flips from false to true', () => {
    vi.useRealTimers(); // avoid waitFor interaction with fake timers
    const { rerender } = renderWithProviders(
      <TestFormModal isOpen={true} initialName="initial" />
    );

    const input = () => screen.getByTestId('name-input') as HTMLInputElement;
    expect(input().value).toBe('initial');

    // Mutate the field
    fireEvent.change(input(), { target: { value: 'changed' } });
    expect(input().value).toBe('changed');

    // Close
    act(() => {
      rerender(<TestFormModal isOpen={false} initialName="initial" />);
    });

    // Re-open — the useEffect on isOpen should reset the form
    act(() => {
      rerender(<TestFormModal isOpen={true} initialName="initial" />);
    });

    expect(input().value).toBe('initial');
  });

  it('resets to latest defaultValues only on closed→open transition, not on repeated opens', () => {
    vi.useRealTimers();
    const { rerender } = renderWithProviders(
      <TestFormModal isOpen={false} initialName="v1" />
    );

    // First open: form seeds from defaultValues
    act(() => {
      rerender(<TestFormModal isOpen={true} initialName="v1" />);
    });

    const input = () => screen.getByTestId('name-input') as HTMLInputElement;
    expect(input().value).toBe('v1');

    // Mutate, then re-open (closed → open flip again)
    fireEvent.change(input(), { target: { value: 'user-typed' } });
    act(() => { rerender(<TestFormModal isOpen={false} initialName="v1" />); });
    act(() => { rerender(<TestFormModal isOpen={true} initialName="updated" />); });

    // Second open resets to the latest defaultValues
    expect(input().value).toBe('updated');
  });

  it('disables submit button while isPending (shows Loading... text)', () => {
    renderWithProviders(<TestFormModal isPending={true} />);
    const loadingBtn = screen.getByRole('button', { name: /loading/i });
    expect(loadingBtn).toBeDisabled();
  });
});
