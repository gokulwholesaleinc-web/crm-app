/**
 * Central export for all hooks.
 */

// Auth hooks
export {
  useUser,
  useLogin,
  useLogout,
  useRegister,
  useUpdateProfile,
  useUsers,
  authKeys,
} from './useAuth';

// Contact hooks
export {
  useContacts,
  useContact,
  useCreateContact,
  useUpdateContact,
  useDeleteContact,
  useContactSearch,
  contactKeys,
} from './useContacts';

// Company hooks
export {
  useCompanies,
  useCompany,
  useCreateCompany,
  useUpdateCompany,
  useDeleteCompany,
  useCompanySearch,
  companyKeys,
} from './useCompanies';

// Lead hooks
export {
  useLeads,
  useLead,
  useCreateLead,
  useUpdateLead,
  useDeleteLead,
  useConvertLead,
  useConvertLeadToContact,
  useConvertLeadToOpportunity,
  useLeadSources,
  useCreateLeadSource,
  useLeadSearch,
  leadKeys,
  leadSourceKeys,
} from './useLeads';

// Opportunity hooks
export {
  useOpportunities,
  useOpportunity,
  useCreateOpportunity,
  useUpdateOpportunity,
  useDeleteOpportunity,
  usePipelineStages,
  useCreatePipelineStage,
  useUpdatePipelineStage,
  useReorderPipelineStages,
  useKanban,
  useMoveOpportunity,
  useForecast,
  usePipelineSummary,
  useOpportunitySearch,
  opportunityKeys,
  pipelineKeys,
} from './useOpportunities';

// Activity hooks
export {
  useActivities,
  useActivity,
  useCreateActivity,
  useUpdateActivity,
  useDeleteActivity,
  useCompleteActivity,
  useTimeline,
  useUserTimeline,
  useUpcomingActivities,
  useOverdueActivities,
  useMyTasks,
  activityKeys,
} from './useActivities';

// Re-export useUpcoming and useUpcomingActivities alias
export { useUpcomingActivities as useUpcoming } from './useActivities';

// Campaign hooks
export {
  useCampaigns,
  useCampaign,
  useCreateCampaign,
  useUpdateCampaign,
  useDeleteCampaign,
  useCampaignStats,
  useCampaignMembers,
  useAddCampaignMembers,
  useRemoveCampaignMember,
  campaignKeys,
} from './useCampaigns';

// Dashboard hooks
export {
  useDashboard,
  useKPIs,
  useCharts,
  usePipelineFunnelChart,
  useLeadsByStatusChart,
  useLeadsBySourceChart,
  useRevenueTrendChart,
  useActivitiesChart,
  useNewLeadsTrendChart,
  useConversionRatesChart,
  useSalesFunnel,
  dashboardKeys,
} from './useDashboard';

// Notes hooks
export {
  useNotes,
  useNote,
  useEntityNotes,
  useCreateNote,
  useUpdateNote,
  useDeleteNote,
  noteKeys,
} from './useNotes';

// AI hooks
export {
  useChat,
  useRecommendations,
  useDailySummary,
  useLeadInsights,
  useOpportunityInsights,
  useInsights,
  useNextBestAction,
  useSemanticSearch,
  useRefreshAIData,
  aiKeys,
} from './useAI';

// Generic CRUD utilities
export {
  createEntityHooks,
  createQueryKeys,
  type PaginatedResponse,
  type ListParams,
  type EntityConfig,
} from './useEntityCRUD';

// Auth-aware query helpers
export { useAuthQuery, useAuthEnabled } from './useAuthQuery';
