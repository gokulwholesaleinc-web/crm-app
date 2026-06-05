/**
 * Tests for the shared AttachmentList "View" action: a View button appears only
 * for browser-viewable types (PDF / raster image) and opens the file via
 * viewAttachmentFile; a non-viewable type only offers Download.
 *
 * The api/attachments wrappers and the useAttachments react-query hooks are
 * mocked so the component's real render/branch logic runs against fixtures.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  renderWithProviders,
  screen,
  fireEvent,
  waitFor,
} from '../../test-utils/renderWithProviders';
import type { AttachmentResponse } from '../../api/attachments';

const apiMock = vi.hoisted(() => ({
  downloadAttachmentFile: vi.fn(),
  viewAttachmentFile: vi.fn(),
}));
vi.mock('../../api/attachments', () => apiMock);
vi.mock('../../utils/toast', () => ({ showSuccess: vi.fn(), showError: vi.fn() }));

const hooksMock = vi.hoisted(() => ({
  useAttachments: vi.fn(),
  useUploadAttachment: vi.fn(),
  useDeleteAttachment: vi.fn(),
}));
vi.mock('../../hooks/useAttachments', () => hooksMock);

import { AttachmentList } from './AttachmentList';

function attachment(over: Partial<AttachmentResponse> = {}): AttachmentResponse {
  return {
    id: 1,
    filename: 'stored',
    original_filename: 'Doc.pdf',
    file_size: 1024,
    mime_type: 'application/pdf',
    entity_type: 'contacts',
    entity_id: 5,
    category: null,
    uploaded_by: null,
    created_at: '2026-06-04T00:00:00Z',
    ...over,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  hooksMock.useUploadAttachment.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
  hooksMock.useDeleteAttachment.mockReturnValue({ mutateAsync: vi.fn(), isPending: false });
});

describe('AttachmentList View action', () => {
  it('shows a View button for a PDF and opens it via viewAttachmentFile', async () => {
    hooksMock.useAttachments.mockReturnValue({
      data: {
        items: [attachment({ id: 10, original_filename: 'Report.pdf', mime_type: 'application/pdf' })],
      },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<AttachmentList entityType="contacts" entityId={5} />);

    const viewBtn = await screen.findByRole('button', { name: 'View Report.pdf' });
    fireEvent.click(viewBtn);
    await waitFor(() => expect(apiMock.viewAttachmentFile).toHaveBeenCalledWith(10));
    expect(apiMock.downloadAttachmentFile).not.toHaveBeenCalled();
  });

  it('hides the View button for a non-viewable type but still offers Download', async () => {
    hooksMock.useAttachments.mockReturnValue({
      data: {
        items: [
          attachment({
            id: 11,
            original_filename: 'Sheet.xlsx',
            mime_type:
              'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          }),
        ],
      },
      isLoading: false,
      error: null,
    });

    renderWithProviders(<AttachmentList entityType="contacts" entityId={5} />);

    await screen.findByText('Sheet.xlsx');
    expect(
      screen.queryByRole('button', { name: 'View Sheet.xlsx' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Download Sheet.xlsx' }),
    ).toBeInTheDocument();
  });
});
