import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, fireEvent, waitFor, act } from '../../test-utils/renderWithProviders';
import { InlineSectionEditor } from './InlineSectionEditor';

function renderEditor(overrides: Partial<Parameters<typeof InlineSectionEditor>[0]> = {}) {
  const defaultProps = {
    title: 'Executive Summary',
    value: 'Initial content',
    onSave: vi.fn().mockResolvedValue(undefined),
    canEdit: true,
    ...overrides,
  };
  return { ...renderWithProviders(<InlineSectionEditor {...defaultProps} />), props: defaultProps };
}

describe('InlineSectionEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders title and value in read mode', () => {
    renderEditor();
    expect(screen.getByText('Executive Summary')).toBeTruthy();
    expect(screen.getByText('Initial content')).toBeTruthy();
  });

  it('does not render pencil button when canEdit is false', () => {
    renderEditor({ canEdit: false });
    expect(screen.queryByRole('button', { name: /edit executive summary/i })).toBeNull();
  });

  it('renders pencil button when canEdit is true', () => {
    renderEditor();
    expect(screen.getByRole('button', { name: /edit executive summary/i })).toBeTruthy();
  });

  it('clicking pencil enters edit mode with textarea populated', async () => {
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: /edit executive summary/i }));
    const textarea = screen.getByRole('textbox') as HTMLTextAreaElement;
    expect(textarea).toBeTruthy();
    expect(textarea.value).toBe('Initial content');
  });

  it('typing new value and clicking Save calls onSave with trimmed value', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderEditor({ onSave });
    fireEvent.click(screen.getByRole('button', { name: /edit executive summary/i }));
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: '  New content  ' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    });
    await waitFor(() => expect(onSave).toHaveBeenCalledWith('New content'));
  });

  it('clicking Cancel reverts to read mode with original value preserved', () => {
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: /edit executive summary/i }));
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Changed content' } });
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(screen.getByText('Initial content')).toBeTruthy();
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('pressing Esc in textarea cancels edit mode', () => {
    renderEditor();
    fireEvent.click(screen.getByRole('button', { name: /edit executive summary/i }));
    const textarea = screen.getByRole('textbox');
    fireEvent.keyDown(textarea, { key: 'Escape' });
    expect(screen.queryByRole('textbox')).toBeNull();
    expect(screen.getByText('Initial content')).toBeTruthy();
  });

  it('pressing Cmd+Enter in textarea triggers save', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderEditor({ onSave });
    fireEvent.click(screen.getByRole('button', { name: /edit executive summary/i }));
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Keyboard saved content' } });
    await act(async () => {
      fireEvent.keyDown(textarea, { key: 'Enter', metaKey: true });
    });
    await waitFor(() => expect(onSave).toHaveBeenCalledWith('Keyboard saved content'));
  });

  it('pressing Ctrl+Enter in textarea triggers save', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderEditor({ onSave });
    fireEvent.click(screen.getByRole('button', { name: /edit executive summary/i }));
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Ctrl saved content' } });
    await act(async () => {
      fireEvent.keyDown(textarea, { key: 'Enter', ctrlKey: true });
    });
    await waitFor(() => expect(onSave).toHaveBeenCalledWith('Ctrl saved content'));
  });

  it('saving an unchanged value does not call onSave', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderEditor({ value: 'Same content', onSave });
    fireEvent.click(screen.getByRole('button', { name: /edit executive summary/i }));
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    });
    expect(onSave).not.toHaveBeenCalled();
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('save error surfaces inline and stays in edit mode', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('Network failure'));
    renderEditor({ onSave });
    fireEvent.click(screen.getByRole('button', { name: /edit executive summary/i }));
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: 'Changed value' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    });
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy());
    expect(screen.getByText('Network failure')).toBeTruthy();
    expect(screen.getByRole('textbox')).toBeTruthy();
  });

  it('shows Add affordance when value is null/empty and canEdit is true', () => {
    renderEditor({ value: null });
    const addButton = screen.getByRole('button', { name: /add executive summary/i });
    expect(addButton).toBeTruthy();
    expect(screen.getByText(/add executive summary\.\.\./i)).toBeTruthy();
  });

  it('Add affordance click enters edit mode', () => {
    renderEditor({ value: null });
    fireEvent.click(screen.getByRole('button', { name: /add executive summary/i }));
    expect(screen.getByRole('textbox')).toBeTruthy();
  });

  it('does not show Add affordance when canEdit is false and value is empty', () => {
    renderEditor({ value: null, canEdit: false });
    expect(screen.queryByRole('button', { name: /add executive summary/i })).toBeNull();
  });

  it('saving empty value emits null to onSave', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    renderEditor({ value: 'Some content', onSave });
    fireEvent.click(screen.getByRole('button', { name: /edit executive summary/i }));
    const textarea = screen.getByRole('textbox');
    fireEvent.change(textarea, { target: { value: '   ' } });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    });
    await waitFor(() => expect(onSave).toHaveBeenCalledWith(null));
  });
});
