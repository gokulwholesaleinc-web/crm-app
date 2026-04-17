import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useState } from 'react';
import { renderWithProviders, screen, waitFor, fireEvent } from '../../test-utils/renderWithProviders';
import { EmailComposeModal } from './EmailComposeModal';
import type { ThreadEmailItem } from '../../types/email';

const mutateAsync = vi.fn();
let mockIsPending = false;

vi.mock('../../hooks/useEmail', () => ({
  useSendEmail: () => ({
    mutateAsync,
    isPending: mockIsPending,
  }),
}));

const BASE_PROPS = {
  isOpen: true,
  onClose: vi.fn(),
};

const REPLY_TO: ThreadEmailItem = {
  id: 1,
  direction: 'inbound',
  from_email: 'sender@example.com',
  to_email: 'me@example.com',
  cc: 'cc@example.com',
  subject: 'Hello World',
  body: 'Test body',
  body_html: null,
  timestamp: '2026-01-01T00:00:00Z',
  status: null,
  open_count: null,
  attachments: null,
  thread_id: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockIsPending = false;
});

describe('EmailComposeModal', () => {
  it('renders "Compose Email" title in compose mode and "Reply to Email" in reply mode', () => {
    const { unmount } = renderWithProviders(<EmailComposeModal {...BASE_PROPS} />);
    expect(screen.getByText('Compose Email')).toBeInTheDocument();
    unmount();

    renderWithProviders(<EmailComposeModal {...BASE_PROPS} replyTo={REPLY_TO} />);
    expect(screen.getByText('Reply to Email')).toBeInTheDocument();
  });

  it('pre-fills the To field from defaultTo in compose mode', () => {
    renderWithProviders(
      <EmailComposeModal {...BASE_PROPS} defaultTo="default@example.com" />
    );
    expect(screen.getByLabelText('To')).toHaveValue('default@example.com');
  });

  it('reply mode pre-fills To, Subject with Re: prefix, CC, and shows CC/BCC fields', () => {
    renderWithProviders(<EmailComposeModal {...BASE_PROPS} replyTo={REPLY_TO} />);

    expect(screen.getByLabelText('To')).toHaveValue('sender@example.com');
    expect(screen.getByLabelText('Subject')).toHaveValue('Re: Hello World');
    expect(screen.getByLabelText('CC')).toHaveValue('cc@example.com');
    expect(screen.getByLabelText('BCC')).toBeInTheDocument();
  });

  it('does not double-prefix subject if already starts with "Re: "', () => {
    const alreadyPrefixed: ThreadEmailItem = { ...REPLY_TO, subject: 'Re: Hello World' };
    renderWithProviders(<EmailComposeModal {...BASE_PROPS} replyTo={alreadyPrefixed} />);
    expect(screen.getByLabelText('Subject')).toHaveValue('Re: Hello World');
  });

  it('submitting with valid fields calls mutateAsync with correct payload and closes on success', async () => {
    mutateAsync.mockResolvedValueOnce({});
    const onClose = vi.fn();

    renderWithProviders(
      <EmailComposeModal
        {...BASE_PROPS}
        onClose={onClose}
        defaultTo="to@example.com"
        entityType="contact"
        entityId={42}
        fromEmail="from@example.com"
      />
    );

    fireEvent.change(screen.getByLabelText('Subject'), { target: { value: 'Test Subject' } });
    fireEvent.change(screen.getByLabelText('Body'), { target: { value: 'Test body text' } });
    fireEvent.submit(screen.getByLabelText('Subject').closest('form')!);

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        to_email: 'to@example.com',
        subject: 'Test Subject',
        body: 'Test body text',
        from_email: 'from@example.com',
        cc: undefined,
        bcc: undefined,
        entity_type: 'contact',
        entity_id: 42,
      });
      expect(onClose).toHaveBeenCalledOnce();
    });
  });

  it('shows loading state on Send button when mutation is pending', () => {
    mockIsPending = true;

    renderWithProviders(<EmailComposeModal {...BASE_PROPS} />);

    const submitButton = screen.getByText('Loading...').closest('button');
    expect(submitButton).toBeDisabled();
  });

  it('does NOT close modal when mutation rejects', async () => {
    mutateAsync.mockRejectedValueOnce(new Error('Send failed'));
    const onClose = vi.fn();

    renderWithProviders(
      <EmailComposeModal
        {...BASE_PROPS}
        onClose={onClose}
        defaultTo="to@example.com"
      />
    );

    fireEvent.change(screen.getByLabelText('Subject'), { target: { value: 'Subject' } });
    fireEvent.change(screen.getByLabelText('Body'), { target: { value: 'Body' } });
    fireEvent.submit(screen.getByLabelText('Subject').closest('form')!);

    await waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(onClose).not.toHaveBeenCalled();
  });

  it('"Add CC / BCC" toggle reveals cc and bcc inputs when clicked', () => {
    renderWithProviders(<EmailComposeModal {...BASE_PROPS} />);

    expect(screen.queryByLabelText('CC')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('BCC')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Add CC / BCC'));

    expect(screen.getByLabelText('CC')).toBeInTheDocument();
    expect(screen.getByLabelText('BCC')).toBeInTheDocument();
  });

  it('preserves in-progress edits when parent re-renders with a new defaultTo', () => {
    function Harness() {
      const [defaultTo, setDefaultTo] = useState('first@example.com');
      return (
        <>
          <button type="button" onClick={() => setDefaultTo('second@example.com')}>
            change-default
          </button>
          <EmailComposeModal {...BASE_PROPS} defaultTo={defaultTo} />
        </>
      );
    }

    renderWithProviders(<Harness />);

    fireEvent.change(screen.getByLabelText('Subject'), { target: { value: 'Draft subject' } });
    fireEvent.change(screen.getByLabelText('Body'), { target: { value: 'Draft body text' } });

    fireEvent.click(screen.getByText('change-default'));

    expect(screen.getByLabelText('Subject')).toHaveValue('Draft subject');
    expect(screen.getByLabelText('Body')).toHaveValue('Draft body text');
  });
});
