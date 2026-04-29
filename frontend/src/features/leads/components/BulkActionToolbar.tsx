/**
 * Bulk action toolbar - appears when checkboxes are selected on list views
 */

import { Fragment } from 'react';
import { Menu, Transition } from '@headlessui/react';
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
  if (selectedIds.length === 0) return null;

  const handleStatusChange = async (status: string) => {
    await onBulkUpdate({ status });
  };

  const handleAssign = async (userId: number) => {
    await onBulkAssign(userId);
  };

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-white dark:bg-gray-800 shadow-lg border border-gray-200 dark:border-gray-700 rounded-lg px-4 py-3 flex items-center gap-3 min-w-[320px]">
      <span className="text-sm font-medium text-gray-700 dark:text-gray-200">
        {selectedIds.length} {entityType} selected
      </span>

      <div className="flex items-center gap-2 ml-auto">
        {/* Status Update */}
        {statusOptions.length > 0 && (
          <Menu as="div" className="relative">
            {({ open }) => (
              <>
                <Menu.Button
                  as={Fragment}
                >
                  <Button
                    size="sm"
                    variant="secondary"
                    leftIcon={<ArrowPathIcon className="h-4 w-4" />}
                    disabled={isLoading}
                    aria-haspopup="true"
                    aria-expanded={open}
                  >
                    Update Status
                  </Button>
                </Menu.Button>
                <Transition
                  as={Fragment}
                  enter="transition ease-out duration-100"
                  enterFrom="transform opacity-0 scale-95"
                  enterTo="transform opacity-100 scale-100"
                  leave="transition ease-in duration-75"
                  leaveFrom="transform opacity-100 scale-100"
                  leaveTo="transform opacity-0 scale-95"
                >
                  <Menu.Items className="absolute bottom-full mb-1 left-0 z-50 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md shadow-lg py-1 min-w-[160px] focus:outline-none">
                    {statusOptions.map((opt) => (
                      <Menu.Item key={opt.value}>
                        {({ active }) => (
                          <button
                            onClick={() => handleStatusChange(opt.value)}
                            className={`block w-full text-left px-3 py-1.5 text-sm text-gray-700 dark:text-gray-200 ${active ? 'bg-gray-100 dark:bg-gray-700' : ''}`}
                          >
                            {opt.label}
                          </button>
                        )}
                      </Menu.Item>
                    ))}
                  </Menu.Items>
                </Transition>
              </>
            )}
          </Menu>
        )}

        {/* Assign Owner */}
        {users.length > 0 && (
          <Menu as="div" className="relative">
            {({ open }) => (
              <>
                <Menu.Button
                  as={Fragment}
                >
                  <Button
                    size="sm"
                    variant="secondary"
                    leftIcon={<UserGroupIcon className="h-4 w-4" />}
                    disabled={isLoading}
                    aria-haspopup="true"
                    aria-expanded={open}
                  >
                    Assign
                  </Button>
                </Menu.Button>
                <Transition
                  as={Fragment}
                  enter="transition ease-out duration-100"
                  enterFrom="transform opacity-0 scale-95"
                  enterTo="transform opacity-100 scale-100"
                  leave="transition ease-in duration-75"
                  leaveFrom="transform opacity-100 scale-100"
                  leaveTo="transform opacity-0 scale-95"
                >
                  <Menu.Items className="absolute bottom-full mb-1 left-0 z-50 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md shadow-lg py-1 min-w-[180px] max-h-48 overflow-y-auto focus:outline-none">
                    {users.map((user) => (
                      <Menu.Item key={user.id}>
                        {({ active }) => (
                          <button
                            onClick={() => handleAssign(user.id)}
                            className={`block w-full text-left px-3 py-1.5 text-sm text-gray-700 dark:text-gray-200 ${active ? 'bg-gray-100 dark:bg-gray-700' : ''}`}
                          >
                            {user.full_name}
                          </button>
                        )}
                      </Menu.Item>
                    ))}
                  </Menu.Items>
                </Transition>
              </>
            )}
          </Menu>
        )}

        {/* Clear */}
        <Button
          size="sm"
          variant="ghost"
          onClick={onClearSelection}
          aria-label="Clear selection"
          className="text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
        >
          <XMarkIcon className="h-4 w-4" aria-hidden="true" />
        </Button>
      </div>
    </div>
  );
}

export default BulkActionToolbar;
