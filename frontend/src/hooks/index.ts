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
  useFeedback,
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
  useComment,
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
export { useSavedFilters, useCreateSavedFilter, useDeleteSavedFilter, filterKeys } from './useFilters';

// Report hooks
export { reportKeys, useReportTemplates, useSavedReports, useSavedReport, useExecuteReport, useExportReportCsv, useCreateSavedReport, useDeleteSavedReport } from './useReports';

// Permission hooks
export { usePermissions, useRoles, useMyPermissions, useAssignRole, roleKeys } from './usePermissions';

// Email hooks
export { emailKeys, useEmailList, useEntityEmails, useSendEmail, useSendTemplateEmail } from './useEmail';

// Notification hooks
export { notificationKeys, useNotifications, useUnreadCount, useMarkNotificationRead, useMarkAllNotificationsRead } from './useNotifications';

// Webhook hooks
export {
  webhookKeys,
  useWebhooks,
  useWebhook,
  useWebhookDeliveries,
  useCreateWebhook,
  useUpdateWebhook,
  useDeleteWebhook,
  useTestWebhook,
} from './useWebhooks';

// Assignment hooks
export {
  assignmentKeys,
  useAssignmentRules,
  useAssignmentRule,
  useAssignmentStats,
  useCreateAssignmentRule,
  useUpdateAssignmentRule,
  useDeleteAssignmentRule,
} from './useAssignment';

// Sequence hooks
export {
  sequenceKeys,
  useSequences,
  useSequence,
  useSequenceEnrollments,
  useContactEnrollments,
  useCreateSequence,
  useUpdateSequence,
  useDeleteSequence,
  useEnrollContact,
  usePauseEnrollment,
  useResumeEnrollment,
  useProcessDueSteps,
} from './useSequences';

// Attachment hooks
export { attachmentKeys, useAttachments, useUploadAttachment, useDeleteAttachment } from './useAttachments';

// Dedup hooks
export { useCheckDuplicates, useMergeEntities } from './useDedup';

// Quote hooks
export {
  quoteKeys,
  useQuotes,
  useQuote,
  useCreateQuote,
  useUpdateQuote,
  useDeleteQuote,
  useSendQuote,
  useAcceptQuote,
  useRejectQuote,
  useAddLineItem,
  useRemoveLineItem,
} from './useQuotes';

// Payment hooks
export {
  paymentKeys,
  usePayments,
  usePayment,
  useCreateCheckout,
  useCreatePaymentIntent,
  useStripeCustomers,
  useSyncCustomer,
  useProducts,
  useCreateProduct,
  useSubscriptions,
} from './usePayments';

// Proposal hooks
export {
  proposalKeys,
  useProposals,
  useProposal,
  useCreateProposal,
  useUpdateProposal,
  useDeleteProposal,
  useSendProposal,
  useAcceptProposal,
  useRejectProposal,
  useGenerateProposal,
  useProposalTemplates,
  useCreateProposalTemplate,
} from './useProposals';

// Theme hook
export { useTheme } from './useTheme';

// Page title hook
export { usePageTitle } from './usePageTitle';

// Auth-aware query helpers
export { useAuthQuery, useAuthEnabled } from './useAuthQuery';
