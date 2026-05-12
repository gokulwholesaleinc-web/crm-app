import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

const { mockGet, mockPost, mockPublicClient } = vi.hoisted(() => {
  const mockGet = vi.fn();
  const mockPost = vi.fn();
  return { mockGet, mockPost, mockPublicClient: { get: mockGet, post: mockPost } };
});

vi.mock('axios', () => ({
  default: { create: vi.fn(() => mockPublicClient) },
}));

import PublicContractView from './PublicContractView';

function renderAt(token = 'tok-abc123') {
  return render(
    <MemoryRouter initialEntries={[`/contracts/public/${token}`]}>
      <Routes>
        <Route path="/contracts/public/:token" element={<PublicContractView />} />
      </Routes>
    </MemoryRouter>
  );
}

const baseContract = {
  id: 1,
  title: 'Service Agreement',
  scope: null,
  value: null,
  currency: 'USD',
  start_date: null,
  end_date: null,
  status: 'sent',
  company_name: 'Acme Corp',
  contact_name: 'Jane Doe',
  signer_email: 'jane@acme.com',
  expires_at: null,
  signed_at: null,
  signed_by_name: null,
  branding: {
    company_name: 'Acme Corp',
    logo_url: null,
    primary_color: '#6366f1',
    secondary_color: '#8b5cf6',
    accent_color: '#22c55e',
    bg_color_light: '#f9fafb',
    surface_color_light: '#ffffff',
    footer_text: null,
    privacy_policy_url: null,
    terms_of_service_url: null,
  },
};

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
});

describe('PublicContractView', () => {
  it('shows loading state initially before GET resolves', () => {
    mockGet.mockReturnValue(new Promise(() => {}));
    renderAt();
    expect(screen.queryByText('Service Agreement')).not.toBeInTheDocument();
  });

  it('renders contract title and contact on successful GET', async () => {
    mockGet.mockResolvedValue({ data: baseContract });
    renderAt();
    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 1, name: 'Service Agreement' })).toBeInTheDocument()
    );
    // "Prepared for Jane Doe" uses role="doc-subtitle" and aria-label="Recipient"
    expect(screen.getByRole('doc-subtitle', { name: 'Recipient' })).toBeInTheDocument();
    expect(screen.getByRole('doc-subtitle', { name: 'Recipient' }).textContent).toContain('Jane Doe');
  });

  it('renders error state when GET fails', async () => {
    mockGet.mockRejectedValue(new Error('Network Error'));
    renderAt();
    await waitFor(() =>
      expect(screen.getByText('Contract not found or this signing link is no longer valid.')).toBeInTheDocument()
    );
  });

  it('shows sign form when status is sent', async () => {
    mockGet.mockResolvedValue({ data: baseContract });
    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));
    expect(screen.getByLabelText('Full name')).toBeInTheDocument();
    expect(screen.getByLabelText('Signature pad — draw your signature')).toBeInTheDocument();
  });

  it('shows already-signed state when contract is already signed', async () => {
    mockGet.mockResolvedValue({
      data: { ...baseContract, status: 'signed', signed_at: '2026-01-01T00:00:00Z', signed_by_name: 'Jane Doe' },
    });
    renderAt();
    await waitFor(() =>
      expect(screen.getByText('Contract signed')).toBeInTheDocument()
    );
    expect(screen.queryByLabelText('Full name')).not.toBeInTheDocument();
  });

  it('shows expired notice when contract expires_at is in the past', async () => {
    mockGet.mockResolvedValue({
      data: { ...baseContract, expires_at: '2020-01-01T00:00:00Z' },
    });
    renderAt();
    await waitFor(() =>
      expect(screen.getByText(/This signing link has expired/)).toBeInTheDocument()
    );
    expect(screen.queryByLabelText('Full name')).not.toBeInTheDocument();
  });

  it('shows validation error when name is empty on submit', async () => {
    mockGet.mockResolvedValue({ data: baseContract });
    renderAt();
    await waitFor(() => screen.getByRole('button', { name: /Sign Contract/ }));

    // Check agree checkbox to enable button
    fireEvent.click(screen.getByLabelText('I have read and agree to the terms and conditions above'));
    fireEvent.click(screen.getByRole('button', { name: /Sign Contract/ }));

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent('Please enter your full name.')
    );
    expect(mockPost).not.toHaveBeenCalled();
  });

  it('shows success banner after signing', async () => {
    mockGet.mockResolvedValue({ data: baseContract });
    mockPost.mockResolvedValue({});
    renderAt();
    await waitFor(() => screen.getByLabelText('Full name'));

    fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Jane Doe' } });
    fireEvent.click(screen.getByLabelText('I have read and agree to the terms and conditions above'));

    // Can't draw on canvas in jsdom — mock isCanvasEmpty to return false
    const canvas = screen.getByLabelText('Signature pad — draw your signature') as HTMLCanvasElement;
    vi.spyOn(canvas, 'toDataURL').mockReturnValue('data:image/png;base64,abc');
    const ctx = { getImageData: vi.fn(() => ({ data: new Uint8ClampedArray([0, 0, 0, 255]) })) } as unknown as CanvasRenderingContext2D;
    vi.spyOn(canvas, 'getContext').mockReturnValue(ctx);

    fireEvent.click(screen.getByRole('button', { name: /Sign Contract/ }));

    await waitFor(() =>
      expect(screen.getByText('Contract signed — thank you')).toBeInTheDocument()
    );
  });

  it('has role="doc-subtitle" with aria-label="Recipient" on prepared-for line', async () => {
    mockGet.mockResolvedValue({ data: baseContract });
    renderAt();
    await waitFor(() => screen.getByRole('heading', { level: 1 }));
    const subtitle = document.querySelector('[role="doc-subtitle"]');
    expect(subtitle).toBeTruthy();
    expect(subtitle?.getAttribute('aria-label')).toBe('Recipient');
  });
});
