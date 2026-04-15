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
const RegisterPage = lazy(() => import('../features/auth/RegisterPage'));
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

// Opportunities (list redirects to Pipeline; detail page remains)
const OpportunityDetailPage = lazy(() => import('../features/opportunities/OpportunityDetailPage'));

// Quotes
const QuotesPage = lazy(() => import('../features/quotes/QuotesPage'));
const QuoteDetailPage = lazy(() => import('../features/quotes/QuoteDetail'));
const PublicQuoteView = lazy(() => import('../features/quotes/PublicQuoteView'));

// Payments
const PaymentsPage = lazy(() => import('../features/payments/PaymentsPage'));
const PaymentDetailPage = lazy(() => import('../features/payments/PaymentDetail'));

// Proposals
const ProposalsPage = lazy(() => import('../features/proposals/ProposalsPage'));
const ProposalDetailPage = lazy(() => import('../features/proposals/ProposalDetail'));
const PublicProposalView = lazy(() => import('../features/proposals/PublicProposalView'));

// Activities
const ActivitiesPage = lazy(() => import('../features/activities/ActivitiesPage'));
const CalendarPage = lazy(() => import('../features/calendar/CalendarPage'));

// Campaigns
const CampaignsPage = lazy(() => import('../features/campaigns/CampaignsPage'));
const CampaignDetailPage = lazy(() => import('../features/campaigns/CampaignDetailPage'));

// AI Assistant
const AIAssistantPage = lazy(() => import('../features/ai-assistant/AIAssistantPage'));

// Reports
const ReportsPage = lazy(() => import('../features/reports/ReportsPage'));

// Workflows
const WorkflowsPage = lazy(() => import('../features/workflows/WorkflowsPage'));

// Import/Export
const ImportExportPage = lazy(() => import('../features/import-export/ImportExportPage'));

// Sequences
const SequencesPage = lazy(() => import('../features/sequences/SequencesPage'));

// Pipeline
const PipelinePage = lazy(() => import('../features/pipeline/PipelinePage'));

// Settings
const SettingsPage = lazy(() => import('../features/settings/SettingsPage'));

// OAuth Callbacks
const OAuthCallbackPage = lazy(() => import('../features/settings/OAuthCallbackPage'));

// Admin
const AdminDashboardPage = lazy(() => import('../features/admin/AdminDashboard'));

// Help
const HelpPage = lazy(() => import('../features/help/HelpPage'));

// Duplicates
const DuplicatesPage = lazy(() => import('../features/settings/DuplicatesPage'));

function AppRoutes() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/auth/google/callback" element={<GoogleAuthCallbackPage />} />
      <Route path="/proposals/public/:token" element={<PublicProposalView />} />
      <Route path="/quotes/public/:quoteNumber" element={<PublicQuoteView />} />

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

      {/* Opportunities - redirect list to unified Pipeline page */}
      <Route path="/opportunities" element={<Navigate to="/pipeline" replace />} />
      <Route
        path="/opportunities/:id"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <OpportunityDetailPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Quotes */}
      <Route
        path="/quotes"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <QuotesPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />
      <Route
        path="/quotes/:id"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <QuoteDetailPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

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

      {/* AI Assistant */}
      <Route
        path="/ai-assistant"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <AIAssistantPage />
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

      {/* Workflows */}
      <Route
        path="/workflows"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <WorkflowsPage />
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

      {/* Sequences */}
      <Route
        path="/sequences"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <SequencesPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

      {/* Pipeline */}
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
          <PrivateRoute>
            <ErrorBoundary>
              <AdminDashboardPage />
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

      {/* Duplicates */}
      <Route
        path="/duplicates"
        element={
          <PrivateRoute>
            <ErrorBoundary>
              <DuplicatesPage />
            </ErrorBoundary>
          </PrivateRoute>
        }
      />

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

      {/* Catch-all redirect to dashboard */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default AppRoutes;
