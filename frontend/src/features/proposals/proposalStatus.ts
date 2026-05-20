/**
 * Proposal-flow helpers shared by ProposalDetail to keep the detail page
 * focused on rendering. Builds the StatusTimeline steps + SendChecklist
 * items + primary-action selection from a Proposal record.
 */

import type { Proposal } from '../../types';
import type { TimelineStep } from '../../components/shared/StatusTimeline';
import type { ChecklistItem } from '../../components/shared/checklist';
import { hasSignaturePlacements } from './signaturePlacements';

const STATUS_ORDER = ['draft', 'sent', 'viewed', 'accepted'];

// Pre-2026-05-18 proposals could land in 'awaiting_payment' or 'paid'
// when proposals still spawned Stripe artifacts on accept. Those rows
// are still in the DB and need to render correctly — collapse them to
// 'accepted' rank so a fully-signed-and-paid legacy proposal shows the
// Signed step as completed, not as upcoming behind a "current" Draft.
const LEGACY_STATUS_ALIAS: Record<string, string> = {
  awaiting_payment: 'accepted',
  paid: 'accepted',
};

// Once a proposal hits any of these states, edits would mutate
// something the customer has already committed to. Includes legacy
// terminal billing statuses so a paid pre-cutover proposal stays locked.
const LOCKED_STATUSES = new Set(['signed', 'accepted', 'awaiting_payment', 'paid']);

function rankStatus(status: string | undefined): number {
  if (!status) return 0;
  const canonical = LEGACY_STATUS_ALIAS[status] ?? status;
  const idx = STATUS_ORDER.indexOf(canonical);
  return idx === -1 ? 0 : idx;
}

/** True when the proposal has reached a customer-committed status and
 *  should no longer be edited from the UI. */
export function isProposalLocked(proposal: Proposal): boolean {
  return LOCKED_STATUSES.has(proposal.status ?? '');
}

/**
 * Build the Draft → Sent → Viewed → Signed timeline. Step state derives
 * from the actual timestamps on the proposal (sent_at, viewed_at,
 * signed_at) — falling back to status ranking when a timestamp isn't
 * available. Rejected proposals collapse to a Draft → Sent → Rejected
 * three-step view so the timeline still reads.
 */
export function buildProposalTimelineSteps(proposal: Proposal): TimelineStep[] {
  if (proposal.status === 'rejected') {
    return [
      { key: 'draft', label: 'Draft', at: proposal.created_at, state: 'completed' },
      {
        key: 'sent',
        label: 'Sent',
        at: proposal.sent_at ?? null,
        state: proposal.sent_at ? 'completed' : 'skipped',
      },
      {
        key: 'rejected',
        label: 'Rejected',
        at: proposal.rejected_at ?? null,
        state: 'current',
        tooltip: proposal.rejection_reason ?? undefined,
      },
    ];
  }

  const rank = rankStatus(proposal.status);

  const stepState = (myRank: number): TimelineStep['state'] => {
    if (myRank < rank) return 'completed';
    if (myRank === rank) return 'current';
    return 'upcoming';
  };

  return [
    { key: 'draft', label: 'Draft', at: proposal.created_at, state: stepState(0) },
    {
      key: 'sent',
      label: 'Sent',
      at: proposal.sent_at ?? null,
      state: stepState(1),
    },
    {
      key: 'viewed',
      label: 'Viewed',
      at: proposal.last_viewed_at ?? null,
      state: stepState(2),
    },
    {
      key: 'signed',
      label: 'Signed',
      at: proposal.signed_at ?? null,
      state: stepState(3),
      tooltip: proposal.signer_name
        ? `Signed by ${proposal.signer_name}`
        : undefined,
    },
  ];
}

/**
 * Build the pre-send checklist. Only renders when the proposal is in a
 * sendable status (draft/sent/viewed) — accepted proposals have no send
 * action so there's nothing to gate.
 */
export function buildProposalSendChecklist(
  proposal: Proposal,
  options: {
    onEditContact: () => void;
    onEditValidUntil?: () => void;
    onManageSigningDocuments?: () => void;
  },
): ChecklistItem[] {
  const items: ChecklistItem[] = [];

  // A recipient is either a designated signer email override OR the
  // linked contact's email. Without one, /send returns 400.
  const recipient =
    proposal.designated_signer_email || proposal.contact?.email || '';
  items.push({
    key: 'recipient',
    label: recipient ? `Recipient set (${recipient})` : 'Recipient email',
    state: Boolean(recipient),
    hint: recipient
      ? undefined
      : 'Set a designated signer email or attach a contact with an email.',
    action: recipient
      ? undefined
      : { label: 'Set recipient', onClick: options.onEditContact },
  });

  // Linked contact OR company is required so accepted-side hooks
  // (deal creation, activity log, contact-of-record on signed PDF)
  // have something to attach to.
  const hasEntity = Boolean(proposal.contact || proposal.company);
  items.push({
    key: 'entity',
    label: hasEntity ? 'Linked to contact or company' : 'Link a contact or company',
    state: hasEntity,
    hint: hasEntity ? undefined : 'Attach a contact or company so we can route the signed copy.',
    action: hasEntity ? undefined : { label: 'Edit', onClick: options.onEditContact },
  });

  // Expired valid_until is a warning, not a hard block — the backend
  // doesn't refuse send on a past date — but the sender probably didn't
  // mean to send a proposal that says "valid until 3 weeks ago."
  if (proposal.valid_until) {
    const isExpired = new Date(proposal.valid_until) < new Date();
    items.push({
      key: 'valid_until',
      label: isExpired
        ? `Expired (valid until ${proposal.valid_until})`
        : `Valid until ${proposal.valid_until}`,
      state: !isExpired,
      hint: isExpired
        ? 'The proposal lists a past expiration date. Update it before sending.'
        : undefined,
      action:
        isExpired && options.onEditValidUntil
          ? { label: 'Update date', onClick: options.onEditValidUntil }
          : undefined,
    });
  }

  const signingDocuments = proposal.signing_documents ?? [];
  if (signingDocuments.length > 0) {
    const missingPlacement = signingDocuments.filter(
      (doc) =>
        !hasSignaturePlacements(doc.signature_field_coords) ||
        !hasSignaturePlacements(doc.date_field_coords),
    );
    const firstMissingPlacement = missingPlacement[0];
    items.push({
      key: 'signing_documents',
      label:
        missingPlacement.length === 0
          ? `Signature and date areas placed on ${signingDocuments.length} document${
              signingDocuments.length === 1 ? '' : 's'
            }`
          : `${missingPlacement.length} signing document${
              missingPlacement.length === 1 ? '' : 's'
            } need placement`,
      state: missingPlacement.length === 0,
      hint:
        !firstMissingPlacement
          ? undefined
          : `Place signature and date areas on ${firstMissingPlacement.original_filename} before sending.`,
      action:
        missingPlacement.length === 0 || !options.onManageSigningDocuments
          ? undefined
          : {
              label: 'Place areas',
              onClick: options.onManageSigningDocuments,
            },
    });
  } else if (
    proposal.master_contract_pdf_path &&
    (!hasSignaturePlacements(proposal.signature_field_coords) ||
      !hasSignaturePlacements(proposal.date_field_coords))
  ) {
    items.push({
      key: 'legacy_master_signature',
      label: 'Master agreement needs signature and date placement',
      state: false,
      hint: 'Place signature and date areas on the uploaded master agreement before sending.',
      action: options.onManageSigningDocuments
        ? { label: 'Place areas', onClick: options.onManageSigningDocuments }
        : undefined,
    });
  }

  return items;
}

export function hasSigningDocumentSendBlocker(proposal: Proposal): boolean {
  const signingDocuments = proposal.signing_documents ?? [];
  if (
    signingDocuments.some(
      (doc) =>
        !hasSignaturePlacements(doc.signature_field_coords) ||
        !hasSignaturePlacements(doc.date_field_coords),
    )
  ) {
    return true;
  }
  return Boolean(
    signingDocuments.length === 0 &&
      proposal.master_contract_pdf_path &&
      (!hasSignaturePlacements(proposal.signature_field_coords) ||
        !hasSignaturePlacements(proposal.date_field_coords)),
  );
}
