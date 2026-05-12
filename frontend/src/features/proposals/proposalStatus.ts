/**
 * Proposal-flow helpers shared by ProposalDetail to keep the detail page
 * focused on rendering. Builds the StatusTimeline steps + SendChecklist
 * items + primary-action selection from a Proposal record.
 */

import type { Proposal } from '../../types';
import type { TimelineStep } from '../../components/shared/StatusTimeline';
import type { ChecklistItem } from '../../components/shared/SendChecklist';

const STATUS_ORDER = ['draft', 'sent', 'viewed', 'accepted', 'awaiting_payment', 'paid'];

// Once a proposal hits any of these states, edits/refresh-from-quote would
// mutate something the customer has already committed to. The backend
// refuses these on /refresh-from-quote — keep the frontend in sync.
const LOCKED_STATUSES = new Set(['signed', 'accepted', 'awaiting_payment', 'paid']);

function rankStatus(status: string | undefined): number {
  if (!status) return 0;
  const idx = STATUS_ORDER.indexOf(status);
  return idx === -1 ? 0 : idx;
}

/** True when the proposal can no longer be safely refreshed from its quote. */
export function isProposalLocked(proposal: Proposal): boolean {
  return LOCKED_STATUSES.has(proposal.status ?? '');
}

function hasBillingAmount(proposal: Proposal): boolean {
  return Boolean(proposal.amount && Number(proposal.amount) > 0);
}

/**
 * Build the Draft → Sent → Viewed → Signed → Paid timeline. Step state
 * derives from the actual timestamps on the proposal (sent_at, viewed_at,
 * signed_at, paid_at) — falling back to status ranking when a timestamp
 * isn't available. Rejected proposals collapse to a Draft → Sent → Rejected
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

  // Paid is only meaningful for proposals that actually carry a billing
  // amount — a one-time $0 proposal still goes Draft → Sent → Viewed →
  // Signed and stops there. Mark Paid as skipped in that case so the
  // timeline doesn't look unfinished forever.
  const hasBilling = hasBillingAmount(proposal);

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
    {
      key: 'paid',
      label: 'Paid',
      at: proposal.paid_at ?? null,
      state: hasBilling ? stepState(5) : 'skipped',
    },
  ];
}

/**
 * Build the pre-send checklist. Only renders when the proposal is in a
 * sendable status (draft/sent/viewed) — accepted/paid proposals have no
 * send action so there's nothing to gate.
 */
export function buildProposalSendChecklist(
  proposal: Proposal,
  options: {
    onEditContact: () => void;
    onEditValidUntil?: () => void;
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

  // Billing is optional — a free strategy doc proposal doesn't need it.
  // Marked optional so it surfaces as a hint without blocking send.
  const hasBilling = hasBillingAmount(proposal);
  items.push({
    key: 'billing',
    label: hasBilling
      ? `Billing configured (${proposal.payment_type === 'subscription' ? 'subscription' : 'one-time'})`
      : 'Billing (optional)',
    state: hasBilling ? true : 'optional',
    hint: hasBilling
      ? undefined
      : 'No invoice will spawn on accept. Add a billing amount if you want Stripe to handle payment.',
  });

  // Expired valid_until is a warning, not a hard block — the backend
  // doesn't refuse send on a past date — but Lorenzo probably doesn't
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

  return items;
}
