import { ConfirmDialog } from '../ui';

export type RelationEntityType = 'proposal' | 'contract' | 'quote';

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
