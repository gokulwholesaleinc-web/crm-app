/**
 * Contract-flow helpers shared by ContractDetailPage. Builds the
 * StatusTimeline steps + SendChecklist items from a Contract record.
 */

import type { Contract } from '../../types';
import type { TimelineStep } from '../../components/shared/StatusTimeline';
import type { ChecklistItem } from '../../components/shared/checklist';

// Status flow: draft → sent → signed → active → expired/terminated.
// Contracts don't carry payment so there's no Paid step.
const STATUS_ORDER = ['draft', 'sent', 'signed', 'active', 'expired'];

function rankStatus(status: string | undefined): number {
  if (!status) return 0;
  const idx = STATUS_ORDER.indexOf(status);
  return idx === -1 ? 0 : idx;
}

/**
 * Build the Draft → Sent → Signed → Active timeline. Step state derives
 * from the actual timestamps on the contract (sent_at, signed_at) and
 * the start_date / end_date for the active-vs-expired transition.
 *
 * Terminated/voided contracts collapse to a Draft → Terminated view so
 * the timeline still reads.
 */
export function buildContractTimelineSteps(contract: Contract): TimelineStep[] {
  if (contract.status === 'terminated' || contract.status === 'voided') {
    return [
      { key: 'draft', label: 'Draft', at: contract.created_at, state: 'completed' },
      {
        key: 'sent',
        label: 'Sent',
        at: contract.sent_at ?? null,
        state: contract.sent_at ? 'completed' : 'skipped',
      },
      {
        key: 'terminated',
        label: contract.status === 'voided' ? 'Voided' : 'Terminated',
        at: contract.updated_at,
        state: 'current',
      },
    ];
  }

  const rank = rankStatus(contract.status);

  const stepState = (myRank: number): TimelineStep['state'] => {
    if (myRank < rank) return 'completed';
    if (myRank === rank) return 'current';
    return 'upcoming';
  };

  const steps: TimelineStep[] = [
    { key: 'draft', label: 'Draft', at: contract.created_at, state: stepState(0) },
    {
      key: 'sent',
      label: 'Sent',
      at: contract.sent_at ?? null,
      state: stepState(1),
    },
    {
      key: 'signed',
      label: 'Signed',
      at: contract.signed_at ?? null,
      state: stepState(2),
      tooltip: contract.signed_by_name
        ? `Signed by ${contract.signed_by_name}`
        : undefined,
    },
    {
      key: 'active',
      label: 'Active',
      at: contract.start_date ?? null,
      state: stepState(3),
    },
  ];

  // Only show Expired step when the contract actually has an end_date —
  // open-ended contracts don't have a meaningful expiry step.
  if (contract.end_date) {
    steps.push({
      key: 'expired',
      label: 'Expired',
      at: contract.end_date,
      state: stepState(4),
    });
  }

  return steps;
}

/**
 * Build the pre-send checklist for a contract. Mirrors the proposal
 * checklist shape so the two surfaces feel like one product.
 */
export function buildContractSendChecklist(
  contract: Contract,
  options: { onEditContact: () => void },
): ChecklistItem[] {
  const items: ChecklistItem[] = [];

  // Contracts route signature requests to the linked contact (the
  // contact's email is resolved server-side at send time, but ContactBrief
  // on Contract doesn't surface email — so we gate on "is a contact
  // linked" client-side and let the backend 400 if the contact has no
  // email, which surfaces via the toast on click.
  const hasContact = Boolean(contract.contact?.id);
  items.push({
    key: 'recipient',
    label: hasContact ? 'Contact linked' : 'Contact not set',
    state: hasContact,
    hint: hasContact
      ? undefined
      : 'Attach a contact so we can route the signature request to them.',
    action: hasContact
      ? undefined
      : { label: 'Set contact', onClick: options.onEditContact },
  });

  // Scope is the body of what's being signed — sending a blank scope
  // creates a hollow document. Flagged as required.
  const hasScope = Boolean(contract.scope && contract.scope.trim() !== '');
  items.push({
    key: 'scope',
    label: hasScope ? 'Scope defined' : 'Scope is empty',
    state: hasScope,
    hint: hasScope
      ? undefined
      : 'Fill in the scope so the signer knows what they’re agreeing to.',
    action: hasScope ? undefined : { label: 'Edit scope', onClick: options.onEditContact },
  });

  // Linked company helps with audit trail + reporting. Optional —
  // freelance / sole-proprietor contracts may legitimately have no
  // company.
  const hasEntity = Boolean(contract.contact || contract.company);
  items.push({
    key: 'entity',
    label: hasEntity ? 'Linked to contact or company' : 'Link a contact or company',
    state: hasEntity,
    hint: hasEntity ? undefined : 'Attach at least one party so we can route the signed copy.',
    action: hasEntity ? undefined : { label: 'Edit', onClick: options.onEditContact },
  });

  // Contract value is optional — NDAs / referral agreements often
  // don't carry one — but absent value is worth surfacing.
  const hasValue = Boolean(contract.value && Number(contract.value) > 0);
  items.push({
    key: 'value',
    label: hasValue
      ? `Value set (${new Intl.NumberFormat(undefined, { style: 'currency', currency: contract.currency || 'USD' }).format(Number(contract.value))})`
      : 'Value (optional)',
    state: hasValue ? true : 'optional',
    hint: hasValue ? undefined : 'No value entered. Set one if the contract carries a fee — useful for reporting.',
  });

  return items;
}
