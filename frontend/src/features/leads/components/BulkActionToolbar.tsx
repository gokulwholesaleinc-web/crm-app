/**
 * Bulk action toolbar - appears when checkboxes are selected on list views
 */

import { useState } from 'react';
import {
  UserGroupIcon,
  ArrowPathIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { Button } from '../../../components/ui/Button';

interface BulkActionToolbarProps {
  selectedIds: number[];
  entityType: string;
  onBulkUpdate: (updates: Record<string, unknown>) => Promise<void>;
  onBulkAssign: (ownerId: number) => Promise<void>;
  onClearSelection: () => void;
  isLoading?: boolean;
  users?: Array<{ id: number; full_name: string }>;
  statusOptions?: Array<{ value: string; label: string }>;
}

export function BulkActionToolbar({
  selectedIds,
  entityType,
  onBulkUpdate,
  onBulkAssign,
  onClearSelection,
  isLoading,
  users = [],
  statusOptions = [],
}: BulkActionToolbarProps) {
  const [showStatusDropdown, setShowStatusDropdown] = useState(false);
  const [showAssignDropdown, setShowAssignDropdown] = useState(false);

  if (selectedIds.length === 0) return null;

  const handleStatusChange = async (status: string) => {
    await onBulkUpdate({ status });
    setShowStatusDropdown(false);
  };

  const handleAssign = async (userId: number) => {
    await onBulkAssign(userId);
    setShowAssignDropdown(false);
  };

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-white shadow-lg border rounded-lg px-4 py-3 flex items-center gap-3 min-w-[320px]">
      <span className="text-sm font-medium text-gray-700">
        {selectedIds.length} {entityType} selected
      </span>

      <div className="flex items-center gap-2 ml-auto">
        {/* Status Update */}
        {statusOptions.length > 0 && (
          <div className="relative">
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<ArrowPathIcon className="h-4 w-4" />}
              onClick={() => {
                setShowStatusDropdown(!showStatusDropdown);
                setShowAssignDropdown(false);
              }}
              disabled={isLoading}
            >
              Update Status
            </Button>
            {showStatusDropdown && (
              <div className="absolute bottom-full mb-1 left-0 bg-white border rounded-md shadow-lg py-1 min-w-[160px]">
                {statusOptions.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => handleStatusChange(opt.value)}
                    className="block w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100"
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Assign Owner */}
        {users.length > 0 && (
          <div className="relative">
            <Button
              size="sm"
              variant="secondary"
              leftIcon={<UserGroupIcon className="h-4 w-4" />}
              onClick={() => {
                setShowAssignDropdown(!showAssignDropdown);
                setShowStatusDropdown(false);
              }}
              disabled={isLoading}
            >
              Assign
            </Button>
            {showAssignDropdown && (
              <div className="absolute bottom-full mb-1 left-0 bg-white border rounded-md shadow-lg py-1 min-w-[180px] max-h-48 overflow-y-auto">
                {users.map((user) => (
                  <button
                    key={user.id}
                    onClick={() => handleAssign(user.id)}
                    className="block w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100"
                  >
                    {user.full_name}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Clear */}
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            onClearSelection();
            setShowStatusDropdown(false);
            setShowAssignDropdown(false);
          }}
        >
          <XMarkIcon className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

export default BulkActionToolbar;
