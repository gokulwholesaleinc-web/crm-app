import { ConfirmDialog } from '../ui';

// Contracts + Quotes retired 2026-05-14 — both surfaces that used this
// dialog are gone, so the entityType prop collapsed to a single value
// ("proposal") and got inlined. If a future module reintroduces a
// missing-relation confirmation, restore the prop + RelationEntityType
// union.

interface MissingRelationDialogProps {
  isOpen: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  isLoading?: boolean;
}

export function MissingRelationDialog({
  isOpen,
  onConfirm,
  onCancel,
  isLoading,
}: MissingRelationDialogProps) {
  return (
    <ConfirmDialog
      isOpen={isOpen}
      onClose={onCancel}
      onConfirm={onConfirm}
      title="Create proposal without a contact or company?"
      message={
        <span>
          This proposal has no contact or company attached. You can save it
          now and assign one later by editing the proposal, but you{'’'}ll
          need to add a recipient before it can be sent.
        </span>
      }
      confirmLabel="Save anyway"
      cancelLabel="Back to form"
      variant="warning"
      isLoading={isLoading}
    />
  );
}
