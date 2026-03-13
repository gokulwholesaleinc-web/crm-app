import { useState, useEffect } from 'react';
import { Link, useSearchParams, useNavigate } from 'react-router-dom';
import { PlusIcon, FunnelIcon, BookmarkIcon, XMarkIcon } from '@heroicons/react/24/outline';
import { Button, Modal, ConfirmDialog } from '../../components/ui';
import { SkeletonTable } from '../../components/ui/Skeleton';
import { DuplicateWarningModal } from '../../components/shared/DuplicateWarningModal';
import { ContactForm, ContactFormData } from './components/ContactForm';
import { SmartListBuilder } from './components/SmartListBuilder';
import { useContacts, useCreateContact, useUpdateContact, useDeleteContact } from '../../hooks/useContacts';
import { useCheckDuplicates } from '../../hooks/useDedup';
import { useSavedFilters, useDeleteSavedFilter } from '../../hooks/useFilters';
import { formatDate, formatPhoneNumber } from '../../utils/formatters';
import { usePageTitle } from '../../hooks/usePageTitle';
import { showSuccess, showError } from '../../utils/toast';
import type { Contact, ContactCreate, ContactUpdate } from '../../types';
import type { DuplicateMatch } from '../../api/dedup';
import type { FilterGroup } from '../../api/filters';

function ContactsPage() {
  usePageTitle('Contacts');
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchQuery, setSearchQuery] = useState(searchParams.get('search') || '');
  const [currentPage, setCurrentPage] = useState(1);
  const [showForm, setShowForm] = useState(false);
  const [editingContact, setEditingContact] = useState<Contact | null>(null);
  const [showSmartListBuilder, setShowSmartListBuilder] = useState(false);
  const [activeFilters, setActiveFilters] = useState<FilterGroup | null>(null);
  const [activeSmartListName, setActiveSmartListName] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ isOpen: boolean; contact: Contact | null }>({
    isOpen: false,
    contact: null,
  });
  const [pageSize, setPageSize] = useState(25);
  const [pendingFormData, setPendingFormData] = useState<ContactFormData | null>(null);
  const [duplicateResults, setDuplicateResults] = useState<DuplicateMatch[]>([]);
  const [showDuplicateWarning, setShowDuplicateWarning] = useState(false);

  // Fetch saved smart lists
  const { data: savedFilters } = useSavedFilters('contacts');
  const deleteFilterMutation = useDeleteSavedFilter();

  // Handle URL query parameters for auto-opening form (e.g., from company detail page)
  useEffect(() => {
    const action = searchParams.get('action');

    if (action === 'new') {
      setShowForm(true);
      // Clear the action from URL to prevent re-opening on refresh
      const newParams = new URLSearchParams(searchParams);
      newParams.delete('action');
      setSearchParams(newParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  // Use the hooks for data fetching
  const {
    data: contactsData,
    isLoading,
    error,
  } = useContacts({
    page: currentPage,
    page_size: pageSize,
    search: searchQuery || undefined,
    ...(activeFilters ? { filters: JSON.stringify(activeFilters) } : {}),
  });

  const createContactMutation = useCreateContact();
  const updateContactMutation = useUpdateContact();
  const deleteContactMutation = useDeleteContact();
  const checkDuplicatesMutation = useCheckDuplicates();

  const contacts = contactsData?.items ?? [];
  const totalPages = contactsData?.pages ?? 1;
  const total = contactsData?.total ?? 0;

  const handleDeleteClick = (contact: Contact) => {
    setDeleteConfirm({ isOpen: true, contact });
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm.contact) return;
    try {
      await deleteContactMutation.mutateAsync(deleteConfirm.contact.id);
      setDeleteConfirm({ isOpen: false, contact: null });
      showSuccess('Contact deleted successfully');
    } catch (err) {
      showError('Failed to delete contact');
    }
  };

  const handleDeleteCancel = () => {
    setDeleteConfirm({ isOpen: false, contact: null });
  };

  const handleEdit = (contact: Contact) => {
    setEditingContact(contact);
    setShowForm(true);
  };

  const doCreateContact = async (data: ContactFormData) => {
    const createData: ContactCreate = {
      first_name: data.firstName,
      last_name: data.lastName,
      email: data.email,
      phone: data.phone,
      job_title: data.jobTitle,
      company_id: data.company_id ?? undefined,
      status: 'active',
    };
    await createContactMutation.mutateAsync(createData);
    showSuccess('Contact created successfully');
    setShowForm(false);
    setEditingContact(null);
    setPendingFormData(null);
  };

  const handleFormSubmit = async (data: ContactFormData) => {
    try {
      if (editingContact) {
        const updateData: ContactUpdate = {
          first_name: data.firstName,
          last_name: data.lastName,
          email: data.email,
          phone: data.phone,
          job_title: data.jobTitle,
          company_id: data.company_id ?? undefined,
        };
        await updateContactMutation.mutateAsync({
          id: editingContact.id,
          data: updateData,
        });
        showSuccess('Contact updated successfully');
        setShowForm(false);
        setEditingContact(null);
      } else {
        // Check for duplicates before creating
        const result = await checkDuplicatesMutation.mutateAsync({
          entityType: 'contacts',
          data: {
            first_name: data.firstName,
            last_name: data.lastName,
            email: data.email,
            phone: data.phone,
          },
        });
        if (result.has_duplicates) {
          setPendingFormData(data);
          setDuplicateResults(result.duplicates);
          setShowDuplicateWarning(true);
          return;
        }
        await doCreateContact(data);
      }
    } catch (err) {
      showError('Failed to save contact');
    }
  };

  const handleCreateAnyway = async () => {
    if (!pendingFormData) return;
    setShowDuplicateWarning(false);
    try {
      await doCreateContact(pendingFormData);
    } catch {
      showError('Failed to create contact');
    }
  };

  const handleViewDuplicate = (id: number) => {
    setShowDuplicateWarning(false);
    setShowForm(false);
    setPendingFormData(null);
    navigate(`/contacts/${id}`);
  };

  const handleFormCancel = () => {
    setShowForm(false);
    setEditingContact(null);
  };

  const getInitialFormData = (): Partial<ContactFormData> | undefined => {
    if (!editingContact) return undefined;
    return {
      firstName: editingContact.first_name,
      lastName: editingContact.last_name,
      email: editingContact.email || '',
      phone: editingContact.phone || '',
      jobTitle: editingContact.job_title || '',
      company_id: editingContact.company_id ?? null,
    };
  };

  const handleApplySmartListFilters = (filters: FilterGroup) => {
    setActiveFilters(filters);
    setActiveSmartListName(null);
    setCurrentPage(1);
    setShowSmartListBuilder(false);
  };

  const handleSelectSavedFilter = (filter: { name: string; filters: FilterGroup }) => {
    setActiveFilters(filter.filters);
    setActiveSmartListName(filter.name);
    setCurrentPage(1);
  };

  const handleClearFilters = () => {
    setActiveFilters(null);
    setActiveSmartListName(null);
    setCurrentPage(1);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Contacts</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Manage your contacts and relationships
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            leftIcon={<FunnelIcon className="h-5 w-5" />}
            onClick={() => setShowSmartListBuilder(true)}
            className="w-full sm:w-auto"
          >
            Build Smart List
          </Button>
          <Button
            leftIcon={<PlusIcon className="h-5 w-5" />}
            onClick={() => setShowForm(true)}
            className="w-full sm:w-auto"
          >
            Add Contact
          </Button>
        </div>
      </div>

      {/* Saved Smart Lists */}
      {savedFilters && savedFilters.length > 0 && (
        <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4 border border-transparent dark:border-gray-700">
          <div className="flex items-center gap-2 mb-3">
            <BookmarkIcon className="h-4 w-4 text-gray-500 dark:text-gray-400" />
            <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Smart Lists</h3>
          </div>
          <div className="flex flex-wrap gap-2">
            {savedFilters.map((filter) => (
              <div key={filter.id} className="flex items-center gap-1">
                <button
                  onClick={() => handleSelectSavedFilter(filter)}
                  className={`px-3 py-1.5 text-sm rounded-full border transition-colors ${
                    activeSmartListName === filter.name
                      ? 'bg-primary-100 dark:bg-primary-900/30 text-primary-800 dark:text-primary-200 border-primary-300 dark:border-primary-700'
                      : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 border-gray-200 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600'
                  }`}
                >
                  {filter.name}
                  {filter.is_public && (
                    <span className="ml-1 text-xs text-gray-400">(shared)</span>
                  )}
                </button>
                {filter.user_id && (
                  <button
                    onClick={async () => {
                      try {
                        await deleteFilterMutation.mutateAsync(filter.id);
                        if (activeSmartListName === filter.name) {
                          handleClearFilters();
                        }
                        showSuccess('Smart list deleted');
                      } catch {
                        showError('Failed to delete smart list');
                      }
                    }}
                    className="p-0.5 text-gray-400 hover:text-red-500 rounded"
                    aria-label={`Delete ${filter.name} smart list`}
                  >
                    <XMarkIcon className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Active Filter Banner */}
      {activeFilters && (
        <div className="flex items-center gap-2 px-4 py-2 bg-primary-50 dark:bg-primary-900/20 border border-primary-200 dark:border-primary-800 rounded-lg">
          <FunnelIcon className="h-4 w-4 text-primary-600 dark:text-primary-400" />
          <span className="text-sm text-primary-800 dark:text-primary-200 font-medium">
            {activeSmartListName ? `Smart List: ${activeSmartListName}` : 'Custom filters applied'}
          </span>
          <span className="text-sm text-primary-600 dark:text-primary-400">
            ({total} result{total !== 1 ? 's' : ''})
          </span>
          <button
            onClick={handleClearFilters}
            className="ml-auto text-sm text-primary-600 dark:text-primary-400 hover:text-primary-800 dark:hover:text-primary-200 font-medium"
          >
            Clear filters
          </button>
        </div>
      )}

      {/* Search and Filters */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg p-4 border border-transparent dark:border-gray-700">
        <div className="flex flex-col gap-3 sm:flex-row sm:gap-4">
          <div className="flex-1">
            <label htmlFor="search" className="sr-only">
              Search contacts
            </label>
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <svg
                  className="h-5 w-5 text-gray-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                  />
                </svg>
              </div>
              <input
                type="search"
                name="search"
                id="search"
                value={searchQuery}
                onChange={(e) => { setSearchQuery(e.target.value); setCurrentPage(1); }}
                className="block w-full pl-10 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md leading-5 bg-white dark:bg-gray-700 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus-visible:outline-none focus-visible:placeholder-gray-400 focus-visible:ring-1 focus-visible:ring-primary-500 focus-visible:border-primary-500 text-sm"
                placeholder="Search by name, email, or company..."
              />
            </div>
          </div>
        </div>
      </div>

      {/* Error Message */}
      {error && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
          <div className="flex">
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800 dark:text-red-300">
                {error instanceof Error ? error.message : 'An error occurred'}
              </h3>
            </div>
          </div>
        </div>
      )}

      {/* Delete Error Message */}
      {deleteContactMutation.isError && (
        <div className="rounded-md bg-red-50 dark:bg-red-900/20 p-4">
          <div className="flex">
            <div className="ml-3">
              <h3 className="text-sm font-medium text-red-800 dark:text-red-300">
                Failed to delete contact
              </h3>
            </div>
          </div>
        </div>
      )}

      {/* Contacts Table */}
      <div className="bg-white dark:bg-gray-800 shadow rounded-lg overflow-hidden border border-transparent dark:border-gray-700">
        {isLoading ? (
          <SkeletonTable rows={5} cols={8} />
        ) : contacts.length === 0 ? (
          <div className="text-center py-12">
            <svg
              className="mx-auto h-12 w-12 text-gray-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
              />
            </svg>
            <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-gray-100">No contacts</h3>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {activeFilters
                ? 'No contacts match the current filters.'
                : 'Get started by creating a new contact.'}
            </p>
            <div className="mt-6 flex justify-center gap-2">
              {activeFilters && (
                <Button variant="secondary" onClick={handleClearFilters}>
                  Clear Filters
                </Button>
              )}
              <Button onClick={() => setShowForm(true)}>Add Contact</Button>
            </div>
          </div>
        ) : (
          <>
            {/* Mobile Card View */}
            <div className="block md:hidden divide-y divide-gray-200 dark:divide-gray-700">
              {contacts.map((contact: Contact) => (
                <div key={contact.id} className="p-4 hover:bg-gray-50 dark:hover:bg-gray-700">
                  <div className="flex items-start justify-between">
                    <Link
                      to={`/contacts/${contact.id}`}
                      className="flex-1 min-w-0"
                    >
                      <p className="text-sm font-medium text-primary-600 hover:text-primary-900 dark:hover:text-primary-300 truncate">
                        {contact.first_name} {contact.last_name}
                      </p>
                      {contact.job_title && (
                        <p className="text-sm text-gray-500 dark:text-gray-400 truncate">{contact.job_title}</p>
                      )}
                    </Link>
                    <div className="flex items-center gap-2 ml-2 flex-shrink-0">
                      <button
                        onClick={() => handleEdit(contact)}
                        className="p-2 text-primary-600 hover:text-primary-900 dark:hover:text-primary-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDeleteClick(contact)}
                        className="p-2 text-red-600 hover:text-red-900 dark:hover:text-red-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-md"
                        disabled={deleteContactMutation.isPending}
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                  <div className="mt-2 space-y-1 text-sm text-gray-500 dark:text-gray-400">
                    {contact.email && <p className="truncate">{contact.email}</p>}
                    {contact.company?.name && (
                      <p className="truncate">
                        Company:{' '}
                        <Link
                          to={`/companies/${contact.company.id}`}
                          className="text-primary-600 hover:text-primary-500 focus-visible:underline focus-visible:outline-none"
                        >
                          {contact.company.name}
                        </Link>
                      </p>
                    )}
                    {contact.phone && <p>{formatPhoneNumber(contact.phone)}</p>}
                    {contact.mobile && contact.mobile !== contact.phone && (
                      <p>Mobile: {formatPhoneNumber(contact.mobile)}</p>
                    )}
                    {contact.department && <p>Dept: {contact.department}</p>}
                    {(contact.city || contact.state) && (
                      <p>{[contact.city, contact.state].filter(Boolean).join(', ')}</p>
                    )}
                    {contact.status && (
                      <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 capitalize">
                        {contact.status}
                      </span>
                    )}
                    <p className="text-xs text-gray-400 dark:text-gray-500">Created: {formatDate(contact.created_at)}</p>
                  </div>
                </div>
              ))}
            </div>

            {/* Desktop Table View */}
            <div className="hidden md:block overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                <thead className="bg-gray-50 dark:bg-gray-900">
                  <tr>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Name
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Email
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Company
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Phone
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Department
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Location
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Status
                    </th>
                    <th
                      scope="col"
                      className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider"
                    >
                      Created
                    </th>
                    <th scope="col" className="relative px-6 py-3">
                      <span className="sr-only">Actions</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                  {contacts.map((contact: Contact) => (
                    <tr key={contact.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <Link
                          to={`/contacts/${contact.id}`}
                          className="text-sm font-medium text-primary-600 hover:text-primary-900 dark:hover:text-primary-300"
                        >
                          {contact.first_name} {contact.last_name}
                        </Link>
                        {contact.job_title && (
                          <p className="text-sm text-gray-500 dark:text-gray-400">{contact.job_title}</p>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {contact.email || '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {contact.company ? (
                          <Link
                            to={`/companies/${contact.company.id}`}
                            className="text-primary-600 hover:text-primary-500"
                          >
                            {contact.company.name}
                          </Link>
                        ) : (
                          '-'
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        <div>{formatPhoneNumber(contact.phone)}</div>
                        {contact.mobile && contact.mobile !== contact.phone && (
                          <div className="text-xs text-gray-400 dark:text-gray-500">
                            M: {formatPhoneNumber(contact.mobile)}
                          </div>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {contact.department || '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {contact.city || contact.state
                          ? [contact.city, contact.state].filter(Boolean).join(', ')
                          : '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm">
                        {contact.status ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 capitalize">
                            {contact.status}
                          </span>
                        ) : '-'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                        {formatDate(contact.created_at)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <button
                          onClick={() => handleEdit(contact)}
                          className="text-primary-600 hover:text-primary-900 dark:hover:text-primary-300 mr-4"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDeleteClick(contact)}
                          className="text-red-600 hover:text-red-900 dark:hover:text-red-300"
                          disabled={deleteContactMutation.isPending}
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="bg-white dark:bg-gray-800 px-4 py-3 border-t border-gray-200 dark:border-gray-700 sm:px-6">
              {/* Mobile Pagination */}
              <div className="flex flex-col gap-3 sm:hidden">
                <div className="flex items-center justify-between">
                  <p className="text-sm text-gray-700 dark:text-gray-300">
                    Page {currentPage} of {totalPages} ({total} results)
                  </p>
                  <select
                    value={pageSize}
                    onChange={(e) => {
                      setPageSize(Number(e.target.value));
                      setCurrentPage(1);
                    }}
                    aria-label="Results per page"
                    className="text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 px-2 py-1"
                  >
                    <option value={10}>10 / page</option>
                    <option value={25}>25 / page</option>
                    <option value={50}>50 / page</option>
                    <option value={100}>100 / page</option>
                  </select>
                </div>
                <div className="flex justify-between gap-3">
                  <Button
                    variant="secondary"
                    onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                    disabled={currentPage === 1}
                    className="flex-1"
                  >
                    Previous
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                    disabled={currentPage === totalPages}
                    className="flex-1"
                  >
                    Next
                  </Button>
                </div>
              </div>
              {/* Desktop Pagination */}
              <div className="hidden sm:flex sm:items-center sm:justify-between">
                <div className="flex items-center gap-4">
                  <p className="text-sm text-gray-700 dark:text-gray-300">
                    Showing{' '}
                    <span className="font-medium">
                      {(currentPage - 1) * pageSize + 1}
                    </span>{' '}
                    to{' '}
                    <span className="font-medium">
                      {Math.min(currentPage * pageSize, total)}
                    </span>{' '}
                    of <span className="font-medium">{total}</span> results
                  </p>
                  <select
                    value={pageSize}
                    onChange={(e) => {
                      setPageSize(Number(e.target.value));
                      setCurrentPage(1);
                    }}
                    aria-label="Results per page"
                    className="text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 px-2 py-1"
                  >
                    <option value={10}>10 / page</option>
                    <option value={25}>25 / page</option>
                    <option value={50}>50 / page</option>
                    <option value={100}>100 / page</option>
                  </select>
                </div>
                <div>
                  <nav
                    className="relative z-0 inline-flex rounded-md shadow-sm -space-x-px"
                    aria-label="Pagination"
                  >
                    <button
                      onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                      disabled={currentPage === 1}
                      className="relative inline-flex items-center px-2 py-2 rounded-l-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm font-medium text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <span className="sr-only">Previous</span>
                      <svg
                        className="h-5 w-5"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path
                          fillRule="evenodd"
                          d="M12.707 5.293a1 1 0 010 1.414L9.414 10l3.293 3.293a1 1 0 01-1.414 1.414l-4-4a1 1 0 010-1.414l4-4a1 1 0 011.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                    </button>
                    <span className="relative inline-flex items-center px-4 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm font-medium text-gray-700 dark:text-gray-300">
                      Page {currentPage} of {totalPages}
                    </span>
                    <button
                      onClick={() =>
                        setCurrentPage((p) => Math.min(totalPages, p + 1))
                      }
                      disabled={currentPage === totalPages}
                      className="relative inline-flex items-center px-2 py-2 rounded-r-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-sm font-medium text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-600 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <span className="sr-only">Next</span>
                      <svg
                        className="h-5 w-5"
                        fill="currentColor"
                        viewBox="0 0 20 20"
                      >
                        <path
                          fillRule="evenodd"
                          d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z"
                          clipRule="evenodd"
                        />
                      </svg>
                    </button>
                  </nav>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Smart List Builder Modal */}
      <Modal
        isOpen={showSmartListBuilder}
        onClose={() => setShowSmartListBuilder(false)}
        title="Build Smart List"
        size="lg"
      >
        <SmartListBuilder
          entityType="contacts"
          onApplyFilters={handleApplySmartListFilters}
          onClose={() => setShowSmartListBuilder(false)}
        />
      </Modal>

      {/* Form Modal */}
      <Modal
        isOpen={showForm}
        onClose={handleFormCancel}
        title={editingContact ? 'Edit Contact' : 'Add Contact'}
        size="lg"
      >
        <ContactForm
          initialData={getInitialFormData()}
          onSubmit={handleFormSubmit}
          onCancel={handleFormCancel}
          isLoading={
            createContactMutation.isPending || updateContactMutation.isPending
          }
          submitLabel={editingContact ? 'Update Contact' : 'Create Contact'}
        />
      </Modal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={deleteConfirm.isOpen}
        onClose={handleDeleteCancel}
        onConfirm={handleDeleteConfirm}
        title="Delete Contact"
        message={`Are you sure you want to delete ${deleteConfirm.contact?.first_name} ${deleteConfirm.contact?.last_name}? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteContactMutation.isPending}
      />

      {/* Duplicate Warning Modal */}
      <DuplicateWarningModal
        isOpen={showDuplicateWarning}
        onClose={() => { setShowDuplicateWarning(false); setPendingFormData(null); }}
        onCreateAnyway={handleCreateAnyway}
        onViewDuplicate={handleViewDuplicate}
        duplicates={duplicateResults}
        entityType="contacts"
      />
    </div>
  );
}

export default ContactsPage;
