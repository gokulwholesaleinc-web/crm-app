import { describe, expect, it, vi } from 'vitest';
import type { Proposal } from '../../types';
import {
  buildProposalSendChecklist,
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

  it('allows send when every signing document has placement', () => {
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
    expect(item?.label).toContain('Signing areas placed');
  });
});
