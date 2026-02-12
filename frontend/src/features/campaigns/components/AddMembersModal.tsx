/**
 * Modal for adding contacts or leads to a campaign
 */

import { useState, useMemo } from 'react';
import clsx from 'clsx';
import { XMarkIcon, MagnifyingGlassIcon, CheckIcon } from '@heroicons/react/24/outline';
import { Button } from '../../../components/ui/Button';
import { Spinner } from '../../../components/ui/Spinner';
import { useContacts } from '../../../hooks/useContacts';
import { useLeads } from '../../../hooks/useLeads';
import type { Contact, Lead } from '../../../types';

interface AddMembersModalProps {
  campaignId: number;
  existingMemberIds?: { contacts: number[]; leads: number[] };
  onClose: () => void;
  onAdd: (memberType: 'contact' | 'lead', memberIds: number[]) => Promise<void>;
  isLoading?: boolean;
}

type MemberType = 'contact' | 'lead';

export function AddMembersModal({
  existingMemberIds = { contacts: [], leads: [] },
  onClose,
  onAdd,
  isLoading = false,
}: AddMembersModalProps) {
  const [memberType, setMemberType] = useState<MemberType>('contact');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  // Fetch contacts and leads
  const { data: contactsData, isLoading: isLoadingContacts } = useContacts({
    page_size: 100,
    search: searchQuery || undefined,
  });
  const { data: leadsData, isLoading: isLoadingLeads } = useLeads({
    page_size: 100,
    search: searchQuery || undefined,
  });

  const contacts = contactsData?.items ?? [];
  const leads = leadsData?.items ?? [];

  // Filter out already added members
  const availableContacts = useMemo(
    () => contacts.filter((c) => !existingMemberIds.contacts.includes(c.id)),
    [contacts, existingMemberIds.contacts]
  );

  const availableLeads = useMemo(
    () => leads.filter((l) => !existingMemberIds.leads.includes(l.id)),
    [leads, existingMemberIds.leads]
  );

  const currentItems = memberType === 'contact' ? availableContacts : availableLeads;
  const isLoadingItems = memberType === 'contact' ? isLoadingContacts : isLoadingLeads;

  const handleToggleSelect = (id: number) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  };

  const handleSelectAll = () => {
    const allIds = currentItems.map((item) => item.id);
    setSelectedIds(allIds);
  };

  const handleClearSelection = () => {
    setSelectedIds([]);
  };

  const handleSubmit = async () => {
    if (selectedIds.length === 0) return;
    await onAdd(memberType, selectedIds);
  };

  const handleTypeChange = (type: MemberType) => {
    setMemberType(type);
    setSelectedIds([]);
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-screen items-center justify-center p-0 sm:p-4">
        <div
          className="fixed inset-0 bg-black bg-opacity-25"
          onClick={onClose}
        />
        <div className="relative bg-white sm:rounded-lg shadow-xl w-full sm:max-w-2xl h-full sm:h-auto sm:max-h-[80vh] flex flex-col">
          {/* Header */}
          <div className="px-4 sm:px-6 py-4 border-b flex items-center justify-between flex-shrink-0">
            <h2 className="text-base sm:text-lg font-semibold text-gray-900">Add Campaign Members</h2>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors"
              aria-label="Close"
            >
              <XMarkIcon className="h-5 w-5 text-gray-500" aria-hidden="true" />
            </button>
          </div>

          {/* Member Type Tabs */}
          <div className="px-4 sm:px-6 py-3 border-b flex-shrink-0">
            <div className="flex space-x-2 sm:space-x-4">
              <button
                onClick={() => handleTypeChange('contact')}
                className={clsx(
                  'flex-1 sm:flex-none px-3 sm:px-4 py-2 text-sm font-medium rounded-lg transition-colors',
                  memberType === 'contact'
                    ? 'bg-primary-100 text-primary-700'
                    : 'text-gray-500 hover:bg-gray-100'
                )}
              >
                Contacts ({availableContacts.length})
              </button>
              <button
                onClick={() => handleTypeChange('lead')}
                className={clsx(
                  'flex-1 sm:flex-none px-3 sm:px-4 py-2 text-sm font-medium rounded-lg transition-colors',
                  memberType === 'lead'
                    ? 'bg-primary-100 text-primary-700'
                    : 'text-gray-500 hover:bg-gray-100'
                )}
              >
                Leads ({availableLeads.length})
              </button>
            </div>
          </div>

          {/* Search */}
          <div className="px-4 sm:px-6 py-3 border-b flex-shrink-0">
            <div className="relative">
              <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
              <label htmlFor="member-search" className="sr-only">Search members</label>
              <input
                type="search"
                id="member-search"
                name="search"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder={`Search ${memberType}s...`}
                className="w-full pl-10 pr-4 py-2 text-base sm:text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              />
            </div>
          </div>

          {/* Selection Actions */}
          <div className="px-4 sm:px-6 py-2 border-b flex items-center justify-between text-sm flex-shrink-0">
            <span className="text-gray-600">
              {selectedIds.length} selected
            </span>
            <div className="flex gap-2">
              <button
                onClick={handleSelectAll}
                className="text-primary-600 hover:text-primary-700"
                disabled={currentItems.length === 0}
              >
                Select All
              </button>
              <span className="text-gray-300">|</span>
              <button
                onClick={handleClearSelection}
                className="text-gray-500 hover:text-gray-700"
                disabled={selectedIds.length === 0}
              >
                Clear
              </button>
            </div>
          </div>

          {/* List */}
          <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-3">
            {isLoadingItems ? (
              <div className="flex items-center justify-center py-12">
                <Spinner />
              </div>
            ) : currentItems.length === 0 ? (
              <div className="text-center py-12 text-gray-500">
                <p>No {memberType}s available to add.</p>
                {searchQuery && (
                  <p className="text-sm mt-1">Try adjusting your search.</p>
                )}
              </div>
            ) : (
              <div className="space-y-2">
                {currentItems.map((item) => {
                  const isSelected = selectedIds.includes(item.id);
                  const name =
                    memberType === 'contact'
                      ? (item as Contact).full_name ||
                        `${(item as Contact).first_name} ${(item as Contact).last_name}`
                      : `${(item as Lead).first_name} ${(item as Lead).last_name}`;
                  const email = item.email || '-';
                  const extra =
                    memberType === 'contact'
                      ? (item as Contact).company?.name
                      : (item as Lead).company_name;

                  return (
                    <div
                      key={item.id}
                      onClick={() => handleToggleSelect(item.id)}
                      className={clsx(
                        'flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors',
                        isSelected
                          ? 'border-primary-500 bg-primary-50'
                          : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                      )}
                    >
                      <div
                        className={clsx(
                          'w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0',
                          isSelected
                            ? 'border-primary-500 bg-primary-500'
                            : 'border-gray-300'
                        )}
                      >
                        {isSelected && <CheckIcon className="h-3 w-3 text-white" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-gray-900 truncate">{name}</p>
                        <p className="text-xs sm:text-sm text-gray-500 truncate">
                          {email}
                          {extra && ` - ${extra}`}
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-4 sm:px-6 py-4 border-t flex flex-col-reverse sm:flex-row sm:items-center sm:justify-end gap-3 flex-shrink-0">
            <Button variant="secondary" onClick={onClose} disabled={isLoading} className="w-full sm:w-auto">
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              isLoading={isLoading}
              disabled={selectedIds.length === 0}
              className="w-full sm:w-auto"
            >
              Add {selectedIds.length} {memberType}
              {selectedIds.length !== 1 ? 's' : ''}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default AddMembersModal;
