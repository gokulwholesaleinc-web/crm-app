/**
 * Application route definitions with lazy loading for code splitting.
 */

import { lazy } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';

import { PrivateRoute } from './PrivateRoute';

// Lazy load all page components for code splitting
// Authentication pages
const LoginPage = lazy(() => import('../features/auth/LoginPage'));
const RegisterPage = lazy(() => import('../features/auth/RegisterPage'));

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

// Opportunities
const OpportunitiesPage = lazy(() => import('../features/opportunities/OpportunitiesPage'));
const OpportunityDetailPage = lazy(() => import('../features/opportunities/OpportunityDetailPage'));

// Activities
const ActivitiesPage = lazy(() => import('../features/activities/ActivitiesPage'));

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

// Settings
const SettingsPage = lazy(() => import('../features/settings/SettingsPage'));

function AppRoutes() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Protected routes */}
      <Route
        path="/"
        element={
          <PrivateRoute>
            <DashboardPage />
          </PrivateRoute>
        }
      />

      {/* Contacts */}
      <Route
        path="/contacts"
        element={
          <PrivateRoute>
            <ContactsPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/contacts/:id"
        element={
          <PrivateRoute>
            <ContactDetailPage />
          </PrivateRoute>
        }
      />

      {/* Companies */}
      <Route
        path="/companies"
        element={
          <PrivateRoute>
            <CompaniesPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/companies/:id"
        element={
          <PrivateRoute>
            <CompanyDetailPage />
          </PrivateRoute>
        }
      />

      {/* Leads */}
      <Route
        path="/leads"
        element={
          <PrivateRoute>
            <LeadsPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/leads/:id"
        element={
          <PrivateRoute>
            <LeadDetailPage />
          </PrivateRoute>
        }
      />

      {/* Opportunities */}
      <Route
        path="/opportunities"
        element={
          <PrivateRoute>
            <OpportunitiesPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/opportunities/:id"
        element={
          <PrivateRoute>
            <OpportunityDetailPage />
          </PrivateRoute>
        }
      />

      {/* Activities */}
      <Route
        path="/activities"
        element={
          <PrivateRoute>
            <ActivitiesPage />
          </PrivateRoute>
        }
      />

      {/* Campaigns */}
      <Route
        path="/campaigns"
        element={
          <PrivateRoute>
            <CampaignsPage />
          </PrivateRoute>
        }
      />
      <Route
        path="/campaigns/:id"
        element={
          <PrivateRoute>
            <CampaignDetailPage />
          </PrivateRoute>
        }
      />

      {/* AI Assistant */}
      <Route
        path="/ai-assistant"
        element={
          <PrivateRoute>
            <AIAssistantPage />
          </PrivateRoute>
        }
      />

      {/* Reports */}
      <Route
        path="/reports"
        element={
          <PrivateRoute>
            <ReportsPage />
          </PrivateRoute>
        }
      />

      {/* Workflows */}
      <Route
        path="/workflows"
        element={
          <PrivateRoute>
            <WorkflowsPage />
          </PrivateRoute>
        }
      />

      {/* Import/Export */}
      <Route
        path="/import-export"
        element={
          <PrivateRoute>
            <ImportExportPage />
          </PrivateRoute>
        }
      />

      {/* Settings */}
      <Route
        path="/settings"
        element={
          <PrivateRoute>
            <SettingsPage />
          </PrivateRoute>
        }
      />

      {/* Catch-all redirect to dashboard */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default AppRoutes;
