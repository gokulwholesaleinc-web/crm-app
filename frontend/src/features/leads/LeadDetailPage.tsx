import { useState, useEffect } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Button } from '../../components/ui/Button';
import { Spinner } from '../../components/ui/Spinner';
import { ConvertLeadModal } from './components/ConvertLeadModal';
import clsx from 'clsx';

interface Lead {
  id: string;
  firstName: string;
  lastName: string;
  email: string;
  phone?: string;
  company?: string;
  jobTitle?: string;
  source: string;
  status: string;
  score: number;
  notes?: string;
  createdAt: string;
  updatedAt: string;
}

const statusColors: Record<string, string> = {
  new: 'bg-blue-100 text-blue-800',
  contacted: 'bg-yellow-100 text-yellow-800',
  qualified: 'bg-green-100 text-green-800',
  unqualified: 'bg-red-100 text-red-800',
  nurturing: 'bg-purple-100 text-purple-800',
};

function getScoreColor(score: number): string {
  if (score >= 80) return 'text-green-600';
  if (score >= 60) return 'text-yellow-600';
  if (score >= 40) return 'text-orange-600';
  return 'text-red-600';
}

export function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [lead, setLead] = useState<Lead | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showConvertModal, setShowConvertModal] = useState(false);

  useEffect(() => {
    const fetchLead = async () => {
      try {
        const response = await fetch(`/api/leads/${id}`, {
          headers: {
            Authorization: `Bearer ${localStorage.getItem('access_token')}`,
          },
        });

        if (!response.ok) {
          throw new Error('Failed to fetch lead');
        }

        const data = await response.json();
        setLead(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An error occurred');
      } finally {
        setIsLoading(false);
      }
    };

    fetchLead();
  }, [id]);

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to delete this lead?')) {
      return;
    }

    try {
      const response = await fetch(`/api/leads/${id}`, {
        method: 'DELETE',
        headers: {
          Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        },
      });

      if (response.ok) {
        navigate('/leads');
      }
    } catch {
      setError('Failed to delete lead');
    }
  };

  const handleConvert = async (data: {
    createContact: boolean;
    createOpportunity: boolean;
    opportunityName?: string;
    opportunityValue?: number;
    opportunityStage?: string;
  }) => {
    try {
      const response = await fetch(`/api/leads/${id}/convert`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        },
        body: JSON.stringify({
          create_contact: data.createContact,
          create_opportunity: data.createOpportunity,
          opportunity_name: data.opportunityName,
          opportunity_value: data.opportunityValue,
          opportunity_stage: data.opportunityStage,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to convert lead');
      }

      const result = await response.json();

      // Navigate to the appropriate page based on what was created
      if (result.contact_id) {
        navigate(`/contacts/${result.contact_id}`);
      } else if (result.opportunity_id) {
        navigate(`/opportunities`);
      } else {
        navigate('/leads');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to convert lead');
      throw err;
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  if (error || !lead) {
    return (
      <div className="rounded-md bg-red-50 p-4">
        <div className="flex">
          <div className="ml-3">
            <h3 className="text-sm font-medium text-red-800">
              {error || 'Lead not found'}
            </h3>
            <div className="mt-4">
              <Link to="/leads" className="text-red-600 hover:text-red-500">
                Back to leads
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link to="/leads" className="text-gray-400 hover:text-gray-500">
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
              {lead.firstName} {lead.lastName}
            </h1>
            {lead.jobTitle && lead.company && (
              <p className="text-sm text-gray-500">
                {lead.jobTitle} at {lead.company}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center space-x-3">
          {lead.status === 'qualified' && (
            <Button onClick={() => setShowConvertModal(true)}>
              <svg
                className="h-5 w-5 mr-2"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              Convert Lead
            </Button>
          )}
          <Button
            variant="secondary"
            onClick={() => navigate(`/leads/${id}/edit`)}
          >
            Edit
          </Button>
          <Button variant="danger" onClick={handleDelete}>
            Delete
          </Button>
        </div>
      </div>

      {/* Lead Score Card */}
      <div className="bg-white shadow rounded-lg p-6">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-medium text-gray-900">Lead Score</h3>
            <p className="text-sm text-gray-500">
              Based on engagement and fit criteria
            </p>
          </div>
          <div className="flex items-center space-x-4">
            <div className="text-center">
              <div
                className={clsx(
                  'text-4xl font-bold',
                  getScoreColor(lead.score)
                )}
              >
                {lead.score}
              </div>
              <div className="text-sm text-gray-500">out of 100</div>
            </div>
            <div className="w-32 h-32 relative">
              <svg className="w-full h-full transform -rotate-90">
                <circle
                  cx="64"
                  cy="64"
                  r="56"
                  stroke="currentColor"
                  strokeWidth="8"
                  fill="none"
                  className="text-gray-200"
                />
                <circle
                  cx="64"
                  cy="64"
                  r="56"
                  stroke="currentColor"
                  strokeWidth="8"
                  fill="none"
                  strokeDasharray={`${(lead.score / 100) * 352} 352`}
                  className={clsx({
                    'text-green-500': lead.score >= 80,
                    'text-yellow-500': lead.score >= 60 && lead.score < 80,
                    'text-orange-500': lead.score >= 40 && lead.score < 60,
                    'text-red-500': lead.score < 40,
                  })}
                />
              </svg>
            </div>
          </div>
        </div>
      </div>

      {/* Lead Details */}
      <div className="bg-white shadow rounded-lg">
        <div className="px-4 py-5 sm:p-6">
          <h3 className="text-lg font-medium text-gray-900 mb-4">
            Lead Details
          </h3>
          <dl className="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2">
            <div>
              <dt className="text-sm font-medium text-gray-500">Email</dt>
              <dd className="mt-1 text-sm text-gray-900">
                <a
                  href={`mailto:${lead.email}`}
                  className="text-primary-600 hover:text-primary-500"
                >
                  {lead.email}
                </a>
              </dd>
            </div>

            <div>
              <dt className="text-sm font-medium text-gray-500">Phone</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {lead.phone ? (
                  <a
                    href={`tel:${lead.phone}`}
                    className="text-primary-600 hover:text-primary-500"
                  >
                    {lead.phone}
                  </a>
                ) : (
                  '-'
                )}
              </dd>
            </div>

            <div>
              <dt className="text-sm font-medium text-gray-500">Company</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {lead.company || '-'}
              </dd>
            </div>

            <div>
              <dt className="text-sm font-medium text-gray-500">Job Title</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {lead.jobTitle || '-'}
              </dd>
            </div>

            <div>
              <dt className="text-sm font-medium text-gray-500">Status</dt>
              <dd className="mt-1">
                <span
                  className={clsx(
                    'px-2 inline-flex text-xs leading-5 font-semibold rounded-full',
                    statusColors[lead.status] || 'bg-gray-100 text-gray-800'
                  )}
                >
                  {lead.status.charAt(0).toUpperCase() +
                    lead.status.slice(1).replace('_', ' ')}
                </span>
              </dd>
            </div>

            <div>
              <dt className="text-sm font-medium text-gray-500">Source</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {lead.source.charAt(0).toUpperCase() +
                  lead.source.slice(1).replace('_', ' ')}
              </dd>
            </div>

            <div className="sm:col-span-2">
              <dt className="text-sm font-medium text-gray-500">Notes</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {lead.notes || 'No notes'}
              </dd>
            </div>

            <div>
              <dt className="text-sm font-medium text-gray-500">Created</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {new Date(lead.createdAt).toLocaleDateString()}
              </dd>
            </div>

            <div>
              <dt className="text-sm font-medium text-gray-500">Last Updated</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {new Date(lead.updatedAt).toLocaleDateString()}
              </dd>
            </div>
          </dl>
        </div>
      </div>

      {/* Convert Lead Modal */}
      {showConvertModal && (
        <ConvertLeadModal
          leadId={lead.id}
          leadName={`${lead.firstName} ${lead.lastName}`}
          onClose={() => setShowConvertModal(false)}
          onConvert={handleConvert}
        />
      )}
    </div>
  );
}
