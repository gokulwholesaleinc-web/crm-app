import { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { Button, Spinner, Modal, ConfirmDialog } from '../../components/ui';
import { ConvertLeadModal } from './components/ConvertLeadModal';
import { LeadForm, LeadFormData } from './components/LeadForm';
import { getStatusBadgeClasses, formatStatusLabel } from '../../utils';
import { formatDate, formatPhoneNumber } from '../../utils/formatters';
import { useLead, useDeleteLead, useConvertLead, useUpdateLead } from '../../hooks';
import type { LeadUpdate } from '../../types';
import clsx from 'clsx';

function getScoreColor(score: number): string {
  if (score >= 80) return 'text-green-600';
  if (score >= 60) return 'text-yellow-600';
  if (score >= 40) return 'text-orange-600';
  return 'text-red-600';
}

function LeadDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const leadId = id ? parseInt(id, 10) : undefined;
  const [showConvertModal, setShowConvertModal] = useState(false);
  const [showEditForm, setShowEditForm] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Use hooks for data fetching
  const { data: lead, isLoading, error } = useLead(leadId);
  const deleteLeadMutation = useDeleteLead();
  const convertLeadMutation = useConvertLead();
  const updateLeadMutation = useUpdateLead();

  const handleEditSubmit = async (data: LeadFormData) => {
    if (!leadId) return;
    try {
      const updateData: LeadUpdate = {
        first_name: data.firstName,
        last_name: data.lastName,
        email: data.email,
        phone: data.phone || undefined,
        company_name: data.company || undefined,
        job_title: data.jobTitle || undefined,
        status: data.status,
      };
      await updateLeadMutation.mutateAsync({
        id: leadId,
        data: updateData,
      });
      setShowEditForm(false);
    } catch (err) {
      console.error('Failed to update lead:', err);
    }
  };

  const getInitialFormData = (): Partial<LeadFormData> | undefined => {
    if (!lead) return undefined;
    return {
      firstName: lead.first_name,
      lastName: lead.last_name,
      email: lead.email || '',
      phone: lead.phone || '',
      company: lead.company_name || '',
      jobTitle: lead.job_title || '',
      status: lead.status,
      source: lead.source?.name || '',
      notes: lead.description || '',
    };
  };

  const handleDeleteConfirm = async () => {
    if (!leadId) return;

    try {
      await deleteLeadMutation.mutateAsync(leadId);
      navigate('/leads');
    } catch {
      // Error handled by mutation
    }
  };

  const handleConvert = async (data: {
    createContact: boolean;
    createOpportunity: boolean;
    opportunityName?: string;
    opportunityValue?: number;
    opportunityStage?: string;
  }) => {
    if (!leadId) return;

    try {
      // Map stage string to stage ID (using default stage 1 for now)
      // In a production app, you'd fetch pipeline stages and map properly
      const stageMapping: Record<string, number> = {
        qualification: 1,
        proposal: 2,
        negotiation: 3,
        closed_won: 4,
        closed_lost: 5,
      };
      const stageId = data.opportunityStage ? (stageMapping[data.opportunityStage] || 1) : 1;

      const result = await convertLeadMutation.mutateAsync({
        leadId: leadId,
        data: {
          pipeline_stage_id: stageId,
          create_company: data.createContact,
        },
      });

      // Navigate to the appropriate page based on what was created
      if (result.contact_id) {
        navigate(`/contacts/${result.contact_id}`);
      } else if (result.opportunity_id) {
        navigate(`/opportunities`);
      } else {
        navigate('/leads');
      }
    } catch {
      // Error handled by mutation
      throw new Error('Failed to convert lead');
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

  if (errorMessage || !lead) {
    return (
      <div className="rounded-md bg-red-50 p-4">
        <div className="flex">
          <div className="ml-3">
            <h3 className="text-sm font-medium text-red-800">
              {errorMessage || 'Lead not found'}
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
              {lead.first_name} {lead.last_name}
            </h1>
            {lead.job_title && lead.company_name && (
              <p className="text-sm text-gray-500">
                {lead.job_title} at {lead.company_name}
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
            onClick={() => setShowEditForm(true)}
          >
            Edit
          </Button>
          <Button variant="danger" onClick={() => setShowDeleteConfirm(true)} isLoading={deleteLeadMutation.isPending}>
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
                    {formatPhoneNumber(lead.phone)}
                  </a>
                ) : (
                  '-'
                )}
              </dd>
            </div>

            <div>
              <dt className="text-sm font-medium text-gray-500">Company</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {lead.company_name || '-'}
              </dd>
            </div>

            <div>
              <dt className="text-sm font-medium text-gray-500">Job Title</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {lead.job_title || '-'}
              </dd>
            </div>

            <div>
              <dt className="text-sm font-medium text-gray-500">Status</dt>
              <dd className="mt-1">
                <span className={getStatusBadgeClasses(lead.status, 'lead')}>
                  {formatStatusLabel(lead.status)}
                </span>
              </dd>
            </div>

            <div>
              <dt className="text-sm font-medium text-gray-500">Source</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {lead.source?.name ? formatStatusLabel(lead.source.name) : '-'}
              </dd>
            </div>

            <div className="sm:col-span-2">
              <dt className="text-sm font-medium text-gray-500">Description</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {lead.description || 'No description'}
              </dd>
            </div>

            <div>
              <dt className="text-sm font-medium text-gray-500">Created</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {formatDate(lead.created_at)}
              </dd>
            </div>

            <div>
              <dt className="text-sm font-medium text-gray-500">Last Updated</dt>
              <dd className="mt-1 text-sm text-gray-900">
                {formatDate(lead.updated_at)}
              </dd>
            </div>
          </dl>
        </div>
      </div>

      {/* Convert Lead Modal */}
      <ConvertLeadModal
        isOpen={showConvertModal}
        leadId={String(lead.id)}
        leadName={`${lead.first_name} ${lead.last_name}`}
        onClose={() => setShowConvertModal(false)}
        onConvert={handleConvert}
      />

      {/* Edit Form Modal */}
      <Modal
        isOpen={showEditForm}
        onClose={() => setShowEditForm(false)}
        title="Edit Lead"
        size="lg"
      >
        <LeadForm
          initialData={getInitialFormData()}
          onSubmit={handleEditSubmit}
          onCancel={() => setShowEditForm(false)}
          isLoading={updateLeadMutation.isPending}
          submitLabel="Update Lead"
        />
      </Modal>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={handleDeleteConfirm}
        title="Delete Lead"
        message={`Are you sure you want to delete ${lead.first_name} ${lead.last_name}? This action cannot be undone.`}
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        isLoading={deleteLeadMutation.isPending}
      />
    </div>
  );
}

export default LeadDetailPage;
