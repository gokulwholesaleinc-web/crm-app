/**
 * Duplicate Warning Modal - shown when creating an entity that matches existing records.
 * User can choose to: Create Anyway, View Duplicate, or Cancel.
 */

import { Modal, Button } from '../ui';
import type { DuplicateMatch } from '../../api/dedup';

interface DuplicateWarningModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCreateAnyway: () => void;
  onViewDuplicate: (id: number) => void;
  duplicates: DuplicateMatch[];
  entityType: string;
}

export function DuplicateWarningModal({
  isOpen,
  onClose,
  onCreateAnyway,
  onViewDuplicate,
  duplicates,
  entityType,
}: DuplicateWarningModalProps) {
  const entityLabel = entityType === 'contacts'
    ? 'contact'
    : entityType === 'companies'
    ? 'company'
    : 'lead';

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Potential Duplicates Found"
      size="lg"
    >
      <div className="space-y-4">
        <p className="text-sm text-gray-600">
          We found {duplicates.length} potential duplicate{duplicates.length !== 1 ? 's' : ''}.
          Please review before creating a new {entityLabel}.
        </p>

        <div className="divide-y divide-gray-100 border border-gray-200 rounded-lg overflow-hidden">
          {duplicates.map((dup) => (
            <div
              key={dup.id}
              className="flex items-center justify-between p-4 hover:bg-gray-50"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-900 truncate">
                  {dup.display_name}
                </p>
                <div className="flex items-center gap-3 mt-1 text-xs text-gray-500">
                  {dup.email && <span>{dup.email}</span>}
                  {dup.phone && <span>{dup.phone}</span>}
                </div>
                <p className="mt-1 text-xs text-amber-600 font-medium">
                  {dup.match_reason}
                </p>
              </div>
              <Button
                variant="secondary"
                onClick={() => onViewDuplicate(dup.id)}
                className="flex-shrink-0 ml-4"
              >
                View
              </Button>
            </div>
          ))}
        </div>

        <div className="flex flex-col-reverse gap-3 sm:flex-row sm:justify-end pt-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={onCreateAnyway}>
            Create Anyway
          </Button>
        </div>
      </div>
    </Modal>
  );
}

export default DuplicateWarningModal;
