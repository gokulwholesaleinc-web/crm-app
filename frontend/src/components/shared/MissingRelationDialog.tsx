import { ConfirmDialog } from '../ui';

// ``contract`` retired 2026-05-14 — contracts router unmounted.
// ``quote`` retired 2026-05-14 — quotes router unmounted.
// Both surfaces that mounted with those entityType values have been
// removed; the union now only covers Proposals.
export type RelationEntityType = 'proposal';

interface MissingRelationDialogProps {
  isOpen: boolean;
  entityType: RelationEntityType;
  onConfirm: () => void;
  onCancel: () => void;
  isLoading?: boolean;
}

export function MissingRelationDialog({
  isOpen,
  entityType,
  onConfirm,
  onCancel,
  isLoading,
}: MissingRelationDialogProps) {
  return (
    <ConfirmDialog
      isOpen={isOpen}
      onClose={onCancel}
      onConfirm={onConfirm}
      title={`Create ${entityType} without a contact or company?`}
      message={
        <span>
          This {entityType} has no contact or company attached. You can save it
          now and assign one later by editing the {entityType}, but you{'’'}ll
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
