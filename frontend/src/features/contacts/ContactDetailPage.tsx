import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Button, Spinner, Modal, ConfirmDialog } from '../../components/ui';
import { NotesList } from '../../components/shared';
import { ContactForm, ContactFormData } from './components/ContactForm';
import { AIInsightsCard, NextBestActionCard } from '../../components/ai';
import { useContact, useDeleteContact, useUpdateContact } from '../../hooks';
import { useTimeline } from '../../hooks/useActivities';
import { formatDate, formatPhoneNumber } from '../../utils/formatters';
import type { ContactUpdate } from '../../types';
import clsx from 'clsx';

type TabType = 'details' | 'activities' | 'notes';

function ContactDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const contactId = id ? parseInt(id, 10) : undefined;
  const [activeTab, setActiveTab] = useState<TabType>('details');
  const [showEditForm, setShowEditForm] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Use hooks for data fetching
  const { data: contact, isLoading, error } = useContact(contactId);
  const deleteContactMutation = useDeleteContact();
  const updateContactMutation = useUpdateContact();

  // Fetch timeline/activities for the contact - only fetch when on activities tab
  const shouldFetchActivities = activeTab === 'activities' && !!contactId;
  const { data: timelineData, isLoading: isLoadingActivities } = useTimeline(
    shouldFetchActivities ? 'contact' : '',
    shouldFetchActivities ? contactId! : 0
  );

  const activities = timelineData?.items || [];

  const handleEditSubmit = async (data: ContactFormData) => {
    if (!contactId) return;
    try {
      const updateData: ContactUpdate = {
        first_name: data.firstName,
        last_name: data.lastName,
        email: data.email,
        phone: data.phone,
        job_title: data.jobTitle,
      };
      await updateContactMutation.mutateAsync({
        id: contactId,
        data: updateData,
      });
      setShowEditForm(false);
    } catch (err) {
      console.error('Failed to update contact:', err);
    }
  };

  const getInitialFormData = (): Partial<ContactFormData> | undefined => {
    if (!contact) return undefined;
    return {
      firstName: contact.first_name,
      lastName: contact.last_name,
      email: contact.email || '',
      phone: contact.phone || '',
      jobTitle: contact.job_title || '',
      company: contact.company?.name || '',
    };
  };

  const handleDeleteConfirm = async () => {
    if (!contactId) return;

    try {
      await deleteContactMutation.mutateAsync(contactId);
      navigate('/contacts');
    } catch {
      // Error is handled by the mutation
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  const errorMessage = error instanceof Error ? error.message : error ? String(error) : null;

  if (errorMessage || !contact) {
    return (
      <div className="rounded-md bg-red-50 p-4">
        <div className="flex">
          <div className="ml-3">
            <h3 className="text-sm font-medium text-red-800">
              {errorMessage || 'Contact not found'}
            </h3>
            <div className="mt-4">
              <Link to="/contacts" className="text-red-600 hover:text-red-500">
                Back to contacts
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const tabs: { id: TabType; name: string }[] = [
    { id: 'details', name: 'Details' },
    { id: 'activities', name: 'Activities' },
    { id: 'notes', name: 'Notes' },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center space-x-4">
          <Link
            to="/contacts"
            className="text-gray-400 hover:text-gray-500 flex-shrink-0"
          >
            <svg
              className="h-6 w-6"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10 19l-7-7m0 0l7-7m-7 7h18"
              />
            </svg>
          </Link>
          <div className="min-w-0">
            <h1 className="text-xl sm:text-2xl font-bold text-gray-900 truncate">
              {contact.first_name} {contact.last_name}
            </h1>
            {contact.job_title && contact.company?.name && (
              <p className="text-sm text-gray-500 truncate">
                {contact.job_title} at {contact.company.name}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 w-full sm:w-auto">
          <Button
            variant="secondary"
            onClick={() => setShowEditForm(true)}
            className="flex-1 sm:flex-none"
          >
            Edit
          </Button>
          <Button
            variant="danger"
            onClick={() => setShowDeleteConfirm(true)}
            isLoading={deleteContactMutation.isPending}
            className="flex-1 sm:flex-none"
          >
            Delete
          </Button>
        </div>
      </div>

      {/* AI Suggestions */}
      <NextBestActionCard entityType="contact" entityId={contact.id} />
      <AIInsightsCard entityType="lead" entityId={contact.id} variant="inline" entityName={`${contact.first_name} ${contact.last_name}`} />

      {/* Tabs */}
      <div className="border-b border-gray-200 overflow-x-auto">
        <nav className="-mb-px flex space-x-4 sm:space-x-8 min-w-max px-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                'whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm flex-shrink-0',
                activeTab === tab.id
                  ? 'border-primary-500 text-primary-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              )}
            >
              {tab.name}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab Content */}
      {activeTab === 'details' && (
        <div className="bg-white shadow rounded-lg">
          <div className="p-4 sm:p-6">
            <dl className="grid grid-cols-1 gap-4 sm:gap-x-4 sm:gap-y-6 sm:grid-cols-2">
              <div>
                <dt className="text-sm font-medium text-gray-500">Email</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  <a
                    href={`mailto:${contact.email}`}
                    className="text-primary-600 hover:text-primary-500"
                  >
                    {contact.email}
                  </a>
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Phone</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {contact.phone ? (
                    <a
                      href={`tel:${contact.phone}`}
                      className="text-primary-600 hover:text-primary-500"
                    >
                      {formatPhoneNumber(contact.phone)}
                    </a>
                  ) : (
                    '-'
                  )}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Company</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {contact.company?.name || '-'}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Job Title</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {contact.job_title || '-'}
                </dd>
              </div>

              <div className="sm:col-span-2">
                <dt className="text-sm font-medium text-gray-500">Address</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {contact.address_line1 ? (
                    <>
                      {contact.address_line1}
                      {contact.address_line2 && <><br />{contact.address_line2}</>}
                      <br />
                      {[contact.city, contact.state, contact.postal_code]
                        .filter(Boolean)
                        .join(', ')}
                      {contact.country && (
                        <>
                          <br />
                          {contact.country}
                        </>
                      )}
                    </>
                  ) : (
                    '-'
                  )}
                </dd>
              </div>

              <div className="sm:col-span-2">
                <dt className="text-sm font-medium text-gray-500">Notes</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {contact.description || 'No notes'}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Created</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {formatDate(contact.created_at)}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">
                  Last Updated
                </dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {formatDate(contact.updated_at)}
                </dd>
              </div>
            </dl>
          </div>
        </div>
      )}

      {activeTab === 'activities' && (
        <div className="bg-white shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            {isLoadingActivities ? (
              <div className="flex items-center justify-center py-4">
                <Spinner />
              </div>
            ) : activities.length === 0 ? (
              <p className="text-sm text-gray-500 text-center py-4">
                No activities recorded yet.
              </p>
            ) : (
              <ul className="space-y-4">
                {activities.map((activity) => (
                  <li
                    key={activity.id}
                    className="flex items-start space-x-3 pb-4 border-b border-gray-100 last:border-0"
                  >
                    <div className="flex-shrink-0">
                      <div className="h-8 w-8 rounded-full bg-primary-100 flex items-center justify-center">
                        <svg
                          className="h-4 w-4 text-primary-600"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                          />
                        </svg>
                      </div>
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-gray-900">
                        {activity.subject}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        {formatDate(activity.created_at)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {activeTab === 'notes' && contactId && (
        <NotesList entityType="contact" entityId={contactId} />
      )}

      {/* Edit Form Modal */}
      <Modal
        isOpen={showEditForm}
        onClose={() => setShowEditForm(false)}
        title="Edit Contact"
        size="lg"
      >
        <ContactForm
          initialData={getInitialFormData()}
          onSubmit={handleEditSubmit}
          onCancel={() => setShowEditForm(false)}
          isLoading={updateContactMutation.isPending}
          submitLabel="Update Contact"
        />
      </Modal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleDeleteConfirm}
        title="Delete Contact"
        message={`Are you sure you want to delete ${contact.first_name} ${contact.last_name}? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteContactMutation.isPending}
      />
    </div>
  );
}

export default ContactDetailPage;
