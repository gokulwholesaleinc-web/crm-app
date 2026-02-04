import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import clsx from 'clsx';

interface Contact {
  id: string;
  firstName: string;
  lastName: string;
  email: string;
  phone?: string;
  company?: string;
  jobTitle?: string;
  address?: string;
  city?: string;
  state?: string;
  zipCode?: string;
  country?: string;
  notes?: string;
  createdAt: string;
  updatedAt: string;
}

interface Activity {
  id: string;
  type: string;
  description: string;
  timestamp: string;
  user: {
    firstName: string;
    lastName: string;
  };
}

interface Note {
  id: string;
  content: string;
  createdAt: string;
  user: {
    firstName: string;
    lastName: string;
  };
}

type TabType = 'details' | 'activities' | 'notes';

export function ContactDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [contact, setContact] = useState<Contact | null>(null);
  const [activities, setActivities] = useState<Activity[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [activeTab, setActiveTab] = useState<TabType>('details');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newNote, setNewNote] = useState('');
  const [isAddingNote, setIsAddingNote] = useState(false);

  useEffect(() => {
    const fetchContact = async () => {
      try {
        const response = await fetch(`/api/contacts/${id}`, {
          headers: {
            Authorization: `Bearer ${localStorage.getItem('access_token')}`,
          },
        });

        if (!response.ok) {
          throw new Error('Failed to fetch contact');
        }

        const data = await response.json();
        setContact(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        setIsLoading(false);
      }
    };

    fetchContact();
  }, [id]);

  useEffect(() => {
    if (activeTab === 'activities') {
      fetchActivities();
    } else if (activeTab === 'notes') {
      fetchNotes();
    }
  }, [activeTab, id]);

  const fetchActivities = async () => {
    try {
      const response = await fetch(`/api/contacts/${id}/activities`, {
        headers: {
          Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setActivities(data);
      }
    } catch {
      // Silent fail for activities
    }
  };

  const fetchNotes = async () => {
    try {
      const response = await fetch(`/api/contacts/${id}/notes`, {
        headers: {
          Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setNotes(data);
      }
    } catch {
      // Silent fail for notes
    }
  };

  const handleAddNote = async () => {
    if (!newNote.trim()) return;

    setIsAddingNote(true);
    try {
      const response = await fetch(`/api/contacts/${id}/notes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        },
        body: JSON.stringify({ content: newNote }),
      });

      if (response.ok) {
        setNewNote('');
        fetchNotes();
      }
    } catch {
      // Handle error
    } finally {
      setIsAddingNote(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this contact?')) {
      return;
    }

    try {
      const response = await fetch(`/api/contacts/${id}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        },
      });

      if (response.ok) {
        navigate('/contacts');
      }
    } catch {
      setError('Failed to delete contact');
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error || !contact) {
    return (
      <div className="rounded-md bg-red-50 p-4">
        <div className="flex">
          <div className="ml-3">
            <h3 className="text-sm font-medium text-red-800">
              {error || 'Contact not found'}
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
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link
            to="/contacts"
            className="text-gray-400 hover:text-gray-500"
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
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {contact.firstName} {contact.lastName}
            </h1>
            {contact.jobTitle && contact.company && (
              <p className="text-sm text-gray-500">
                {contact.jobTitle} at {contact.company}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center space-x-3">
          <Button
            variant="secondary"
            onClick={() => navigate(`/contacts/${id}/edit`)}
          >
            Edit
          </Button>
          <Button variant="danger" onClick={handleDelete}>
            Delete
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={clsx(
                'whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm',
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
          <div className="px-4 py-5 sm:p-6">
            <dl className="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2">
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
                      {contact.phone}
                    </a>
                  ) : (
                    '-'
                  )}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Company</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {contact.company || '-'}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Job Title</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {contact.jobTitle || '-'}
                </dd>
              </div>

              <div className="sm:col-span-2">
                <dt className="text-sm font-medium text-gray-500">Address</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {contact.address ? (
                    <>
                      {contact.address}
                      <br />
                      {[contact.city, contact.state, contact.zipCode]
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
                  {contact.notes || 'No notes'}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">Created</dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {new Date(contact.createdAt).toLocaleDateString()}
                </dd>
              </div>

              <div>
                <dt className="text-sm font-medium text-gray-500">
                  Last Updated
                </dt>
                <dd className="mt-1 text-sm text-gray-900">
                  {new Date(contact.updatedAt).toLocaleDateString()}
                </dd>
              </div>
            </dl>
          </div>
        </div>
      )}

      {activeTab === 'activities' && (
        <div className="bg-white shadow rounded-lg">
          <div className="px-4 py-5 sm:p-6">
            {activities.length === 0 ? (
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
                        {activity.description}
                      </p>
                      <p className="text-xs text-gray-500 mt-1">
                        {activity.user.firstName} {activity.user.lastName} -{' '}
                        {new Date(activity.timestamp).toLocaleString()}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {activeTab === 'notes' && (
        <div className="space-y-4">
          {/* Add Note Form */}
          <div className="bg-white shadow rounded-lg p-4">
            <div className="flex space-x-3">
              <div className="flex-1">
                <textarea
                  rows={3}
                  value={newNote}
                  onChange={(e) => setNewNote(e.target.value)}
                  className="block w-full rounded-md border-gray-300 shadow-sm focus:border-primary-500 focus:ring-primary-500 sm:text-sm"
                  placeholder="Add a note..."
                />
              </div>
            </div>
            <div className="mt-3 flex justify-end">
              <Button
                onClick={handleAddNote}
                isLoading={isAddingNote}
                disabled={!newNote.trim()}
              >
                Add Note
              </Button>
            </div>
          </div>

          {/* Notes List */}
          <div className="bg-white shadow rounded-lg">
            <div className="px-4 py-5 sm:p-6">
              {notes.length === 0 ? (
                <p className="text-sm text-gray-500 text-center py-4">
                  No notes yet. Add one above.
                </p>
              ) : (
                <ul className="space-y-4">
                  {notes.map((note) => (
                    <li
                      key={note.id}
                      className="pb-4 border-b border-gray-100 last:border-0"
                    >
                      <p className="text-sm text-gray-900 whitespace-pre-wrap">
                        {note.content}
                      </p>
                      <p className="text-xs text-gray-500 mt-2">
                        {note.user.firstName} {note.user.lastName} -{' '}
                        {new Date(note.createdAt).toLocaleString()}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
