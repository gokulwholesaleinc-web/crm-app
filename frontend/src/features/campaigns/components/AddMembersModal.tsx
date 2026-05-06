/**
 * Modal for adding contacts or leads to a campaign
 */

import { useState, useMemo } from 'react';
import clsx from 'clsx';
import { Button } from '../../../components/ui/Button';
import { Modal, ModalFooter } from '../../../components/ui/Modal';
import { ScrollableListPicker } from '../../../components/shared/ScrollableListPicker';
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
  const [selectedIds, setSelectedIds] = useState<Array<string | number>>([]);

  const { data: contactsData, isLoading: isLoadingContacts } = useContacts({
    page_size: 100,
    search: searchQuery || undefined,
  });
  const { data: leadsData, isLoading: isLoadingLeads } = useLeads({
    page_size: 100,
    search: searchQuery || undefined,
  });

  const existingContactIds = useMemo(
    () => new Set(existingMemberIds.contacts),
    [existingMemberIds.contacts]
  );
  const existingLeadIds = useMemo(
    () => new Set(existingMemberIds.leads),
    [existingMemberIds.leads]
  );

  const availableContacts = useMemo(
    () => (contactsData?.items ?? []).filter((c) => !existingContactIds.has(c.id)),
    [contactsData, existingContactIds]
  );

  const availableLeads = useMemo(
    () => (leadsData?.items ?? []).filter((l) => !existingLeadIds.has(l.id)),
    [leadsData, existingLeadIds]
  );

  const isLoadingItems = memberType === 'contact' ? isLoadingContacts : isLoadingLeads;

  const handleSubmit = async () => {
    if (selectedIds.length === 0) return;
    await onAdd(memberType, selectedIds as number[]);
  };

  const handleTypeChange = (type: MemberType) => {
    setMemberType(type);
    setSelectedIds([]);
    setSearchQuery('');
  };

  const renderContact = (item: Contact, _isSelected: boolean) => {
    const name = item.full_name || `${item.first_name} ${item.last_name}`;
    const email = item.email || '-';
    const extra = item.company?.name;
    return (
      <div className="flex-1 min-w-0">
        <p className="font-medium text-gray-900 truncate">{name}</p>
        <p className="text-xs sm:text-sm text-gray-500 truncate">
          {email}{extra && ` - ${extra}`}
        </p>
      </div>
    );
  };

  const renderLead = (item: Lead, _isSelected: boolean) => {
    const name = `${item.first_name} ${item.last_name}`;
    const email = item.email || '-';
    const extra = item.company_name;
    return (
      <div className="flex-1 min-w-0">
        <p className="font-medium text-gray-900 truncate">{name}</p>
        <p className="text-xs sm:text-sm text-gray-500 truncate">
          {email}{extra && ` - ${extra}`}
        </p>
      </div>
    );
  };

  return (
    <Modal isOpen onClose={onClose} title="Add Campaign Members" size="xl" fullScreenOnMobile>
      {/* Member Type Tabs */}
      <div className="flex space-x-2 sm:space-x-4 mb-4">
        <button
          type="button"
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
          type="button"
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

      {/* Truncation banners */}
      {memberType === 'contact' && contactsData?.total != null && contactsData.total > availableContacts.length && (
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
          Showing {availableContacts.length} of {contactsData.total} contacts. Use search to narrow down.
        </p>
      )}
      {memberType === 'lead' && leadsData?.total != null && leadsData.total > availableLeads.length && (
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-2">
          Showing {availableLeads.length} of {leadsData.total} leads. Use search to narrow down.
        </p>
      )}

      {memberType === 'contact' ? (
        <ScrollableListPicker<Contact>
          items={availableContacts}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          getItemId={(c) => c.id}
          renderItem={renderContact}
          searchPlaceholder="Search contacts..."
          filterFn={(c, q) => {
            const name = (c.full_name || `${c.first_name} ${c.last_name}`).toLowerCase();
            return name.includes(q.toLowerCase()) || (c.email ?? '').toLowerCase().includes(q.toLowerCase());
          }}
          isLoading={isLoadingItems}
          emptyMessage="No contacts available to add."
        />
      ) : (
        <ScrollableListPicker<Lead>
          items={availableLeads}
          selectedIds={selectedIds}
          onSelectionChange={setSelectedIds}
          getItemId={(l) => l.id}
          renderItem={renderLead}
          searchPlaceholder="Search leads..."
          filterFn={(l, q) => {
            const name = `${l.first_name} ${l.last_name}`.toLowerCase();
            return name.includes(q.toLowerCase()) || (l.email ?? '').toLowerCase().includes(q.toLowerCase());
          }}
          isLoading={isLoadingItems}
          emptyMessage="No leads available to add."
        />
      )}

      <ModalFooter>
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
      </ModalFooter>
    </Modal>
  );
}

export default AddMembersModal;
