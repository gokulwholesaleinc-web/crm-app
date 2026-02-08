/**
 * API Module Exports
 *
 * Central export point for all API clients and utilities
 */

// Client and utilities
export { apiClient, getToken, setToken, clearToken, isAuthenticated } from './client';

// Auth API
export { authApi } from './auth';
export {
  register,
  login,
  loginWithForm,
  getMe,
  updateProfile,
  listUsers,
  logout,
} from './auth';

// Contacts API
export { contactsApi } from './contacts';
export {
  listContacts,
  getContact,
  createContact,
  updateContact,
  deleteContact,
} from './contacts';

// Companies API
export { companiesApi } from './companies';
export {
  listCompanies,
  getCompany,
  createCompany,
  updateCompany,
  deleteCompany,
} from './companies';

// Leads API
export { leadsApi } from './leads';
export {
  listLeads,
  getLead,
  createLead,
  updateLead,
  deleteLead,
  listLeadSources,
  createLeadSource,
  convertToContact,
  convertToOpportunity,
  fullConversion,
} from './leads';

// Opportunities API
export { opportunitiesApi } from './opportunities';
export {
  listOpportunities,
  getOpportunity,
  createOpportunity,
  updateOpportunity,
  deleteOpportunity,
  listStages,
  createStage,
  updateStage,
  reorderStages,
  getKanban,
  moveOpportunity,
  getForecast,
  getPipelineSummary,
} from './opportunities';

// Activities API
export { activitiesApi } from './activities';
export {
  listActivities,
  getActivity,
  createActivity,
  updateActivity,
  deleteActivity,
  completeActivity,
  getMyTasks,
  getEntityTimeline,
  getUserTimeline,
  getUpcomingActivities,
  getOverdueActivities,
} from './activities';

// Campaigns API
export { campaignsApi } from './campaigns';
export {
  listCampaigns,
  getCampaign,
  createCampaign,
  updateCampaign,
  deleteCampaign,
  getCampaignStats,
  getCampaignMembers,
  addCampaignMembers,
  updateCampaignMember,
  removeCampaignMember,
  listEmailTemplates,
  getEmailTemplate,
  createEmailTemplate,
  updateEmailTemplate,
  deleteEmailTemplate,
  getCampaignSteps,
  addCampaignStep,
  updateCampaignStep,
  deleteCampaignStep,
  executeCampaign,
} from './campaigns';

// Workflows API
export { workflowsApi } from './workflows';
export {
  listWorkflowRules,
  getWorkflowRule,
  createWorkflowRule,
  updateWorkflowRule,
  deleteWorkflowRule,
  getWorkflowExecutions,
  testWorkflowRule,
} from './workflows';

// Dashboard API
export { dashboardApi } from './dashboard';
export {
  getDashboard,
  getKpis,
  getPipelineFunnelChart,
  getLeadsByStatusChart,
  getLeadsBySourceChart,
  getRevenueTrendChart,
  getActivitiesChart,
  getNewLeadsTrendChart,
  getConversionRatesChart,
  getSalesFunnel,
} from './dashboard';

// Notes API
export { notesApi } from './notes';
export {
  listNotes,
  getNote,
  createNote,
  updateNote,
  deleteNote,
  getEntityNotes,
} from './notes';

// AI API
export { aiApi } from './ai';
export {
  chat,
  getLeadInsights,
  getOpportunityInsights,
  getDailySummary,
  getRecommendations,
  getNextBestAction,
  semanticSearch,
  confirmAction,
  submitFeedback,
  getPreferences,
  updatePreferences,
} from './ai';

// Import/Export API
export { importExportApi } from './importExport';
export {
  exportContacts,
  exportCompanies,
  exportLeads,
  importContacts,
  importCompanies,
  importLeads,
  getTemplate,
  downloadBlob,
  generateExportFilename,
  bulkUpdate,
  bulkAssign,
} from './importExport';

// Audit API
export { auditApi } from './audit';

// Comments API
export { commentsApi } from './comments';

// Pipelines API
export { pipelinesApi } from './pipelines';

// Aggregated API object for convenience
import { authApi as _authApi } from './auth';
import { contactsApi as _contactsApi } from './contacts';
import { companiesApi as _companiesApi } from './companies';
import { leadsApi as _leadsApi } from './leads';
import { opportunitiesApi as _opportunitiesApi } from './opportunities';
import { activitiesApi as _activitiesApi } from './activities';
import { campaignsApi as _campaignsApi } from './campaigns';
import { dashboardApi as _dashboardApi } from './dashboard';
import { aiApi as _aiApi } from './ai';
import { importExportApi as _importExportApi } from './importExport';
import { notesApi as _notesApi } from './notes';
import { workflowsApi as _workflowsApi } from './workflows';
import { auditApi as _auditApi } from './audit';
import { commentsApi as _commentsApi } from './comments';
import { pipelinesApi as _pipelinesApi } from './pipelines';

export const api = {
  auth: _authApi,
  contacts: _contactsApi,
  companies: _companiesApi,
  leads: _leadsApi,
  opportunities: _opportunitiesApi,
  activities: _activitiesApi,
  campaigns: _campaignsApi,
  dashboard: _dashboardApi,
  ai: _aiApi,
  importExport: _importExportApi,
  notes: _notesApi,
  workflows: _workflowsApi,
  audit: _auditApi,
  comments: _commentsApi,
  pipelines: _pipelinesApi,
};

export default api;
