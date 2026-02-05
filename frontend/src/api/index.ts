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
} from './campaigns';

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
} from './dashboard';

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
} from './ai';

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
};

export default api;
