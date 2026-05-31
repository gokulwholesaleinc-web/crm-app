import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import type { ComponentProps } from 'react';
import { renderWithProviders, screen, fireEvent, waitFor } from '../../test-utils/renderWithProviders';
import { server } from '../../test-setup';
import { useAuthStore, type User } from '../../store/authStore';
import { ProposalForm } from './ProposalForm';
import { writeProposalDraft } from './proposalDrafts';

const TEST_USER: User = {
  id: 7,
  email: 'sales@example.com',
  full_name: 'Sales User',
  is_active: true,
  is_superuser: false,
  role: 'sales_rep',
  created_at: '2026-05-18T00:00:00.000Z',
};

const CREATE_DRAFT_KEY = 'crm_proposal_draft:7:create:new:v2';

const baseProps = {
  onSubmit: vi.fn(),
  onCancel: vi.fn(),
};

let storage: Map<string, string>;

function installMemoryStorage() {
  storage = new Map();
  const memoryStorage = {
    get length() {
      return storage.size;
    },
    clear: () => storage.clear(),
    getItem: (key: string) => storage.get(key) ?? null,
    key: (index: number) => Array.from(storage.keys())[index] ?? null,
    removeItem: (key: string) => {
      storage.delete(key);
    },
    setItem: (key: string, value: string) => {
      storage.set(key, String(value));
    },
  };
  Object.defineProperty(window, 'localStorage', {
    configurable: true,
    writable: true,
    value: memoryStorage,
  });
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    writable: true,
    value: memoryStorage,
  });
}

function installEntityHandlers() {
  server.use(
    http.get(/\/api\/contacts(?:\?.*)?$/, () =>
      HttpResponse.json({
        items: [{ id: 1, full_name: 'Jane Buyer' }],
        total: 1,
        page: 1,
        page_size: 100,
        pages: 1,
      }),
    ),
    http.get(/\/api\/companies(?:\?.*)?$/, () =>
      HttpResponse.json({
        items: [{ id: 2, name: 'Acme Co' }],
        total: 1,
        page: 1,
        page_size: 100,
        pages: 1,
      }),
    ),
  );
}

function renderCreateForm(props: Partial<ComponentProps<typeof ProposalForm>> = {}) {
  return renderWithProviders(
    <ProposalForm {...baseProps} {...props} />,
    { initialRoute: '/proposals?action=new&contact_id=1' },
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  installMemoryStorage();
  installEntityHandlers();
  act(() => {
    useAuthStore.setState({
      user: TEST_USER,
      token: 'token',
      isAuthenticated: true,
      isLoading: false,
    });
  });
});

afterEach(() => {
  vi.useRealTimers();
  useAuthStore.setState({
    user: null,
    token: null,
    isAuthenticated: false,
    isLoading: false,
  });
});

describe('ProposalForm local drafts', () => {
  it('autosaves create fields to a per-user local draft', () => {
    vi.useFakeTimers();
    renderCreateForm();

    fireEvent.change(screen.getByLabelText(/Title/i), {
      target: { value: 'Website redesign proposal' },
    });
    fireEvent.change(screen.getByLabelText(/Pricing Notes/i), {
      target: { value: 'Package options and assumptions' },
    });

    act(() => {
      vi.advanceTimersByTime(600);
    });

    const saved = JSON.parse(window.localStorage.getItem(CREATE_DRAFT_KEY) ?? 'null');
    expect(saved).toMatchObject({
      version: 2,
      mode: 'create',
      proposalId: null,
      value: {
        formData: {
          title: 'Website redesign proposal',
          contactId: 1,
          pricingSection: 'Package options and assumptions',
        },
      },
    });
  });

  it('prompts before restoring a saved create draft', async () => {
    writeProposalDraft(CREATE_DRAFT_KEY, 'create', null, {
      formData: {
        title: 'Recovered proposal',
        content: 'Saved body',
        contactId: 1,
        companyId: null,
        executiveSummary: '',
        scopeOfWork: '',
        pricingSection: '',
        timelineField: '',
        terms: '',
        validUntil: '',
      },
    });

    renderCreateForm();

    expect(await screen.findByText(/Unsaved proposal draft found/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /Resume/i }));

    expect(screen.getByLabelText(/Title/i)).toHaveValue('Recovered proposal');
    expect(screen.getByLabelText(/Content/i)).toHaveValue('Saved body');
  });

  it('does not render the signing-documents picker in the create modal', () => {
    renderCreateForm();
    expect(screen.queryByRole('button', { name: /Choose signing PDFs/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/PDFs ready to upload/i)).not.toBeInTheDocument();
  });

  it('starts fresh when editing before resolving a saved draft prompt', () => {
    vi.useFakeTimers();
    writeProposalDraft(CREATE_DRAFT_KEY, 'create', null, {
      formData: {
        title: 'Recovered proposal',
        content: 'Saved body',
        contactId: 1,
        companyId: null,
        executiveSummary: '',
        scopeOfWork: '',
        pricingSection: '',
        timelineField: '',
        terms: '',
        validUntil: '',
      },
    });

    renderCreateForm();
    expect(screen.getByText(/Unsaved proposal draft found/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Title/i), {
      target: { value: 'Fresh proposal' },
    });
    act(() => {
      vi.advanceTimersByTime(600);
    });

    expect(screen.queryByText(/Unsaved proposal draft found/i)).not.toBeInTheDocument();
    const saved = JSON.parse(window.localStorage.getItem(CREATE_DRAFT_KEY) ?? 'null');
    expect(saved.value.formData.title).toBe('Fresh proposal');
    expect(saved.value.pendingSigningDocNames).toBeUndefined();
  });

  it('does not show a saved timestamp when browser storage rejects writes', () => {
    vi.useFakeTimers();
    const originalSetItem = window.localStorage.setItem;
    Object.defineProperty(window.localStorage, 'setItem', {
      configurable: true,
      value: () => {
        throw new Error('blocked');
      },
    });

    renderCreateForm();

    fireEvent.change(screen.getByLabelText(/Title/i), {
      target: { value: 'Storage blocked proposal' },
    });
    act(() => {
      vi.advanceTimersByTime(600);
    });

    expect(screen.queryByText(/Draft saved locally/i)).not.toBeInTheDocument();
    expect(screen.getByText(/browser blocked local autosave/i)).toBeInTheDocument();

    Object.defineProperty(window.localStorage, 'setItem', {
      configurable: true,
      value: originalSetItem,
    });
  });

  it('signals when another tab updates the same draft key', () => {
    renderCreateForm();

    act(() => {
      window.dispatchEvent(
        new StorageEvent('storage', {
          key: CREATE_DRAFT_KEY,
          oldValue: null,
          newValue: '{"version":2}',
        }),
      );
    });

    expect(screen.getByText(/Another tab updated this draft/i)).toBeInTheDocument();
  });

  it('shows autosave initialization while auth is rehydrating', () => {
    act(() => {
      useAuthStore.setState({
        user: null,
        token: null,
        isAuthenticated: false,
        isLoading: true,
      });
    });

    renderCreateForm();

    expect(screen.getByText(/Autosave initializing/i)).toBeInTheDocument();
  });

  it('purges proposal drafts on logout', () => {
    writeProposalDraft(CREATE_DRAFT_KEY, 'create', null, {
      formData: {
        title: 'Confidential proposal',
        content: '',
        contactId: 1,
        companyId: null,
        executiveSummary: '',
        scopeOfWork: '',
        pricingSection: '',
        timelineField: '',
        terms: '',
        validUntil: '',
      },
    });
    window.localStorage.setItem('unrelated-key', 'keep');

    act(() => {
      useAuthStore.getState().logout();
    });

    expect(window.localStorage.getItem(CREATE_DRAFT_KEY)).toBeNull();
    expect(window.localStorage.getItem('unrelated-key')).toBe('keep');
  });

  it('clears the local draft after successful submit', async () => {
    vi.useFakeTimers();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderCreateForm({ onSubmit });

    fireEvent.change(screen.getByLabelText(/Title/i), {
      target: { value: 'Proposal to save' },
    });
    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(window.localStorage.getItem(CREATE_DRAFT_KEY)).not.toBeNull();

    vi.useRealTimers();
    fireEvent.click(screen.getByRole('button', { name: /Create Proposal/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());
    expect(window.localStorage.getItem(CREATE_DRAFT_KEY)).toBeNull();
  });

  it('keeps the local draft when submit fails', async () => {
    vi.useFakeTimers();
    const onSubmit = vi.fn().mockRejectedValue(new Error('network down'));
    renderCreateForm({ onSubmit });

    fireEvent.change(screen.getByLabelText(/Title/i), {
      target: { value: 'Do not lose me' },
    });
    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(window.localStorage.getItem(CREATE_DRAFT_KEY)).not.toBeNull();

    vi.useRealTimers();
    fireEvent.click(screen.getByRole('button', { name: /Create Proposal/i }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledOnce());
    expect(window.localStorage.getItem(CREATE_DRAFT_KEY)).not.toBeNull();
  });

  it('disables fields while submit is pending to avoid in-flight draft loss', async () => {
    vi.useFakeTimers();
    let resolveSubmit!: () => void;
    const onSubmit = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveSubmit = resolve;
        }),
    );
    renderCreateForm({ onSubmit });

    fireEvent.change(screen.getByLabelText(/Title/i), {
      target: { value: 'Submitted title' },
    });
    act(() => {
      vi.advanceTimersByTime(600);
    });
    expect(window.localStorage.getItem(CREATE_DRAFT_KEY)).toContain('Submitted title');

    const titleInput = screen.getByLabelText(/Title/i);
    fireEvent.click(screen.getByRole('button', { name: /Create Proposal/i }));
    expect(titleInput).toBeDisabled();
    act(() => {
      vi.advanceTimersByTime(600);
    });

    expect(window.localStorage.getItem(CREATE_DRAFT_KEY)).toContain('Submitted title');

    act(() => {
      resolveSubmit();
    });
    vi.useRealTimers();

    await waitFor(() => expect(window.localStorage.getItem(CREATE_DRAFT_KEY)).toBeNull());
  });

  it('does not restore a create draft into edit mode', () => {
    writeProposalDraft(CREATE_DRAFT_KEY, 'create', null, {
      formData: {
        title: 'Wrong draft',
        content: '',
        contactId: null,
        companyId: null,
        executiveSummary: '',
        scopeOfWork: '',
        pricingSection: '',
        timelineField: '',
        terms: '',
        validUntil: '',
      },
    });

    renderWithProviders(
      <ProposalForm
        {...baseProps}
        proposalId={42}
        initialData={{
          title: 'Server proposal',
          contact_id: 1,
        }}
      />,
    );

    expect(screen.queryByText(/Unsaved edit draft found/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Title/i)).toHaveValue('Server proposal');
  });
});
