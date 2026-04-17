/* eslint-disable react-refresh/only-export-components -- file intentionally colocates small helper components (Step/Bullet/Tip) with the SECTIONS data structure. */
import { Badge } from '../../components/ui/Badge';
import {
  HomeIcon,
  UserGroupIcon,
  BuildingOfficeIcon,
  FunnelIcon,
  ViewColumnsIcon,
  DocumentTextIcon,
  DocumentDuplicateIcon,
  CreditCardIcon,
  CalendarIcon,
  MegaphoneIcon,
  QueueListIcon,
  BoltIcon,
  DocumentMagnifyingGlassIcon,
  ArrowsRightLeftIcon,
  ChartBarIcon,
  SparklesIcon,
  Cog6ToothIcon,
  ShieldCheckIcon,
  AcademicCapIcon,
  ArrowRightIcon,
} from '@heroicons/react/24/outline';

export interface Section {
  id: string;
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  /** Plain-text description used for the search index. */
  searchText: string;
  body: React.ReactNode;
}

function Step({ n, children }: { n: number; children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="flex-shrink-0 inline-flex h-6 w-6 items-center justify-center rounded-full bg-primary-100 text-primary-700 text-xs font-semibold dark:bg-primary-900/30 dark:text-primary-300">
        {n}
      </span>
      <span className="flex-1 text-sm text-gray-700 dark:text-gray-300">{children}</span>
    </li>
  );
}

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex gap-2 text-sm text-gray-700 dark:text-gray-300">
      <span aria-hidden="true" className="text-gray-400">•</span>
      <span className="flex-1">{children}</span>
    </li>
  );
}

function Tip({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900/40 dark:bg-amber-900/20 dark:text-amber-200">
      <strong className="font-semibold">Tip:</strong> {children}
    </div>
  );
}

export const SECTIONS: Section[] = [
  {
    id: 'getting-started',
    title: 'Getting Started',
    icon: AcademicCapIcon,
    searchText:
      'getting started login sign in register account password remember me sidebar navigation customize order dark mode theme search global header profile',
    body: (
      <div className="space-y-4">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          The CRM is built around a simple funnel:{' '}
          <strong>Lead → Contact (and optionally Company) → Opportunity → Quote / Proposal → Payment</strong>.
          Every other tab — Activities, Campaigns, Sequences, Workflows — exists to help you move
          records through that funnel and keep a full history of what happened along the way.
        </p>

        <div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Signing in
          </h4>
          <ul className="space-y-1.5">
            <Bullet>
              Log in with your email and password on the <code>/login</code> page.
            </Bullet>
            <Bullet>
              New users register from <code>/register</code> with first name, last name, email, and
              password. After registering you are redirected to login.
            </Bullet>
            <Bullet>
              On successful login you land on the Dashboard. Your profile, theme toggle, and sign-out
              live in the top-right user menu.
            </Bullet>
          </ul>
        </div>

        <div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Navigating the app
          </h4>
          <ul className="space-y-1.5">
            <Bullet>
              The left sidebar has two groups: a main group (Dashboard through Campaigns) and a
              secondary group (Sequences, Workflows, Duplicates, Import/Export, Reports, AI
              Assistant, Settings, Admin).
            </Bullet>
            <Bullet>
              Click <strong>Customize Menu</strong> at the bottom of the sidebar to drag items into
              whatever order you prefer. Your order is saved per browser. Hit <em>Reset to Default</em>{' '}
              to restore the original layout.
            </Bullet>
            <Bullet>
              The header has a global search that looks across Contacts, Leads, Companies, Quotes,
              Proposals, and Payments. You can also toggle dark mode from the header.
            </Bullet>
            <Bullet>
              The <strong>Admin</strong> tab is only visible to users with the admin role.
            </Bullet>
          </ul>
        </div>

        <Tip>
          If you get lost, every detail page has tabs along the top (Notes, Activities, Files, etc.)
          and a back button. You can also press the global search and type a name to jump anywhere.
        </Tip>
      </div>
    ),
  },
  {
    id: 'core-flow',
    title: 'The Core Flow (Read This First)',
    icon: ArrowRightIcon,
    searchText:
      'flow funnel lead contact company opportunity quote proposal payment conversion convert process journey',
    body: (
      <div className="space-y-4">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Here is how a typical deal moves through the system. Understanding this once will make every
          tab click much more obvious.
        </p>

        <ol className="space-y-3">
          <Step n={1}>
            <strong>A Lead arrives.</strong> Either you create one manually on the Leads page, import
            a list from CSV (Import/Export), or it appears via an integration. A lead has a status
            (<em>new, contacted, qualified, unqualified, converted, lost</em>) and a numeric{' '}
            <em>score</em> color-coded green/yellow/orange/red on the list.
          </Step>
          <Step n={2}>
            <strong>You qualify and convert it.</strong> Open the lead and click the convert action.
            The conversion modal lets you create a Contact (default), and optionally also create an
            Opportunity at the same time with a name, value, and stage. Both pieces are stored on
            the lead record (<code>converted_contact_id</code>, <code>converted_opportunity_id</code>) and
            the lead's status flips to <em>converted</em>.
          </Step>
          <Step n={3}>
            <strong>The Contact lives in Contacts and Companies.</strong> If the lead's company name
            was set, the converter can create a Company too and link the contact to it. From here on
            you'll see the contact's full history on the Contact detail page.
          </Step>
          <Step n={4}>
            <strong>The Opportunity moves through the Pipeline.</strong> The Pipeline tab is a kanban
            with two tracks (Leads and Opportunities) separated by a Conversion divider. Drag cards
            across stages — the stages themselves are configured in Settings → Pipeline Stages, with
            colors and probabilities.
          </Step>
          <Step n={5}>
            <strong>You build a Quote and/or Proposal.</strong> Both can link to an Opportunity, a
            Contact, and a Company. Quotes hold line items with prices and discounts; Proposals hold
            longer-form sections (cover letter, scope, pricing, timeline, terms). Each has a public
            share URL you send to the client.
          </Step>
          <Step n={6}>
            <strong>The client accepts or rejects.</strong> Public quote/proposal pages capture the
            decision (and an e-signature for quotes — name, email, IP, signed-at). The status flips to
            <em> accepted</em> or <em>rejected</em>.
          </Step>
          <Step n={7}>
            <strong>You collect Payment.</strong> The Payments tab tracks Stripe payment intents,
            checkout sessions, invoices, and subscriptions. Payments link back to the opportunity,
            quote, and Stripe customer.
          </Step>
          <Step n={8}>
            <strong>Activities follow the record everywhere.</strong> Calls, emails, meetings, tasks,
            and notes are logged against whichever entity they belong to. They show up on the
            timeline of every detail page and in the Activities tab.
          </Step>
        </ol>

        <Tip>
          You don't have to follow the funnel strictly. You can create Contacts, Companies, and
          Opportunities directly without ever having a Lead — useful for inbound referrals or
          accounts you already know.
        </Tip>
      </div>
    ),
  },
  {
    id: 'dashboard',
    title: 'Dashboard',
    icon: HomeIcon,
    searchText:
      'dashboard kpi cards charts pipeline overview leads by source sales funnel recent activities widgets reports date range',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          The Dashboard is your home page. It summarizes everything in a single scroll, scoped to
          the date range picker at the top.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">What you see</h4>
        <ul className="space-y-1.5">
          <Bullet>
            <strong>KPI cards:</strong> Total Contacts, Total Leads, Open Opportunities, Total
            Revenue — each with a trend indicator and a click-through to the relevant tab.
          </Bullet>
          <Bullet>
            <strong>Sales KPIs:</strong> Quotes Sent, Proposals Sent, Payments Collected, and Quote
            Conversion Rate.
          </Bullet>
          <Bullet>
            <strong>AI Recommendations:</strong> Lazy-loaded suggestions for which deals to chase
            next, generated from your data.
          </Bullet>
          <Bullet>
            <strong>Report Widgets:</strong> Pin any saved report from the Reports tab as a widget.
            Use the "Add widget" modal to choose from your saved reports.
          </Bullet>
          <Bullet>
            <strong>Charts:</strong> Pipeline Overview (by stage), Leads by Source, Sales Funnel.
          </Bullet>
          <Bullet>
            <strong>Recent Activities:</strong> Your most recent calls, emails, meetings, tasks, and
            notes across the system.
          </Bullet>
        </ul>
        <Tip>
          The date range picker controls every chart and KPI on this page. If a number looks off,
          double-check the range first.
        </Tip>
      </div>
    ),
  },
  {
    id: 'contacts',
    title: 'Contacts',
    icon: UserGroupIcon,
    searchText:
      'contacts contact create edit detail tabs notes activities emails contracts quotes proposals documents attachments history sharing smart list filter search company link',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          A Contact is a person you do business with. Contacts can be linked to a Company, and most
          other records (activities, quotes, proposals, contracts) hang off a contact.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Creating &amp; editing</h4>
        <ul className="space-y-1.5">
          <Bullet>
            Required: first name, last name, email. Optional: phone, company (searchable dropdown
            that creates the link to Companies), job title, sales code, full address, notes.
          </Bullet>
          <Bullet>
            The list view shows name, email, linked company, phone, mobile, department, location,
            status, and created date. Search is debounced — type a name, email, or company.
          </Bullet>
          <Bullet>
            Use <strong>Smart Lists</strong> to save filter combinations. They appear as bookmark
            buttons above the search bar. Personal lists you can delete; shared lists you cannot.
          </Bullet>
        </ul>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Detail page tabs</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Open any contact and you'll see tabs for: <em>Details, Activities, Notes, Emails,
          Contracts, Quotes, Proposals, Documents, Attachments, History, Sharing</em>. Each is a
          self-contained view of just the records that belong to this contact.
        </p>
      </div>
    ),
  },
  {
    id: 'companies',
    title: 'Companies',
    icon: BuildingOfficeIcon,
    searchText:
      'companies company industry size status prospect customer churned segment custom fields tier sow account manager opportunities contracts quotes proposals expenses meta',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Companies group contacts together and act as the parent for opportunities, contracts,
          quotes, proposals, and expenses tied to that account.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">List view</h4>
        <ul className="space-y-1.5">
          <Bullet>
            Card-based layout with the company name, logo/initial, status badge, and industry tag.
          </Bullet>
          <Bullet>
            Filter by status (<em>prospect, customer, churned</em>) and industry (technology,
            healthcare, finance, manufacturing, retail, education, real estate, consulting, media,
            other).
          </Bullet>
          <Bullet>
            Fields you can set: name, website, industry, size, phone, email, full address, annual
            revenue, employee count, LinkedIn, Twitter, description, plus custom fields like tier,
            SOW URL, and account manager.
          </Bullet>
        </ul>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Detail page tabs</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          <em>Overview, Opportunities, Contracts, Quotes, Proposals, Activities, Notes, Attachments,
          History, Sharing, Meta (custom fields), Expenses.</em> The Overview tab lists all linked
          contacts as cards.
        </p>
      </div>
    ),
  },
  {
    id: 'leads',
    title: 'Leads',
    icon: FunnelIcon,
    searchText:
      'leads lead score status new contacted qualified unqualified converted lost source kanban list view bulk actions assign campaign convert contact opportunity company budget',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Leads are unqualified prospects you haven't yet converted. They live in their own table
          (separate from Contacts) and have extra fields specific to qualification.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">List &amp; kanban views</h4>
        <ul className="space-y-1.5">
          <Bullet>
            Toggle between <strong>list</strong> and <strong>kanban</strong> view at the top. The
            kanban groups leads by their pipeline stage.
          </Bullet>
          <Bullet>
            Filter by status (new, contacted, qualified, unqualified, converted, lost), source,
            owner, minimum score, or tags. Search by name, email, or company.
          </Bullet>
          <Bullet>
            <strong>Score bar</strong> shows lead temperature: green (≥80), yellow (≥60), orange
            (≥40), red (&lt;40). Score factors are stored on the record so you can see why.
          </Bullet>
          <Bullet>
            <strong>Bulk actions</strong> (multi-select): update status, assign owner, add to email
            campaign, add to drip campaign.
          </Bullet>
        </ul>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Converting a lead</h4>
        <ol className="space-y-3">
          <Step n={1}>
            Open the lead and click <strong>Convert</strong>. The conversion modal opens.
          </Step>
          <Step n={2}>
            <em>Create Contact</em> is checked by default. Leave it on to create a new Contact from
            the lead's name, email, phone, address, and job title.
          </Step>
          <Step n={3}>
            Optionally tick <em>Create Opportunity</em>. You'll be asked for an opportunity name
            (required), value, and starting stage (discovery, proposal, negotiation, scoping,
            stalling, won, lost).
          </Step>
          <Step n={4}>
            If the lead has a company name set, the system can also create a new Company and link
            the contact to it.
          </Step>
          <Step n={5}>
            On submit, the lead's status flips to <em>converted</em> and the new contact and
            opportunity IDs are stored on the lead so you can always trace it back.
          </Step>
        </ol>
      </div>
    ),
  },
  {
    id: 'pipeline',
    title: 'Pipeline',
    icon: ViewColumnsIcon,
    searchText:
      'pipeline kanban drag drop stages opportunities leads conversion divider stage colors probability won lost',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          The Pipeline page is a unified kanban that shows both Leads and Opportunities in one
          board, separated by a "Conversion" divider. It's the visual workspace where you move deals
          forward.
        </p>
        <ul className="space-y-1.5">
          <Bullet>
            <strong>Drag and drop</strong> cards between stages to update them. Each move is saved
            instantly.
          </Bullet>
          <Bullet>
            Stages are configurable in <em>Settings → Pipeline Stages</em>. Each stage has a name,
            color, order, and a probability percentage, plus flags for "is won" and "is lost".
          </Bullet>
          <Bullet>
            Default opportunity stages seen in code: <em>discovery, proposal, negotiation, scoping,
            stalling, won, lost</em> — but yours may differ if your admin has customized them.
          </Bullet>
          <Bullet>
            Each card shows the deal name, amount, contact, and stage color. Click any card to open
            its detail page.
          </Bullet>
        </ul>
        <Tip>
          The list URL <code>/opportunities</code> automatically redirects to <code>/pipeline</code> —
          there is no separate opportunities list page. Open an individual opportunity from a card
          to see its detail view.
        </Tip>
      </div>
    ),
  },
  {
    id: 'quotes',
    title: 'Quotes',
    icon: DocumentTextIcon,
    searchText:
      'quotes quote line items discount tax payment type one time subscription recurring monthly quarterly yearly draft sent viewed accepted rejected expired public link e-signature',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Quotes are itemized price offers you send to a contact. They can stand alone or attach to
          an Opportunity (and one Opportunity can have multiple Quotes).
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Anatomy of a quote</h4>
        <ul className="space-y-1.5">
          <Bullet>
            Header fields: title, description, currency (default USD), <em>valid until</em> date,
            payment type (one-time or subscription), recurring interval if subscription (monthly,
            quarterly, yearly), and a discount (percent or fixed).
          </Bullet>
          <Bullet>
            Line items: quantity × unit price minus per-line discount. Totals roll up automatically.
          </Bullet>
          <Bullet>
            Branding: company name, logo, and primary/secondary/accent colors are pulled from your
            tenant white-label settings.
          </Bullet>
        </ul>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Status flow</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          <Badge variant="gray">draft</Badge> →{' '}
          <Badge variant="blue">sent</Badge> →{' '}
          <Badge variant="yellow">viewed</Badge> →{' '}
          <Badge variant="green">accepted</Badge> /{' '}
          <Badge variant="red">rejected</Badge> /{' '}
          <Badge variant="gray">expired</Badge>
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Public link &amp; e-signature</h4>
        <ul className="space-y-1.5">
          <Bullet>
            Every quote has a public URL at <code>/quotes/public/&#123;quote_number&#125;</code>{' '}
            that you can send to the client without requiring them to log in.
          </Bullet>
          <Bullet>
            On the public page, the client can view, accept (with their name, email, and IP captured
            as an e-signature) or reject with a reason. Status updates flow back into the CRM.
          </Bullet>
        </ul>
      </div>
    ),
  },
  {
    id: 'proposals',
    title: 'Proposals',
    icon: DocumentDuplicateIcon,
    searchText:
      'proposals proposal cover letter executive summary scope of work pricing timeline terms templates ai generator template gallery public link view tracking',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Proposals are long-form sales documents — think the pitch deck of a quote. They support
          rich content sections, templates, and AI-assisted drafting.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Sections</h4>
        <ul className="space-y-1.5">
          <Bullet>Cover letter</Bullet>
          <Bullet>Executive summary</Bullet>
          <Bullet>Scope of work</Bullet>
          <Bullet>Pricing section</Bullet>
          <Bullet>Timeline</Bullet>
          <Bullet>Terms</Bullet>
        </ul>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Templates &amp; AI</h4>
        <ul className="space-y-1.5">
          <Bullet>
            The Proposals page has two tabs: <em>Proposals</em> and <em>Templates</em>. Use the
            <em> Template Gallery</em> to start a new proposal from a reusable template with merge
            variables.
          </Bullet>
          <Bullet>
            The <em>AI Proposal Generator</em> can draft a full proposal from a short brief.
          </Bullet>
        </ul>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Sharing &amp; tracking</h4>
        <ul className="space-y-1.5">
          <Bullet>
            Public URL pattern: <code>/proposals/public/&#123;proposal_number&#125;</code>.
          </Bullet>
          <Bullet>
            Each view is logged with timestamp and IP, so you can see view count and last-viewed
            time on the proposal record.
          </Bullet>
          <Bullet>
            Status flow: <em>draft → sent → viewed → accepted / rejected</em>. Proposals can also
            link to a Quote (optional <code>quote_id</code>).
          </Bullet>
        </ul>
      </div>
    ),
  },
  {
    id: 'payments',
    title: 'Payments',
    icon: CreditCardIcon,
    searchText:
      'payments stripe payment intent checkout session invoice subscription customer status pending succeeded failed refunded send invoice',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          The Payments tab is your bridge to Stripe. It records every payment intent, checkout
          session, invoice, and subscription that flows through the system.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Two tabs</h4>
        <ul className="space-y-1.5">
          <Bullet>
            <strong>All Payments:</strong> one-time charges with status pending, sent, succeeded,
            failed, or refunded.
          </Bullet>
          <Bullet>
            <strong>Subscriptions:</strong> recurring billing tied to a Stripe subscription ID, with
            current period dates and a "cancel at period end" flag.
          </Bullet>
        </ul>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">What's stored</h4>
        <ul className="space-y-1.5">
          <Bullet>
            Stripe identifiers: payment intent ID, checkout session ID, invoice ID, and customer ID.
          </Bullet>
          <Bullet>
            Links back to the originating Opportunity, Quote, and CRM contact via the StripeCustomer
            mapping.
          </Bullet>
          <Bullet>
            Receipt URL is captured when available so you can jump to the Stripe receipt directly.
          </Bullet>
        </ul>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Sending an invoice</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Use the <em>Send Invoice</em> button to create a Stripe invoice for a customer. It opens
          a modal where you pick the customer, amount, and items, then sends the Stripe-hosted
          invoice link to the contact's email.
        </p>
      </div>
    ),
  },
  {
    id: 'activities',
    title: 'Activities',
    icon: CalendarIcon,
    searchText:
      'activities calls emails meetings tasks notes timeline calendar list view priority complete due date scheduled reminder polymorphic linking',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Activities are the unified history of every interaction. There are five types — and they
          attach polymorphically to whatever entity they belong to (contact, lead, opportunity, or
          company).
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">The five types</h4>
        <ul className="space-y-1.5">
          <Bullet>
            <strong>Call</strong> — duration in minutes, outcome (connected, voicemail, no answer,
            busy).
          </Bullet>
          <Bullet>
            <strong>Email</strong> — to, cc, and an "opened" flag once the recipient opens it.
          </Bullet>
          <Bullet>
            <strong>Meeting</strong> — location and attendees.
          </Bullet>
          <Bullet>
            <strong>Task</strong> — with a reminder datetime so you don't forget.
          </Bullet>
          <Bullet>
            <strong>Note</strong> — free-form description, no other metadata.
          </Bullet>
        </ul>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Common to all: subject, description, priority (low/normal/high/urgent), completion flag,
          scheduled time, due date, owner, and assignee.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Views</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          The Activities page supports list, timeline, and calendar views with filters by type,
          priority, and status. Inline buttons let you mark complete, edit, or delete without
          leaving the page.
        </p>
        <Tip>
          Activities also appear inside the Activities tab of every Contact, Company, Lead, and
          Opportunity detail page — so you don't have to come back here to see them in context.
        </Tip>
      </div>
    ),
  },
  {
    id: 'campaigns',
    title: 'Campaigns',
    icon: MegaphoneIcon,
    searchText:
      'campaigns email event webinar ads social mass send members template steps delay days metrics roi response rate conversion rate analytics volume stats',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          A Campaign is a one-time marketing effort with a defined audience and (optionally)
          multiple email steps spread out over time. Use it for newsletters, product launches,
          events, and webinars.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Setup</h4>
        <ul className="space-y-1.5">
          <Bullet>
            Pick a type: email, event, webinar, ads, social, or other.
          </Bullet>
          <Bullet>
            Set name, description, start/end dates, target audience, expected revenue/responses,
            and budget vs actual cost.
          </Bullet>
          <Bullet>
            Add <strong>members</strong> from your contacts and leads. Each member tracks status
            (pending, sent, responded, converted) with timestamps.
          </Bullet>
          <Bullet>
            Add <strong>email steps</strong> — each step references a template and has a delay (in
            days) from the previous step. The campaign service automatically processes due steps in
            the background.
          </Bullet>
        </ul>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Status flow</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          <em>planned → active → paused → completed</em>. While active, the campaign auto-advances
          members through email steps as their delays mature.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Analytics</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Each campaign has analytics, volume stats, and ROI calculations (response rate, conversion
          rate, expected vs actual revenue) on its detail page.
        </p>
      </div>
    ),
  },
  {
    id: 'sequences',
    title: 'Sequences',
    icon: QueueListIcon,
    searchText:
      'sequences drip multi step email task wait delay enrollment pause resume cancel sales engagement template',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          A Sequence is a multi-step drip cadence enrolled per contact — think 1:1 sales engagement,
          not bulk marketing. You build a series of email, task, and wait steps once and apply it to
          any contact.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Step types</h4>
        <ul className="space-y-1.5">
          <Bullet>
            <strong>Email</strong> — sends a templated email to the enrolled contact.
          </Bullet>
          <Bullet>
            <strong>Task</strong> — creates a task for the assigned rep (e.g. "Make a follow-up
            call").
          </Bullet>
          <Bullet>
            <strong>Wait</strong> — pauses the sequence for N days before the next step fires.
          </Bullet>
        </ul>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Enrollments</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Each contact you enroll gets its own enrollment record with current step, status (active /
          paused / completed / cancelled), started time, and next-step time. You can pause, resume,
          or delete an enrollment at any time.
        </p>
        <Tip>
          <strong>Campaign vs Sequence vs Workflow.</strong> Campaign = one-time blast with delays.
          Sequence = per-contact drip you control. Workflow = event-triggered automation (next
          section).
        </Tip>
      </div>
    ),
  },
  {
    id: 'workflows',
    title: 'Workflows',
    icon: BoltIcon,
    searchText:
      'workflows automation rules trigger entity event lead opportunity contact activity created updated status changed score actions assign owner conditions',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Workflows are event-triggered automations. They watch your CRM for things like "lead
          score crossed 80" or "opportunity moved to negotiation" and run actions in response.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Trigger</h4>
        <ul className="space-y-1.5">
          <Bullet>
            Pick an entity (lead, opportunity, contact, activity, or company).
          </Bullet>
          <Bullet>
            Pick an event: <em>created, updated, status_changed, score_changed</em>.
          </Bullet>
        </ul>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Conditions</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Optional. JSON-defined predicates like <code>{'{"field": "score", "operator": ">=", "value": 80}'}</code>{' '}
          to filter which trigger events actually fire the rule.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Actions</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          A list of action objects, e.g. <code>{'[{"type": "assign_owner", "value": 1}]'}</code>.
          Each rule can run multiple actions in sequence.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Operating the page</h4>
        <ul className="space-y-1.5">
          <Bullet>
            Workflows render as cards with an active/inactive toggle, the entity type, and a short
            description.
          </Bullet>
          <Bullet>
            Every fire is logged in the executions table with status (success/failed/skipped),
            result, and timestamp — so you can audit what happened.
          </Bullet>
          <Bullet>
            Use the <em>Test</em> action to validate a rule against a sample entity before turning
            it on.
          </Bullet>
        </ul>
      </div>
    ),
  },
  {
    id: 'duplicates',
    title: 'Duplicates',
    icon: DocumentMagnifyingGlassIcon,
    searchText:
      'duplicates dedup detection scan merge primary record contacts companies leads email phone name match similarity',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          The Duplicates page finds and merges accidentally-double records. Important to run after
          big imports.
        </p>
        <ol className="space-y-3">
          <Step n={1}>
            Pick the entity type to scan: contacts, companies, or leads (up to 100 records per
            scan).
          </Step>
          <Step n={2}>
            The scanner groups records that match by email, phone, or name similarity. Each match
            comes with a reason ("Email match", "Phone match", etc.).
          </Step>
          <Step n={3}>
            For each duplicate group, choose the <em>primary</em> record — the one that will be
            kept. Confirm the merge.
          </Step>
          <Step n={4}>
            All activities, notes, tags, and other related records from the secondary are moved
            onto the primary. The secondary is then deleted.
          </Step>
          <Step n={5}>
            The page auto-rescans after a merge so you can sweep through the whole list in one
            sitting.
          </Step>
        </ol>
        <Tip>
          Always pick the more complete record as the primary. Merges are not reversible.
        </Tip>
      </div>
    ),
  },
  {
    id: 'import-export',
    title: 'Import / Export',
    icon: ArrowsRightLeftIcon,
    searchText:
      'import export csv contacts companies leads template column mapping aliases monday linkedin sales navigator preview duplicates contact matching',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Bulk-load and bulk-download Contacts, Companies, and Leads via CSV. Smart column mapping
          handles common formats automatically.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Export</h4>
        <ul className="space-y-1.5">
          <Bullet>
            Pick an entity type and click export. The CSV respects your role-based data scope —
            non-admins only get what they're allowed to see.
          </Bullet>
          <Bullet>
            Each entity also has a <strong>template download</strong> showing the expected column
            headers, so you know exactly what to put in your CSV.
          </Bullet>
        </ul>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Import</h4>
        <ol className="space-y-3">
          <Step n={1}>
            Upload a CSV (max 10MB). The importer auto-detects columns using 100+ aliases — for
            example "firstname", "first_name", "First Name", and "fname" all map to the same field.
            Common Monday.com and LinkedIn Sales Navigator exports work out of the box.
          </Step>
          <Step n={2}>
            Review the mapping. You can fix any unmapped or wrongly-mapped column manually.
          </Step>
          <Step n={3}>
            For company imports that include contact info, the importer detects existing contacts
            by email or phone and shows a confidence score. Exact matches (100%) are auto-selected
            for linking; lower-confidence matches you confirm manually.
          </Step>
          <Step n={4}>
            See a preview of the first rows plus warnings about missing columns. Confirm to import.
          </Step>
          <Step n={5}>
            Result screen shows how many records were imported, how many duplicates were skipped,
            how many contacts were created vs linked, and any field-level errors per row.
          </Step>
        </ol>
      </div>
    ),
  },
  {
    id: 'reports',
    title: 'Reports',
    icon: ChartBarIcon,
    searchText:
      'reports custom builder templates ai natural language saved metrics count sum avg min max group by date day week month quarter year chart bar line pie table export csv schedule share',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          The Reports page is where you slice your CRM data. There are three ways to build a
          report.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">1. From a template</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          The template gallery has pre-built reports for every entity (contacts, companies, leads,
          opportunities, payments, contracts, activities, campaigns). Click <em>Run</em> on any
          template to view the result instantly.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">2. With the builder</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Pick an entity, a metric (count, sum, avg, min, max), an optional metric field, an
          optional group-by field, an optional date grouping (day/week/month/quarter/year),
          filters, and a chart type (bar, line, pie, or table).
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">3. With AI</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Click the <em>AI Generate</em> button and describe what you want in plain English. GPT-4
          parses your prompt into a report definition you can run, edit, or save.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Saved reports</h4>
        <ul className="space-y-1.5">
          <Bullet>
            Save a report once and re-run it anytime. Saved reports also show up in the Dashboard's
            "Add Widget" picker so you can pin them to your home screen.
          </Bullet>
          <Bullet>
            Reports can be exported to CSV from the result view.
          </Bullet>
        </ul>
      </div>
    ),
  },
  {
    id: 'ai-assistant',
    title: 'AI Assistant',
    icon: SparklesIcon,
    searchText:
      'ai assistant chat gpt rag pgvector embeddings recommendations insights summary daily lead opportunity confirmation pending action knowledge document conversation history learning preferences',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          The AI Assistant is a chat interface that has read access to your CRM data and can take
          guarded actions (with your confirmation) on your behalf. Under the hood it uses GPT-4 with
          RAG over pgvector embeddings of your contacts, leads, opportunities, and notes.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">What you can ask</h4>
        <ul className="space-y-1.5">
          <Bullet>"Analyze my sales pipeline"</Bullet>
          <Bullet>"Find stale deals"</Bullet>
          <Bullet>"Show me follow-up priorities"</Bullet>
          <Bullet>"What are my top priorities today"</Bullet>
          <Bullet>"High-value opportunities closing this month"</Bullet>
          <Bullet>"Create a quote and send it"</Bullet>
        </ul>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Insights endpoints</h4>
        <ul className="space-y-1.5">
          <Bullet>
            <strong>Lead insights:</strong> deep analysis of a specific lead and what to do next.
          </Bullet>
          <Bullet>
            <strong>Opportunity insights:</strong> deep analysis of a specific opportunity.
          </Bullet>
          <Bullet>
            <strong>Daily summary:</strong> a digest of today's activities, deals closing, and
            action items.
          </Bullet>
          <Bullet>
            <strong>Recommendations:</strong> next-best-actions ranked by urgency.
          </Bullet>
        </ul>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Confirmation gating</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          When the assistant wants to do something risky (create an opportunity, update a record,
          send an email), it returns a <em>pending action</em> instead of executing immediately.
          You see what it wants to do and click <em>Confirm</em> to actually run it. Every action
          is logged with the function name, arguments, result, risk level, and tokens used.
        </p>
        <Tip>
          You can tune the assistant's behavior in <em>Settings → AI Preferences</em> — communication
          style, priority entities, and custom instructions are all stored per user.
        </Tip>
      </div>
    ),
  },
  {
    id: 'settings',
    title: 'Settings',
    icon: Cog6ToothIcon,
    searchText:
      'settings profile branding white label colors logo footer ai preferences pipeline stages lead sources integrations google calendar meta facebook instagram email warmup webhooks roles permissions assignment rules account status',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Settings is where you configure how your CRM behaves. Most sections are editable by
          everyone; some (Roles &amp; Permissions, Branding) require admin rights.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Sections</h4>
        <ul className="space-y-1.5">
          <Bullet>
            <strong>Profile:</strong> avatar, name, email, phone, job title — your personal account
            info.
          </Bullet>
          <Bullet>
            <strong>Branding (white-label):</strong> company name, primary/secondary/accent colors,
            logo URL, favicon URL, footer text. Applied tenant-wide and visible on quotes and
            proposals you send.
          </Bullet>
          <Bullet>
            <strong>AI Preferences:</strong> communication style and custom instructions for the AI
            Assistant.
          </Bullet>
          <Bullet>
            <strong>Pipeline Stages:</strong> create, rename, reorder, and color your deal stages.
            Set probabilities and the won/lost flags here.
          </Bullet>
          <Bullet>
            <strong>Lead Sources:</strong> manage the dropdown list of sources (referral, website,
            ads, etc.) used on the Leads page.
          </Bullet>
          <Bullet>
            <strong>Integrations:</strong> connect Google Calendar (sync events) and Meta
            (Facebook/Instagram pages, with token expiry visible).
          </Bullet>
          <Bullet>
            <strong>Email Settings:</strong> daily send limit, warmup configuration, and warmup
            schedule.
          </Bullet>
          <Bullet>
            <strong>Webhooks:</strong> configure outbound webhooks for events.
          </Bullet>
          <Bullet>
            <strong>Roles &amp; Permissions:</strong> see your role and the permission matrix.
            Admins can assign roles to other users here.
          </Bullet>
          <Bullet>
            <strong>Lead Auto-Assignment Rules:</strong> rules that automatically route incoming
            leads to specific reps.
          </Bullet>
          <Bullet>
            <strong>Account Status:</strong> read-only — shows whether your account is active, your
            role, and your last login.
          </Bullet>
        </ul>
        <Tip>
          The Notifications, Security (2FA), and Preferences (language/timezone) sections are still
          marked "coming soon" in the current build.
        </Tip>
      </div>
    ),
  },
  {
    id: 'admin',
    title: 'Admin (admins only)',
    icon: ShieldCheckIcon,
    searchText:
      'admin dashboard system stats users active total contacts companies leads opportunities quotes proposals payments user management team overview activity feed audit',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Only users with the admin role see this tab. It's the operational view across the whole
          tenant.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">System stats grid</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Nine top-line numbers: Total Users, Active Users (last 7 days), Total Contacts, Total
          Companies, Total Leads, Total Opportunities, Total Quotes, Total Proposals, Total
          Payments.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">User management</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Create, edit, and deactivate users. Change roles. This is the only place new users get
          provisioned.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Team overview</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Per-user breakdown table: name, role, lead count, opportunity count, total pipeline value,
          and won deals. Sortable by any column.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Activity feed</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          A 30-day chronological log of every action across the system: who did it, what they did
          (create/update/delete), which entity, when. Color-coded so you can spot anything unusual.
        </p>
      </div>
    ),
  },
];
