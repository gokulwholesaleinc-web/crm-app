import type { RoleName } from '../../store/authStore';

export type GuideRole = RoleName;

export interface GuideStep {
  title: string;
  body: string;
  action?: string;
  selector?: string;
}

export interface Guide {
  id: string;
  title: string;
  description: string;
  roles: readonly GuideRole[];
  path: string;
  matchPath?: string;
  match?: 'exact' | 'prefix';
  discoverable?: boolean;
  steps: readonly GuideStep[];
  completion?: {
    message: string;
  };
}

const allRoles = ['admin', 'manager', 'sales_rep', 'viewer'] as const;
const staffRoles = ['admin', 'manager', 'sales_rep'] as const;
const managerRoles = ['admin', 'manager'] as const;
const adminRoles = ['admin'] as const;

const target = (name: string) => `[data-guide="${name}"]`;

export const GUIDE_REGISTRY: readonly Guide[] = [
  {
    id: 'navigation-basics',
    title: 'Navigation basics',
    description: 'A quick pass through the sidebar, search, and help entry points.',
    roles: allRoles,
    path: '/',
    steps: [
      {
        title: 'Start from the sidebar',
        body: 'The main modules live here. Admin-only tools are hidden unless your role can use them.',
        selector: target('sidebar-nav'),
      },
      {
        title: 'Jump with global search',
        body: 'Search across contacts, companies, leads, and proposals without leaving your current page.',
        action: 'press the search field and type a contact, company, lead, or proposal name.',
        selector: target('global-search'),
      },
      {
        title: 'Restart guides anytime',
        body: 'Use the Guide button for the best tour on the current page, or open Help to browse every role-relevant guide.',
        action: 'open the Guide menu when you want a refresher or a different page tour.',
        selector: target('header-guide'),
      },
    ],
  },
  {
    id: 'dashboard-tour',
    title: 'Dashboard overview',
    description: 'Read KPIs, pinned reports, recent activity, and team scoping.',
    roles: allRoles,
    path: '/',
    steps: [
      {
        title: 'Your home base',
        body: 'The dashboard summarizes the CRM for the selected date range, with manager and admin views able to scope team data.',
        selector: target('dashboard-header'),
      },
      {
        title: 'Follow the numbers',
        body: 'KPI cards link straight into the records behind the count, so you can move from signal to action quickly.',
        action: 'click a KPI card to jump to the filtered module behind that number.',
        selector: target('dashboard-kpis'),
      },
      {
        title: 'Shared work appears here',
        body: 'Records shared with you surface on the dashboard so collaboration does not depend on memorizing URLs.',
        selector: target('dashboard-shared'),
      },
    ],
  },
  {
    id: 'contacts-tour',
    title: 'Contacts',
    description: 'Create contacts, save smart lists, and jump into relationship history.',
    roles: allRoles,
    path: '/contacts',
    steps: [
      {
        title: 'People records',
        body: 'Contacts are the people you sell to and support. Detail pages collect activity, email, proposal, payment, document, and sharing history.',
        selector: target('contacts-header'),
      },
      {
        title: 'Create or segment',
        body: 'Add a contact directly, or build a smart list when you need a saved, repeatable filter.',
        action: 'use Add Contact for a new person, or Build Smart List to save a reusable segment.',
        selector: target('contacts-actions'),
      },
      {
        title: 'Find the right person',
        body: 'Search by name, email, or company. Saved filters and shared smart lists sit above the table when they exist.',
        action: 'type a name or company into search and watch the table narrow.',
        selector: target('contacts-search'),
      },
    ],
  },
  {
    id: 'contact-detail-tour',
    title: 'Contact detail',
    description: 'Review one person\'s relationship history, communication, payments, and sharing.',
    roles: allRoles,
    path: '/contacts',
    matchPath: '/contacts/:id',
    discoverable: false,
    steps: [
      {
        title: 'Person context',
        body: 'The contact header anchors the record with name, company, subscription state, and the copied ID teammates may ask for.',
        selector: target('contact-detail-header'),
      },
      {
        title: 'Act from the header',
        body: 'Role-allowed actions live together here: email, invoice, proposal creation, edits, and delete confirmation.',
        selector: target('contact-detail-actions'),
      },
      {
        title: 'Use the tabs for history',
        body: 'Details, activities, email, proposals, payments, documents, notes, attachments, history, and sharing keep the full relationship in one place.',
        action: 'switch tabs when you need the next slice of the contact history.',
        selector: target('contact-detail-tabs'),
      },
    ],
  },
  {
    id: 'companies-tour',
    title: 'Companies',
    description: 'Manage account records, segment by status or industry, and open account history.',
    roles: allRoles,
    path: '/companies',
    steps: [
      {
        title: 'Account records',
        body: 'Companies represent customer and prospect accounts. Open a card when you need contacts, proposals, payments, activity, or account metadata.',
        selector: target('companies-page'),
      },
      {
        title: 'Create or update accounts',
        body: 'Add Company starts a duplicate-aware create flow. Existing company cards can be edited or deleted from the card controls.',
        action: 'use Add Company when you need a new account record.',
        selector: target('companies-header'),
      },
      {
        title: 'Find the right account',
        body: 'Search, status, and industry filters are URL-backed so a narrowed company list can be shared or revisited.',
        selector: target('companies-search'),
      },
    ],
  },
  {
    id: 'company-detail-tour',
    title: 'Company detail',
    description: 'Review account contacts, proposals, payments, activity, Meta data, and sharing.',
    roles: allRoles,
    path: '/companies',
    matchPath: '/companies/:id',
    discoverable: false,
    steps: [
      {
        title: 'Account context',
        body: 'The company header shows identity, status, industry, and the copied ID used for cross-team handoffs.',
        selector: target('company-detail-header'),
      },
      {
        title: 'Create follow-up work',
        body: 'Use the action row for role-allowed proposal creation, edits, and delete confirmation.',
        selector: target('company-detail-actions'),
      },
      {
        title: 'Work across account tabs',
        body: 'Tabs keep overview, contacts, proposals, payments, activities, Meta sync, expenses, notes, attachments, history, and sharing tied to the account.',
        action: 'open a tab to inspect the account history without leaving the company record.',
        selector: target('company-detail-tabs'),
      },
    ],
  },
  {
    id: 'leads-tour',
    title: 'Leads',
    description: 'Qualify prospects, assign ownership, promote stages, and convert good fits.',
    roles: staffRoles,
    path: '/leads',
    steps: [
      {
        title: 'Qualify before converting',
        body: 'Leads are prospects that are not contacts yet. Use status, score, source, owner, and stage to decide what should move forward.',
        selector: target('leads-header'),
      },
      {
        title: 'List and pipeline work together',
        body: 'Use the Pipeline button when you want a drag-and-drop view. Keep list view for bulk updates, assignments, and conversion work.',
        action: 'click Pipeline to switch from list operations into stage-based work.',
        selector: target('leads-pipeline-link'),
      },
      {
        title: 'Filter down fast',
        body: 'Search and status filters are URL-backed, so a filtered lead list can be shared with a teammate.',
        selector: target('leads-filters'),
      },
    ],
  },
  {
    id: 'lead-detail-tour',
    title: 'Lead detail',
    description: 'Score, qualify, communicate with, and convert a single lead.',
    roles: staffRoles,
    path: '/leads',
    matchPath: '/leads/:id',
    discoverable: false,
    steps: [
      {
        title: 'Lead context',
        body: 'The header keeps the lead name, company context, and ID visible while you decide the next step.',
        selector: target('lead-detail-header'),
      },
      {
        title: 'Use the qualification signal',
        body: 'The score card summarizes fit and engagement. Use it with status, source, owner, and stage before converting.',
        selector: target('lead-detail-score'),
      },
      {
        title: 'Continue from tabs',
        body: 'Details, activities, email, notes, attachments, history, sharing, and comments keep qualification work attached to the lead.',
        action: 'switch to Activities or Emails when you need the recent conversation before changing status.',
        selector: target('lead-detail-tabs'),
      },
    ],
  },
  {
    id: 'pipeline-tour',
    title: 'Pipeline',
    description: 'Move leads through kanban stages and monitor owner-scoped pipeline health.',
    roles: staffRoles,
    path: '/pipeline',
    steps: [
      {
        title: 'Stage-based selling',
        body: 'The pipeline is a kanban board for promoted leads. New leads stay off-board until they are assigned a pipeline stage.',
        selector: target('pipeline-header'),
      },
      {
        title: 'Scope the board',
        body: 'Managers and admins can filter by owner. Everyone can search by name, email, or company.',
        action: 'search for a lead; managers and admins can also pick an owner to scope the board.',
        selector: target('pipeline-toolbar'),
      },
      {
        title: 'Drag to progress',
        body: 'Move cards between stages to update the lead. The board uses forgiving drop zones for desktop and touch devices.',
        action: 'drag a visible lead card into the next stage when the deal advances.',
        selector: target('pipeline-board'),
      },
    ],
  },
  {
    id: 'proposals-tour',
    title: 'Proposals and signing',
    description: 'Create proposals, attach signing PDFs, place signature areas, and send safely.',
    roles: staffRoles,
    path: '/proposals',
    steps: [
      {
        title: 'Create the proposal',
        body: 'Start from a blank proposal or template. Pricing is reference-only; billing is created manually after the customer signs.',
        action: 'click Create Proposal, then fill the proposal body and optional signing PDFs.',
        selector: target('proposals-header'),
      },
      {
        title: 'Templates live here too',
        body: 'Switch to Templates when you need reusable proposal language with merge variables.',
        action: 'click Templates to start from a reusable proposal format.',
        selector: target('proposals-tabs'),
      },
      {
        title: 'Track signature status',
        body: 'The table shows sent, viewed, accepted, and rejected proposals. Open a record to send, place PDF signing areas, or download signed copies.',
        selector: target('proposals-table'),
      },
    ],
  },
  {
    id: 'proposal-detail-tour',
    title: 'Proposal detail',
    description: 'Edit proposal sections, send safely, place signing documents, and audit acceptance.',
    roles: staffRoles,
    path: '/proposals',
    matchPath: '/proposals/:id',
    discoverable: false,
    steps: [
      {
        title: 'Proposal state',
        body: 'The header shows the proposal number and current status so sent, accepted, rejected, and billing-ready work is easy to distinguish.',
        selector: target('proposal-detail-header'),
      },
      {
        title: 'Send only when ready',
        body: 'The action row and checklist protect sending: missing content, signing documents, or required setup appears before the proposal goes out.',
        action: 'review the send checklist before clicking Send or Copy Link.',
        selector: target('proposal-detail-actions'),
      },
      {
        title: 'Signing and audit trail',
        body: 'Signing documents, public-link views, acceptance data, related records, and sharing live beside the editable proposal sections.',
        selector: target('proposal-detail-signing-documents'),
      },
    ],
  },
  {
    id: 'payments-tour',
    title: 'Payments basics',
    description: 'Send manual Stripe invoices and monitor one-time payments and subscriptions.',
    roles: staffRoles,
    path: '/payments',
    steps: [
      {
        title: 'Billing is manual',
        body: 'After a proposal is signed, use Payments to create the invoice or subscription workflow you want. Proposal acceptance does not auto-charge.',
        selector: target('payments-header'),
      },
      {
        title: 'Send an invoice',
        body: 'Use Send Invoice to pick a Stripe customer, amount, description, and due date.',
        action: 'click Send Invoice when a signed proposal is ready for manual billing.',
        selector: target('payments-send-invoice'),
      },
      {
        title: 'Switch payment views',
        body: 'All Payments shows one-time invoices and charges. Subscriptions shows recurring billing state.',
        selector: target('payments-tabs'),
      },
    ],
  },
  {
    id: 'payment-detail-tour',
    title: 'Payment detail',
    description: 'Review invoice status, Stripe links, attachments, and related CRM records.',
    roles: staffRoles,
    path: '/payments',
    matchPath: '/payments/:id',
    discoverable: false,
    steps: [
      {
        title: 'Invoice state',
        body: 'The header shows payment status, Stripe identifiers, and invoice actions for download, resend, and receipt follow-up.',
        selector: target('payment-detail-header'),
      },
      {
        title: 'Amount and payment facts',
        body: 'The main cards show amount, currency, method, receipt, checkout session, and invoice attachments.',
        selector: target('payment-detail-main'),
      },
      {
        title: 'Connect it back to CRM',
        body: 'The sidebar links the payment to its customer and proposal so billing questions can move back to the source record.',
        selector: target('payment-detail-related'),
      },
    ],
  },
  {
    id: 'activities-tour',
    title: 'Activities',
    description: 'Work calls, emails, meetings, tasks, and notes from one timeline.',
    roles: staffRoles,
    path: '/activities',
    steps: [
      {
        title: 'Every touchpoint',
        body: 'Activities attach to contacts, companies, and leads, then appear both here and on each record detail page.',
        selector: target('activities-header'),
      },
      {
        title: 'Choose the view',
        body: 'Use list for action, timeline for history, and calendar for scheduled work.',
        action: 'switch between list, timeline, and calendar to see the same work from different angles.',
        selector: target('activities-view-toggle'),
      },
      {
        title: 'Filter operational work',
        body: 'Narrow the list by activity type, priority, and completion state when you are planning the day.',
        selector: target('activities-filters'),
      },
    ],
  },
  {
    id: 'calendar-tour',
    title: 'Calendar',
    description: 'Review CRM activities alongside Google Calendar events.',
    roles: staffRoles,
    path: '/calendar',
    steps: [
      {
        title: 'Calendar view',
        body: 'This page shows scheduled activities and synced Google Calendar events in one place.',
        selector: target('calendar-header'),
      },
      {
        title: 'Connect or sync',
        body: 'If Google Calendar is connected, sync from here. If not, jump to Settings integrations.',
        selector: target('calendar-sync'),
      },
    ],
  },
  {
    id: 'inbox-tour',
    title: 'Inbox',
    description: 'Find synced Gmail messages and jump back to the matching CRM record.',
    roles: staffRoles,
    path: '/inbox',
    steps: [
      {
        title: 'Email finder',
        body: 'Inbox is not a Gmail replacement. It helps you locate synced mail and open the CRM record where the thread belongs.',
        selector: target('inbox-header'),
      },
      {
        title: 'Search and filter mail',
        body: 'Search by subject, body, sender, or recipient. Status chips help you focus on sent, received, unread, or failed messages.',
        action: 'type into the inbox search field or choose a status chip.',
        selector: target('inbox-search'),
      },
      {
        title: 'Mind the sending budget',
        body: 'The send-volume tile shows today’s outbound usage against your configured Gmail limit and warmup budget.',
        selector: target('inbox-volume'),
      },
    ],
  },
  {
    id: 'reports-tour',
    title: 'Reports',
    description: 'Run templates, build saved reports, and pin useful reports to the dashboard.',
    roles: allRoles,
    path: '/reports',
    steps: [
      {
        title: 'Analytics for the CRM',
        body: 'Reports turn CRM records into charts and tables, with templates for common sales and activity questions.',
        selector: target('reports-header'),
      },
      {
        title: 'Saved reports',
        body: 'Saved reports can be re-run later and pinned to Dashboard widgets.',
        selector: target('reports-saved'),
      },
      {
        title: 'Template starting points',
        body: 'Use templates when you need a fast answer before building a custom report from scratch.',
        selector: target('reports-templates'),
      },
    ],
  },
  {
    id: 'campaigns-tour',
    title: 'Campaigns',
    description: 'Plan email campaigns, enroll members, and monitor results.',
    roles: managerRoles,
    path: '/campaigns',
    steps: [
      {
        title: 'Campaign workspace',
        body: 'Campaigns organize email outreach, members, sequence steps, budget, and results.',
        selector: target('campaigns-header'),
      },
      {
        title: 'Create and track',
        body: 'Create campaigns from here, then use each detail page to add members and build email steps.',
        selector: target('campaigns-actions'),
      },
    ],
  },
  {
    id: 'campaign-detail-tour',
    title: 'Campaign detail',
    description: 'Manage campaign setup, members, sequence steps, and email analytics.',
    roles: managerRoles,
    path: '/campaigns',
    matchPath: '/campaigns/:id',
    discoverable: false,
    steps: [
      {
        title: 'Campaign command row',
        body: 'Managers and admins can send, edit, or delete from the header when campaign status and permissions allow it.',
        selector: target('campaign-detail-header'),
      },
      {
        title: 'Track performance',
        body: 'Stats, funnel counts, Mailchimp sync, and analytics summarize how the campaign is moving members forward.',
        selector: target('campaign-detail-stats'),
      },
      {
        title: 'Build sequence and audience',
        body: 'Email steps and members stay on the detail page so managers can adjust outreach and recipient lists together.',
        action: 'review members before sending or changing an active email campaign.',
        selector: target('campaign-detail-members'),
      },
    ],
  },
  {
    id: 'settings-preferences-tour',
    title: 'Settings and preferences',
    description: 'Update your profile, notification preferences, theme, tabs, density, and signature.',
    roles: allRoles,
    path: '/settings',
    steps: [
      {
        title: 'Settings sections',
        body: 'The section nav jumps between profile, notifications, preferences, and the setup areas your role can access.',
        action: 'choose a section from the settings navigation to jump directly to it.',
        selector: target('settings-nav'),
      },
      {
        title: 'Profile basics',
        body: 'Keep your name, phone, title, and account details accurate so teammates see the right context.',
        selector: target('settings-section-profile'),
      },
      {
        title: 'Personal preferences',
        body: 'Notification preferences, locale, timezone, currency, theme, default landing page, density, tabs, nav visibility, and signature are available now.',
        selector: target('settings-preferences'),
      },
    ],
  },
  {
    id: 'settings-admin-tour',
    title: 'Admin settings',
    description: 'Configure tenant branding, integrations, webhooks, roles, notifications, and account defaults.',
    roles: adminRoles,
    path: '/settings',
    steps: [
      {
        title: 'Admin setup sections',
        body: 'Admins can configure tenant-wide setup areas from the settings navigation, including branding, integrations, webhooks, and roles.',
        action: 'choose a setup section from the settings navigation to jump directly to it.',
        selector: target('settings-nav'),
      },
      {
        title: 'Integrations',
        body: 'Connect Gmail, Google Calendar, and Meta from Integrations. Token status is visible in the section.',
        selector: target('settings-integrations'),
      },
      {
        title: 'Roles and access',
        body: 'Use Roles when you need to control who can see admin tools, manage users, and configure tenant-level features.',
        selector: target('settings-roles'),
      },
    ],
  },
  {
    id: 'admin-dashboard-tour',
    title: 'Admin dashboard',
    description: 'Review tenant stats, user management, team overview, and activity feed.',
    roles: adminRoles,
    path: '/admin',
    steps: [
      {
        title: 'Tenant command center',
        body: 'Admins see system-wide user, record, proposal, and payment stats here.',
        selector: target('admin-header'),
      },
      {
        title: 'User management',
        body: 'Create, edit, deactivate, and assign roles for tenant users.',
        selector: target('admin-users'),
      },
      {
        title: 'Team oversight',
        body: 'Review team pipeline value, lead counts, won deals, and recent audit activity.',
        selector: target('admin-team'),
      },
    ],
  },
  {
    id: 'user-approvals-tour',
    title: 'User approvals',
    description: 'Approve pending sign-ups, choose roles, and manage blocked emails.',
    roles: adminRoles,
    path: '/admin/user-approvals',
    steps: [
      {
        title: 'Approve new users',
        body: 'Google sign-ups wait here until an admin approves them and assigns sales rep, manager, or admin access.',
        selector: target('approvals-pending'),
      },
      {
        title: 'Rejected email list',
        body: 'Rejected emails are blocked from signing in again until an admin unblocks them.',
        selector: target('approvals-rejected'),
      },
    ],
  },
  {
    id: 'admin-sharing-tour',
    title: 'Admin sharing',
    description: 'Audit record-level shares and revoke stale access.',
    roles: adminRoles,
    path: '/admin/sharing',
    steps: [
      {
        title: 'Tenant-wide sharing audit',
        body: 'Admins can filter every record share by entity type, sender, recipient, and permission.',
        selector: target('admin-sharing-filters'),
      },
      {
        title: 'Revoke access',
        body: 'Use the share table to remove stale access without opening each individual record.',
        selector: target('admin-sharing-table'),
      },
    ],
  },
  {
    id: 'duplicate-cleanup-tour',
    title: 'Duplicate cleanup',
    description: 'Find duplicate clusters and merge redundant records into the best winner.',
    roles: adminRoles,
    path: '/admin/dedup',
    steps: [
      {
        title: 'Pick the scan',
        body: 'Choose contacts, companies, or leads, then scan by email, phone, or normalized name depending on the entity.',
        selector: target('dedup-controls'),
      },
      {
        title: 'Choose the winner',
        body: 'Each cluster lets you pick the record to keep. Linked records move to the winner and redundant records are soft-deleted.',
        selector: target('dedup-results'),
      },
    ],
  },
  {
    id: 'import-export-tour',
    title: 'Import and export',
    description: 'Move CRM data by CSV with templates, previews, and dedup checks.',
    roles: managerRoles,
    path: '/import-export',
    steps: [
      {
        title: 'Export cleanly',
        body: 'Download contacts, companies, or leads. Exports respect role-based data scope.',
        selector: target('import-export-export'),
      },
      {
        title: 'Import with review',
        body: 'Uploads preview column mappings, duplicate handling, and row-level errors before records are created.',
        selector: target('import-export-import'),
      },
    ],
  },
];

export const ROLE_RECOMMENDATIONS: Record<GuideRole, readonly string[]> = {
  sales_rep: [
    'dashboard-tour',
    'contacts-tour',
    'companies-tour',
    'leads-tour',
    'pipeline-tour',
    'proposals-tour',
    'payments-tour',
    'activities-tour',
    'inbox-tour',
  ],
  manager: [
    'dashboard-tour',
    'leads-tour',
    'pipeline-tour',
    'reports-tour',
    'campaigns-tour',
  ],
  admin: [
    'user-approvals-tour',
    'admin-dashboard-tour',
    'settings-admin-tour',
    'admin-sharing-tour',
    'duplicate-cleanup-tour',
    'import-export-tour',
  ],
  viewer: [
    'navigation-basics',
    'contacts-tour',
    'companies-tour',
    'reports-tour',
  ],
};

export function normalizeRole(role: string | undefined, isSuperuser = false): GuideRole {
  if (isSuperuser) return 'admin';
  if (role === 'admin' || role === 'manager' || role === 'sales_rep' || role === 'viewer') {
    return role;
  }
  return 'viewer';
}

export function guideAllowsRole(guide: Guide, role: GuideRole): boolean {
  return guide.roles.includes(role);
}

function normalizePathname(pathname: string): string {
  const pathOnly = pathname.split(/[?#]/)[0] || '/';
  const withLeadingSlash = pathOnly.startsWith('/') ? pathOnly : `/${pathOnly}`;
  return withLeadingSlash.replace(/\/+$/, '') || '/';
}

function pathSegments(pathname: string): string[] {
  return normalizePathname(pathname).split('/').filter(Boolean);
}

function pathPatternMatches(pattern: string, pathname: string): boolean {
  const patternSegments = pathSegments(pattern);
  const currentSegments = pathSegments(pathname);

  if (patternSegments.length !== currentSegments.length) {
    return false;
  }

  return patternSegments.every((segment, index) => {
    const currentSegment = currentSegments[index];
    if (!currentSegment) return false;
    return segment.startsWith(':') ? currentSegment.length > 0 : segment === currentSegment;
  });
}

export function guideMatchesPath(guide: Guide, pathname: string): boolean {
  const guidePath = guide.matchPath ?? guide.path;
  const normalizedGuidePath = normalizePathname(guidePath);
  const normalizedPathname = normalizePathname(pathname);

  if (normalizedGuidePath === '/') return normalizedPathname === '/';
  if (guide.match === 'prefix') {
    return normalizedPathname === normalizedGuidePath || normalizedPathname.startsWith(`${normalizedGuidePath}/`);
  }
  return pathPatternMatches(guidePath, pathname);
}

export function getGuidesForRole(role: GuideRole): Guide[] {
  return GUIDE_REGISTRY.filter((guide) => guide.discoverable !== false && guideAllowsRole(guide, role));
}

export function getGuidesForPath(pathname: string, role: GuideRole): Guide[] {
  return GUIDE_REGISTRY.filter((guide) => guideAllowsRole(guide, role) && guideMatchesPath(guide, pathname));
}

export function getGuideById(id: string): Guide | undefined {
  return GUIDE_REGISTRY.find((guide) => guide.id === id);
}

export function getRecommendedGuides(role: GuideRole): Guide[] {
  const allowed = new Map(getGuidesForRole(role).map((guide) => [guide.id, guide]));
  return ROLE_RECOMMENDATIONS[role]
    .map((id) => allowed.get(id))
    .filter((guide): guide is Guide => Boolean(guide));
}
