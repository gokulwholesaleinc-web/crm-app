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

// Re-export useUpcoming alias
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
  useAIPreferences,
  useUpdateAIPreferences,
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

// Workflow hooks
export {
  useWorkflows,
  useWorkflow,
  useWorkflowExecutions,
  useCreateWorkflow,
  useUpdateWorkflow,
  useDeleteWorkflow,
  useTestWorkflow,
  workflowKeys,
} from './useWorkflows';

// Audit hooks
export {
  useEntityAuditLog,
  auditKeys,
} from './useAudit';

// Comment hooks
export {
  useEntityComments,
  useCreateComment,
  useUpdateComment,
  useDeleteComment,
  commentKeys,
} from './useComments';

// Pipeline entity hooks
export {
  usePipelines,
  usePipeline,
  useCreatePipeline,
  useUpdatePipeline,
  useDeletePipeline,
  pipelineEntityKeys,
} from './usePipelines';

// Filter hooks
export { useFilters } from './useFilters';

// Report hooks
export { useReports } from './useReports';

// Permission hooks
export { usePermissions } from './usePermissions';

// Email hooks
export { useEmail } from './useEmail';

// Notification hooks
export { useNotifications } from './useNotifications';

// Webhook hooks
export { useWebhooks } from './useWebhooks';

// Assignment hooks
export { useAssignment } from './useAssignment';

// Sequence hooks
export { useSequences } from './useSequences';

// Attachment hooks
export { useAttachments } from './useAttachments';

// Theme hook
export { useTheme } from './useTheme';

// Page title hook
export { usePageTitle } from './usePageTitle';

// Auth-aware query helpers
export { useAuthQuery, useAuthEnabled } from './useAuthQuery';
