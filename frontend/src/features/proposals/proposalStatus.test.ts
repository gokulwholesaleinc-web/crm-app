import { describe, expect, it, vi } from 'vitest';
import type { Proposal } from '../../types';
import {
  buildProposalSendChecklist,
  hasPackageSendBlocker,
  hasSigningDocumentSendBlocker,
} from './proposalStatus';

const baseProposal = {
  id: 1,
  proposal_number: 'PR-2026-0001',
  title: 'Test proposal',
  status: 'draft',
  view_count: 0,
  payment_type: 'one_time',
  currency: 'USD',
  created_at: '2026-05-18T00:00:00Z',
  updated_at: '2026-05-18T00:00:00Z',
  contact: { id: 1, full_name: 'Buyer', email: 'buyer@example.com' },
  company: { id: 1, name: 'Buyer Co' },
} as Proposal;

describe('proposal signing document send guardrails', () => {
  it('does not block proposals with no signing documents', () => {
    expect(hasSigningDocumentSendBlocker(baseProposal)).toBe(false);
  });

  it('blocks when any uploaded signing document has no placement', () => {
    const proposal = {
      ...baseProposal,
      signing_documents: [
        {
          id: 10,
          proposal_id: 1,
          original_filename: 'MSA.pdf',
          file_size: 1000,
          content_type: 'application/pdf',
          signature_field_coords: null,
          date_field_coords: null,
          display_order: 0,
          created_at: '2026-05-18T00:00:00Z',
          updated_at: '2026-05-18T00:00:00Z',
        },
      ],
    } as Proposal;

    expect(hasSigningDocumentSendBlocker(proposal)).toBe(true);
    const onManageSigningDocuments = vi.fn();
    const checklist = buildProposalSendChecklist(proposal, {
      onEditContact: vi.fn(),
      onManageSigningDocuments,
    });
    const item = checklist.find((entry) => entry.key === 'signing_documents');

    expect(item?.state).toBe(false);
    expect(item?.hint).toContain('MSA.pdf');
    item?.action?.onClick();
    expect(onManageSigningDocuments).toHaveBeenCalledTimes(1);
  });

  it('allows send when every signing document has signature and date placement', () => {
    const proposal = {
      ...baseProposal,
      signing_documents: [
        {
          id: 10,
          proposal_id: 1,
          original_filename: 'MSA.pdf',
          file_size: 1000,
          content_type: 'application/pdf',
          signature_field_coords: { page: 1, x: 10, y: 10, w: 100, h: 40 },
          date_field_coords: { page: 1, x: 130, y: 10, w: 80, h: 24 },
          display_order: 0,
          created_at: '2026-05-18T00:00:00Z',
          updated_at: '2026-05-18T00:00:00Z',
        },
      ],
    } as Proposal;

    expect(hasSigningDocumentSendBlocker(proposal)).toBe(false);
    const checklist = buildProposalSendChecklist(proposal, {
      onEditContact: vi.fn(),
    });
    const item = checklist.find((entry) => entry.key === 'signing_documents');

    expect(item?.state).toBe(true);
    expect(item?.label).toContain('Signature and date areas placed');
  });

  it('allows multiple placements but treats empty placement arrays as missing', () => {
    const readyProposal = {
      ...baseProposal,
      signing_documents: [
        {
          id: 10,
          proposal_id: 1,
          original_filename: 'MSA.pdf',
          file_size: 1000,
          content_type: 'application/pdf',
          signature_field_coords: [
            { page: 1, x: 10, y: 10, w: 100, h: 40 },
            { page: 1, x: 10, y: 80, w: 100, h: 40 },
          ],
          date_field_coords: [
            { page: 1, x: 130, y: 10, w: 80, h: 24 },
            { page: 1, x: 130, y: 80, w: 80, h: 24 },
          ],
          display_order: 0,
          created_at: '2026-05-18T00:00:00Z',
          updated_at: '2026-05-18T00:00:00Z',
        },
      ],
    } as Proposal;
    const emptyProposal = {
      ...readyProposal,
      signing_documents: [
        {
          ...readyProposal.signing_documents![0],
          signature_field_coords: [],
          date_field_coords: [],
        },
      ],
    } as Proposal;

    expect(hasSigningDocumentSendBlocker(readyProposal)).toBe(false);
    expect(hasSigningDocumentSendBlocker(emptyProposal)).toBe(true);
  });
});

describe('proposal package send guardrails', () => {
  it('does not block text-only proposals with no package rows', () => {
    const checklist = buildProposalSendChecklist(baseProposal, {
      onEditContact: vi.fn(),
    });

    expect(hasPackageSendBlocker(baseProposal)).toBe(false);
    expect(checklist.some((item) => item.key.startsWith('proposal_packages_'))).toBe(false);
  });

  it('blocks proposals that have package rows but zero active packages', () => {
    const proposal = {
      ...baseProposal,
      packages: [
        {
          id: 10,
          proposal_id: 1,
          name: 'Old option',
          description: null,
          currency: 'USD',
          payment_type: 'one_time',
          recurring_interval: null,
          recurring_interval_count: null,
          subtotal: '1000.00',
          discount_amount: '0.00',
          tax_amount: '0.00',
          total: '1000.00',
          sort_order: 0,
          is_recommended: false,
          is_active: false,
          items: [],
        },
      ],
    } as Proposal;

    expect(hasPackageSendBlocker(proposal)).toBe(true);
    const checklist = buildProposalSendChecklist(proposal, {
      onEditContact: vi.fn(),
    });
    expect(checklist.find((item) => item.key === 'proposal_packages_active')?.state).toBe(false);
  });

  it('passes valid active packages and catches mixed currencies', () => {
    const readyPackage = {
      id: 10,
      proposal_id: 1,
      name: 'Starter',
      description: null,
      currency: 'USD',
      payment_type: 'one_time',
      recurring_interval: null,
      recurring_interval_count: null,
      subtotal: '1000.00',
      discount_amount: '0.00',
      tax_amount: '0.00',
      total: '1000.00',
      sort_order: 0,
      is_recommended: true,
      is_active: true,
      items: [
        {
          id: 100,
          package_id: 10,
          description: 'Implementation',
          quantity: '1.00',
          unit_price: '1000.00',
          discount_amount: '0.00',
          total: '1000.00',
          sort_order: 0,
        },
      ],
    };
    const readyProposal = {
      ...baseProposal,
      packages: [readyPackage],
    } as Proposal;
    const mixedCurrencyProposal = {
      ...baseProposal,
      packages: [
        readyPackage,
        {
          ...readyPackage,
          id: 11,
          currency: 'EUR',
          is_recommended: false,
        },
      ],
    } as Proposal;

    expect(hasPackageSendBlocker(readyProposal)).toBe(false);
    expect(hasPackageSendBlocker(mixedCurrencyProposal)).toBe(true);
    const checklist = buildProposalSendChecklist(mixedCurrencyProposal, {
      onEditContact: vi.fn(),
    });
    expect(checklist.find((item) => item.key === 'proposal_packages_currency')?.state).toBe(false);
  });
});
