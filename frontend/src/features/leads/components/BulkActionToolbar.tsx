/**
 * Bulk action toolbar - appears when checkboxes are selected on list views
 */

import { Fragment } from 'react';
import { Menu, Transition } from '@headlessui/react';
import {
  UserGroupIcon,
  ArrowPathIcon,
  ViewColumnsIcon,
  TrashIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { Button } from '../../../components/ui/Button';

export interface BulkStageOption {
  // ``null`` represents the "Off pipeline" target (clear stage).
  id: number | null;
  label: string;
}

interface BulkActionToolbarProps {
  selectedIds: number[];
  entityType: string;
  onBulkUpdate: (updates: Record<string, unknown>) => Promise<void>;
  onBulkAssign: (ownerId: number) => Promise<void>;
  onClearSelection: () => void;
  isLoading?: boolean;
  users?: Array<{ id: number; full_name: string }>;
  statusOptions?: Array<{ value: string; label: string }>;
  // Pipeline-stage move targets. When provided, the toolbar renders a
  // "Change Stage" menu that calls onBulkMoveStage with the chosen
  // stage id (or null to take leads off the pipeline). Lead-specific
  // because /move runs Won auto-convert + pre-flight dedup per row —
  // generic Companies/Contacts bulk doesn't need this.
  stageOptions?: BulkStageOption[];
  onBulkMoveStage?: (stageId: number | null) => Promise<void>;
  // Optional bulk delete. Caller owns the confirm dialog so the copy
  // can stay entity-specific ("Delete 25 leads? This can't be undone.").
  onBulkDelete?: () => void;
  // Caller-owned extra action node, rendered before the menus. Kept
  // for callers that need a one-off affordance the generic toolbar
  // doesn't model.
  extraAction?: React.ReactNode;
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
  stageOptions = [],
  onBulkMoveStage,
  onBulkDelete,
  extraAction,
}: BulkActionToolbarProps) {
  if (selectedIds.length === 0) return null;

  const handleStatusChange = async (status: string) => {
    await onBulkUpdate({ status });
  };

  const handleAssign = async (userId: number) => {
    await onBulkAssign(userId);
  };

  const handleStageChange = async (stageId: number | null) => {
    if (onBulkMoveStage) await onBulkMoveStage(stageId);
  };

  return (
    <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-50 bg-white dark:bg-gray-800 shadow-lg border border-gray-200 dark:border-gray-700 rounded-lg px-4 py-3 flex items-center gap-3 min-w-[320px]">
      <span className="text-sm font-medium text-gray-700 dark:text-gray-200">
        {selectedIds.length} {entityType} selected
      </span>

      <div className="flex items-center gap-2 ml-auto">
        {extraAction}
        {/* Stage Move (Leads only) */}
        {stageOptions.length > 0 && onBulkMoveStage && (
          <Menu as="div" className="relative">
            {() => (
              <>
                <Menu.Button as={Fragment}>
                  <Button
                    size="sm"
                    variant="secondary"
                    leftIcon={<ViewColumnsIcon className="h-4 w-4" />}
                    disabled={isLoading}
                  >
                    Change Stage
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
                  <Menu.Items className="absolute bottom-full mb-1 left-0 z-50 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-md shadow-lg py-1 min-w-[180px] max-h-64 overflow-y-auto focus:outline-none">
                    {stageOptions.map((opt) => (
                      <Menu.Item key={opt.id ?? 'off'}>
                        {({ active }) => (
                          <button
                            onClick={() => handleStageChange(opt.id)}
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
        {/* Status Update */}
        {statusOptions.length > 0 && (
          <Menu as="div" className="relative">
            {() => (
              <>
                <Menu.Button as={Fragment}>
                  <Button
                    size="sm"
                    variant="secondary"
                    leftIcon={<ArrowPathIcon className="h-4 w-4" />}
                    disabled={isLoading}
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
            {() => (
              <>
                <Menu.Button as={Fragment}>
                  <Button
                    size="sm"
                    variant="secondary"
                    leftIcon={<UserGroupIcon className="h-4 w-4" />}
                    disabled={isLoading}
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

        {/* Bulk Delete */}
        {onBulkDelete && (
          <Button
            size="sm"
            variant="secondary"
            leftIcon={<TrashIcon className="h-4 w-4" />}
            onClick={onBulkDelete}
            disabled={isLoading}
            className="text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30"
          >
            Delete
          </Button>
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
