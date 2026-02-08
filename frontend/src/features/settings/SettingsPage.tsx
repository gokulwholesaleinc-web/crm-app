/**
 * Settings page with user profile, AI preferences, pipeline stage management,
 * lead source management, and account settings sections.
 */

import { useState } from 'react';
import { useAuthStore } from '../../store/authStore';
import { Card, CardHeader, CardBody } from '../../components/ui/Card';
import { Avatar } from '../../components/ui/Avatar';
import { Spinner } from '../../components/ui/Spinner';
import { Button } from '../../components/ui/Button';
import {
  UserCircleIcon,
  Cog6ToothIcon,
  BellIcon,
  ShieldCheckIcon,
  PencilSquareIcon,
} from '@heroicons/react/24/outline';
import { EditProfileModal } from './components/EditProfileModal';
import { AIPreferencesSection } from './components/AIPreferencesSection';
import { PipelineStagesSection } from './components/PipelineStagesSection';
import { LeadSourcesSection } from './components/LeadSourcesSection';
import { WebhooksSection } from './components/WebhooksSection';
import { AssignmentRulesSection } from './components/AssignmentRulesSection';

function SettingsPage() {
  const { user, isLoading } = useAuthStore();
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="space-y-4 sm:space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900">Settings</h1>
        <p className="mt-1 text-xs sm:text-sm text-gray-500">
          Manage your account settings and preferences
        </p>
      </div>

      {/* User Profile Section */}
      <Card>
        <CardHeader
          title="Profile"
          description="Your personal information"
          action={
            <Button
              variant="secondary"
              size="sm"
              leftIcon={<PencilSquareIcon className="h-4 w-4" />}
              onClick={() => setIsEditModalOpen(true)}
            >
              Edit
            </Button>
          }
        />
        <CardBody className="p-4 sm:p-6">
          <div className="flex flex-col sm:flex-row sm:items-start gap-4 sm:space-x-6">
            <div className="flex justify-center sm:justify-start">
              <Avatar
                src={user?.avatar_url}
                name={user?.full_name}
                size="xl"
              />
            </div>
            <div className="flex-1 space-y-4">
              <div className="grid grid-cols-1 gap-3 sm:gap-4 sm:grid-cols-2">
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-500">
                    Full Name
                  </label>
                  <p className="mt-1 text-sm text-gray-900">
                    {user?.full_name || 'Not set'}
                  </p>
                </div>
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-500">
                    Email
                  </label>
                  <p className="mt-1 text-sm text-gray-900 break-all">
                    {user?.email || 'Not set'}
                  </p>
                </div>
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-500">
                    Phone
                  </label>
                  <p className="mt-1 text-sm text-gray-900">
                    {user?.phone || 'Not set'}
                  </p>
                </div>
                <div>
                  <label className="block text-xs sm:text-sm font-medium text-gray-500">
                    Job Title
                  </label>
                  <p className="mt-1 text-sm text-gray-900">
                    {user?.job_title || 'Not set'}
                  </p>
                </div>
              </div>
              <div>
                <label className="block text-xs sm:text-sm font-medium text-gray-500">
                  Member Since
                </label>
                <p className="mt-1 text-sm text-gray-900">
                  {user?.created_at
                    ? new Date(user.created_at).toLocaleDateString(undefined, {
                        year: 'numeric',
                        month: 'long',
                        day: 'numeric',
                      })
                    : 'Unknown'}
                </p>
              </div>
            </div>
          </div>
        </CardBody>
      </Card>

      {/* Edit Profile Modal */}
      {user && (
        <EditProfileModal
          isOpen={isEditModalOpen}
          onClose={() => setIsEditModalOpen(false)}
          initialData={{
            full_name: user.full_name || '',
            email: user.email || '',
            phone: user.phone || '',
            job_title: user.job_title || '',
          }}
        />
      )}

      {/* AI Preferences Section */}
      <AIPreferencesSection />

      {/* Pipeline Stages Section */}
      <PipelineStagesSection />

      {/* Lead Sources Section */}
      <LeadSourcesSection />

      {/* Webhooks Section */}
      <WebhooksSection />

      {/* Lead Auto-Assignment Section */}
      <AssignmentRulesSection />

      {/* Account Settings Section */}
      <Card>
        <CardHeader
          title="Account Settings"
          description="Manage your account preferences"
        />
        <CardBody className="p-4 sm:p-6">
          <div className="divide-y divide-gray-200">
            {/* Notification Settings */}
            <div className="py-3 sm:py-4 first:pt-0 last:pb-0">
              <div className="flex items-start sm:items-center gap-3 sm:space-x-4">
                <div className="flex-shrink-0">
                  <div className="h-9 w-9 sm:h-10 sm:w-10 rounded-lg bg-blue-100 flex items-center justify-center">
                    <BellIcon className="h-4 w-4 sm:h-5 sm:w-5 text-blue-600" />
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">
                    Notifications
                  </p>
                  <p className="text-xs sm:text-sm text-gray-500">
                    Configure email and push notification preferences
                  </p>
                </div>
                <div className="text-xs sm:text-sm text-gray-400 flex-shrink-0">Coming soon</div>
              </div>
            </div>

            {/* Security Settings */}
            <div className="py-3 sm:py-4 first:pt-0 last:pb-0">
              <div className="flex items-start sm:items-center gap-3 sm:space-x-4">
                <div className="flex-shrink-0">
                  <div className="h-9 w-9 sm:h-10 sm:w-10 rounded-lg bg-green-100 flex items-center justify-center">
                    <ShieldCheckIcon className="h-4 w-4 sm:h-5 sm:w-5 text-green-600" />
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">
                    Security
                  </p>
                  <p className="text-xs sm:text-sm text-gray-500">
                    Password, two-factor authentication, and sessions
                  </p>
                </div>
                <div className="text-xs sm:text-sm text-gray-400 flex-shrink-0">Coming soon</div>
              </div>
            </div>

            {/* Preferences */}
            <div className="py-3 sm:py-4 first:pt-0 last:pb-0">
              <div className="flex items-start sm:items-center gap-3 sm:space-x-4">
                <div className="flex-shrink-0">
                  <div className="h-9 w-9 sm:h-10 sm:w-10 rounded-lg bg-purple-100 flex items-center justify-center">
                    <Cog6ToothIcon className="h-4 w-4 sm:h-5 sm:w-5 text-purple-600" />
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">
                    Preferences
                  </p>
                  <p className="text-xs sm:text-sm text-gray-500">
                    Language, timezone, and display settings
                  </p>
                </div>
                <div className="text-xs sm:text-sm text-gray-400 flex-shrink-0">Coming soon</div>
              </div>
            </div>

            {/* Profile Settings */}
            <button
              type="button"
              className="w-full py-3 sm:py-4 first:pt-0 last:pb-0 text-left hover:bg-gray-50 -mx-4 sm:-mx-6 px-4 sm:px-6 transition-colors"
              onClick={() => setIsEditModalOpen(true)}
            >
              <div className="flex items-start sm:items-center gap-3 sm:space-x-4">
                <div className="flex-shrink-0">
                  <div className="h-9 w-9 sm:h-10 sm:w-10 rounded-lg bg-orange-100 flex items-center justify-center">
                    <UserCircleIcon className="h-4 w-4 sm:h-5 sm:w-5 text-orange-600" />
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900">
                    Edit Profile
                  </p>
                  <p className="text-xs sm:text-sm text-gray-500">
                    Update your personal information and avatar
                  </p>
                </div>
                <div className="text-xs sm:text-sm text-primary-600 font-medium flex-shrink-0">
                  Edit
                </div>
              </div>
            </button>
          </div>
        </CardBody>
      </Card>

      {/* Account Status */}
      <Card>
        <CardHeader
          title="Account Status"
          description="Your account information"
        />
        <CardBody className="p-4 sm:p-6">
          <div className="grid grid-cols-1 gap-3 sm:gap-4 sm:grid-cols-3">
            <div className="bg-gray-50 rounded-lg p-3 sm:p-4">
              <p className="text-xs sm:text-sm font-medium text-gray-500">Status</p>
              <p className="mt-1 flex items-center text-sm">
                <span
                  className={`inline-block h-2 w-2 rounded-full mr-2 ${
                    user?.is_active ? 'bg-green-500' : 'bg-red-500'
                  }`}
                />
                {user?.is_active ? 'Active' : 'Inactive'}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 sm:p-4">
              <p className="text-xs sm:text-sm font-medium text-gray-500">Role</p>
              <p className="mt-1 text-sm text-gray-900">
                {user?.is_superuser ? 'Administrator' : 'User'}
              </p>
            </div>
            <div className="bg-gray-50 rounded-lg p-3 sm:p-4">
              <p className="text-xs sm:text-sm font-medium text-gray-500">Last Login</p>
              <p className="mt-1 text-sm text-gray-900">
                {user?.last_login
                  ? new Date(user.last_login).toLocaleDateString(undefined, {
                      year: 'numeric',
                      month: 'short',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })
                  : 'Never'}
              </p>
            </div>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

export default SettingsPage;
