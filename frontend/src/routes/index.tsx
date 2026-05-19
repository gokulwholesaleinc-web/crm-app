/**
 * Application route definitions with lazy loading for code splitting.
 */

import { lazy } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';

import { PrivateRoute } from './PrivateRoute';
import { ErrorBoundary } from '../components/ErrorBoundary';


// Lazy load all page components for code splitting
// Authentication pages
const LoginPage = lazy(() => import('../features/auth/LoginPage'));
const GoogleAuthCallbackPage = lazy(() => import('../features/auth/GoogleAuthCallbackPage'));

// Dashboard
const DashboardPage = lazy(() => import('../features/dashboard/DashboardPage'));

// Contacts
const ContactsPage = lazy(() => import('../features/contacts/ContactsPage'));
const ContactDetailPage = lazy(() => import('../features/contacts/ContactDetailPage'));

// Companies
const CompaniesPage = lazy(() => import('../features/companies/CompaniesPage'));
const CompanyDetailPage = lazy(() => import('../features/companies/CompanyDetailPage'));

// Leads
const LeadsPage = lazy(() => import('../features/leads/LeadsPage'));
const LeadDetailPage = lazy(() => import('../features/leads/LeadDetailPage'));

// Pipeline (lead kanban)
const PipelinePage = lazy(() => import('../features/pipeline/PipelinePage'));

// Quotes feature removed 2026-05-14 — replaced by one-off Payment invoices
// with optional PDF attachments. Backend tables preserved for historical data.

// Payments
const PaymentsPage = lazy(() => import('../features/payments/PaymentsPage'));
const PaymentDetailPage = lazy(() => import('../features/payments/PaymentDetail'));

// Proposals
const ProposalsPage = lazy(() => import('../features/proposals/ProposalsPage'));
const ProposalDetailPage = lazy(() => import('../features/proposals/ProposalDetail'));
const PublicProposalView = lazy(() => import('../features/proposals/PublicProposalView'));

// Contracts feature removed 2026-05-14 — contract terms folded into the
// Proposal T&C inline. Backend tables preserved for historical data.

// Activities
const ActivitiesPage = lazy(() => import('../features/activities/ActivitiesPage'));
const CalendarPage = lazy(() => import('../features/calendar/CalendarPage'));

// Campaigns
const CampaignsPage = lazy(() => import('../features/campaigns/CampaignsPage'));
const CampaignDetailPage = lazy(() => import('../features/campaigns/CampaignDetailPage'));

// AI Assistant

// Reports
const ReportsPage = lazy(() => import('../features/reports/ReportsPage'));

// Import/Export
const ImportExportPage = lazy(() => import('../features/import-export/ImportExportPage'));

// Inbox
const InboxPage = lazy(() => import('../features/inbox/InboxPage'));

// Settings
const SettingsPage = lazy(() => import('../features/settings/SettingsPage'));

// OAuth Callbacks
const OAuthCallbackPage = lazy(() => import('../features/settings/OAuthCallbackPage'));

// Admin
const AdminDashboardPage = lazy(() => import('../features/admin/AdminDashboard'));
const AdminAuditPage = lazy(() => import('../features/admin/AdminAuditPage'));
const UserApprovalsPage = lazy(() => import('../features/admin/UserApprovalsPage'));
const AdminSharingPage = lazy(() => import('../features/admin/AdminSharingPage'));
const AdminDedupPage = lazy(() => import('../features/admin/AdminDedupPage'));

// Help
const HelpPage = lazy(() => import('../features/help/HelpPage'));

// Duplicates

function AppRoutes() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/auth/google/callback" element={<GoogleAuthCallbackPage />} />
      <Route path="/proposals/public/:token" element={<PublicProposalView />} />
      {/* /quotes/public/:quoteNumber route removed 2026-05-14 */}
      {/* /contracts/sign/:token route removed 2026-05-14 — contracts retired */}

      {/* Protected routes */}
      <Route
        path="/"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <DashboardPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Contacts */}
      <Route
        path="/contacts"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <ContactsPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />
      <Route
        path="/contacts/:id"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <ContactDetailPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Companies */}
      <Route
        path="/companies"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <CompaniesPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />
      <Route
        path="/companies/:id"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <CompanyDetailPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Leads */}
      <Route
        path="/leads"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <LeadsPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />
      <Route
        path="/leads/:id"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <LeadDetailPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Pipeline (lead kanban) */}
      <Route
        path="/pipeline"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <PipelinePage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Quotes routes removed 2026-05-14 — replaced by one-off Payment
          invoices with optional PDF attachments. */}

      {/* Payments */}
      <Route
        path="/payments"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <PaymentsPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />
      <Route
        path="/payments/:id"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <PaymentDetailPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Proposals */}
      <Route
        path="/proposals"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <ProposalsPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />
      <Route
        path="/proposals/:id"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <ProposalDetailPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Contracts routes removed 2026-05-14 — contract terms now fold into
          the Proposal T&C inline. */}

      {/* Activities */}
      <Route
        path="/activities"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <ActivitiesPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Calendar */}
      <Route
        path="/calendar"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <CalendarPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Campaigns */}
      <Route
        path="/campaigns"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <CampaignsPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />
      <Route
        path="/campaigns/:id"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <CampaignDetailPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />


      {/* Reports */}
      <Route
        path="/reports"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <ReportsPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Import/Export */}
      <Route
        path="/import-export"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <ImportExportPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Inbox */}
      <Route
        path="/inbox"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <InboxPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Settings */}
      <Route
        path="/settings"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <SettingsPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Admin */}
      <Route
        path="/admin"
        element={
          <PrivateRoute allowedRoles={['admin']}>
            <ErrorBoundary>
              <AdminDashboardPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />
      <Route
        path="/admin/user-approvals"
        element={
          <PrivateRoute allowedRoles={['admin']}>
            <ErrorBoundary>
              <UserApprovalsPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />
      <Route
        path="/admin/audit"
        element={
          <PrivateRoute allowedRoles={['admin']}>
            <ErrorBoundary>
              <AdminAuditPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />
      <Route
        path="/admin/sharing"
        element={
          <PrivateRoute allowedRoles={['admin']}>
            <ErrorBoundary>
              <AdminSharingPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />
      <Route
        path="/admin/dedup"
        element={
          <PrivateRoute allowedRoles={['admin']}>
            <ErrorBoundary>
              <AdminDedupPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Help */}
      <Route
        path="/help"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <HelpPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Duplicates — old route preserved for bookmarks; the new admin
          dedup page at /admin/dedup is strictly better (tenant-wide
          scan, activity-aware winner pick, bulk merge, manager-gated). */}
      <Route path="/duplicates" element={<Navigate to="/admin/dedup" replace />} />

      {/* OAuth Callbacks */}
      <Route
        path="/settings/integrations/google-calendar/callback"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <OAuthCallbackPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />
      <Route
        path="/settings/integrations/meta/callback"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <OAuthCallbackPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />
      <Route
        path="/settings/integrations/gmail/callback"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <OAuthCallbackPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Catch-all redirect to dashboard */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default AppRoutes;
