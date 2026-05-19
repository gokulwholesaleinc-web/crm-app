/* eslint-disable react-refresh/only-export-components -- file intentionally colocates small helper components (Step/Bullet/Tip) with the SECTIONS data structure. */
import { Badge } from '../../components/ui/Badge';
import {
  HomeIcon,
  UserGroupIcon,
  BuildingOfficeIcon,
  FunnelIcon,
  DocumentDuplicateIcon,
  CreditCardIcon,
  CalendarIcon,
  CalendarDaysIcon,
  MegaphoneIcon,
  EnvelopeIcon,
  DocumentMagnifyingGlassIcon,
  ArrowsRightLeftIcon,
  ChartBarIcon,
  Cog6ToothIcon,
  ShieldCheckIcon,
  AcademicCapIcon,
  ArrowRightIcon,
  ShareIcon,
  UserPlusIcon,
  ViewColumnsIcon,
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
      'getting started login sign in google approval account sidebar navigation customize order dark mode theme search global header profile',
    body: (
      <div className="space-y-4">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          The CRM is built around a simple funnel:{' '}
          <strong>Lead → Contact (and optionally Company) → Proposal → Payment</strong>.
          Every other tab — Activities, Email Campaigns, Inbox — exists to help you move records
          through that funnel and keep a full history of what happened along the way.
        </p>

        <div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Signing in
          </h4>
          <ul className="space-y-1.5">
            <Bullet>
              Log in from <code>/login</code> with Google Sign-In. Link Creative CRM no longer
              exposes a password registration form.
            </Bullet>
            <Bullet>
              First-time Google sign-ins wait for admin approval. Admins approve or reject users
              from <strong>Admin → User Approvals</strong> and choose the user&apos;s role.
            </Bullet>
            <Bullet>
              On successful login you land on the Dashboard. Your profile, preferences, theme toggle,
              guide menu, notifications, and sign-out live in the header.
            </Bullet>
          </ul>
        </div>

        <div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Navigating the app
          </h4>
          <ul className="space-y-1.5">
            <Bullet>
              The left sidebar has two groups: a main group (Dashboard, Contacts, Companies,
              Leads, Pipeline, Inbox, Proposals, Payments, Activities, Calendar,
              Email Campaigns) and a secondary group (Import/Export, Reports,
              Settings, Help, Admin, User Approvals, Sharing, Duplicate Cleanup).
            </Bullet>
            <Bullet>
              Click <strong>Customize Menu</strong> at the bottom of the sidebar to drag items into
              whatever order you prefer. Your order is saved per browser. Hit <em>Reset to Default</em>{' '}
              to restore the original layout.
            </Bullet>
            <Bullet>
              The header has a global search that looks across Contacts, Companies,
              Leads, and Proposals. You can also toggle dark mode and start a guide from the header.
            </Bullet>
            <Bullet>
              Admin, User Approvals, Sharing, and Duplicate Cleanup are admin-only in the sidebar,
              and those pages also enforce role checks before loading protected data.
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
    id: 'tutorials',
    title: 'Tutorials (Step-by-Step)',
    icon: AcademicCapIcon,
    searchText:
      'tutorials walkthrough how to send docusign esign electronic signature create invoice charge customer view billings per customer email thread chain inbound reply campaign send mass email',
    body: (
      <div className="space-y-6">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Six common tasks people ask about, click-by-click. Each tutorial is anchorable —
          copy the &ldquo;Direct link&rdquo; line to share a specific walkthrough.
        </p>

        <article id="tutorial-esign" className="scroll-mt-4 border-t border-gray-200 dark:border-gray-700 pt-4">
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-2">
            1. Send a proposal for e-signature
          </h3>
          <p className="text-sm text-gray-700 dark:text-gray-300 mb-3">
            <strong>The CRM has its own e-signature built in</strong> — you don&rsquo;t need a
            separate DocuSign / HelloSign / Adobe Sign account. Proposals include
            a public-link signing flow with drawn signature capture, ESIGN consent,
            signer-email verification, PDF signature placement, and a signed-copy email.
          </p>
          <ol className="space-y-2.5">
            <Step n={1}>
              Open <strong>Proposals</strong> in the sidebar and click
              <em> Create Proposal</em>.
            </Step>
            <Step n={2}>
              Fill in the sections, pick the contact and company, add reference pricing if useful,
              and optionally upload one or more signable PDFs. Reference pricing never auto-charges.
            </Step>
            <Step n={3}>
              Open the proposal detail page and place a signing area on every uploaded signing PDF.
              The send button stays disabled until required signing areas are ready.
            </Step>
            <Step n={4}>
              Click <em>Send</em>. The CRM sends the public link to the designated signer email
              and records status <Badge variant="blue">sent</Badge>. The URL looks like{' '}
              <code>/proposals/public/&#123;token&#125;</code>.
            </Step>
            <Step n={5}>
              The client opens the link, reviews the proposal and signing PDFs, opens
              <em> Sign to Accept</em>, draws their signature, confirms the locked signer email,
              checks the ESIGN/T&amp;C consent box, and submits.
            </Step>
            <Step n={6}>
              Status flips to <Badge variant="green">accepted</Badge>. The CRM stores signer name,
              email, IP, browser user-agent, timestamp, and signature image, stamps signature/date
              onto each signing PDF, and emails the signer a signed copy. Billing is created
              manually from <strong>Payments</strong> after signing.
            </Step>
          </ol>
          <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
            Direct link: <code>/help#tutorial-esign</code>
          </p>
        </article>

        <article id="tutorial-create-invoice" className="scroll-mt-4 border-t border-gray-200 dark:border-gray-700 pt-4">
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-2">
            2. Create and send an invoice
          </h3>
          <p className="text-sm text-gray-700 dark:text-gray-300 mb-3">
            Billing is manual after proposal signing. Use the <em>Send Invoice</em> button when
            you are ready to bill the customer.
          </p>
          <ol className="space-y-2.5">
            <Step n={1}>
              Open <strong>Payments</strong> in the sidebar.
            </Step>
            <Step n={2}>
              Click <em>Send Invoice</em> at the top right. A modal opens.
            </Step>
            <Step n={3}>
              Pick the customer from the dropdown. If you opened billing from a specific contact,
              the modal can sync that contact to Stripe; the global Payments page expects an
              existing Stripe customer.
            </Step>
            <Step n={4}>
              Fill in the amount, description, and how many days until the invoice is due.
              Click <em>Send Invoice</em>.
            </Step>
            <Step n={5}>
              Stripe emails the customer a hosted-invoice link (no login required for them).
              You can track the invoice on the Payments page — status moves from{' '}
              <Badge variant="blue">pending</Badge> to{' '}
              <Badge variant="green">succeeded</Badge> when paid, or{' '}
              <Badge variant="red">failed</Badge> if it expires or is voided.
            </Step>
          </ol>
          <Tip>
            Proposal acceptance does not create a Stripe invoice or checkout session. That keeps
            signature capture and billing intentionally separate.
          </Tip>
          <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
            Direct link: <code>/help#tutorial-create-invoice</code>
          </p>
        </article>

        <article id="tutorial-charge-customer" className="scroll-mt-4 border-t border-gray-200 dark:border-gray-700 pt-4">
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-2">
            3. Charge a customer (one-time or recurring)
          </h3>
          <ol className="space-y-2.5">
            <Step n={1}>
              <strong>One-time charge:</strong> follow tutorial 2 — Send Invoice creates a
              one-shot Stripe invoice the customer pays via card or ACH.
            </Step>
            <Step n={2}>
              <strong>Recurring (subscription):</strong> after the client signs, create the
              subscription manually in the Payments workflow. Proposal pricing blocks are
              reference-only and do not create Stripe Checkout automatically.
            </Step>
            <Step n={3}>
              Recurring charges show up on the Payments page under the{' '}
              <em>Subscriptions</em> tab, and on the customer&rsquo;s contact / company
              detail page under the <em>Payments</em> tab.
            </Step>
          </ol>
          <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
            Direct link: <code>/help#tutorial-charge-customer</code>
          </p>
        </article>

        <article id="tutorial-view-billings" className="scroll-mt-4 border-t border-gray-200 dark:border-gray-700 pt-4">
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-2">
            4. View all billings for a specific customer
          </h3>
          <ol className="space-y-2.5">
            <Step n={1}>
              Open <strong>Contacts</strong> (or <strong>Companies</strong>) and click the
              record you care about.
            </Step>
            <Step n={2}>
              Click the <strong>Payments</strong> tab on the detail page.
            </Step>
            <Step n={3}>
              You&rsquo;ll see two stacked lists: every Stripe payment for this customer
              (one-time charges, invoices) and every active subscription. Click any row to
              jump to the full payment detail page.
            </Step>
            <Step n={4}>
              The <em>Details</em> tab also shows a <em>Payment Summary</em> card with the
              rollups (total paid, on-time rate, last payment date).
            </Step>
          </ol>
          <Tip>
            For a global view across all customers, the main <strong>Payments</strong> page
            still has search-by-name and status filters.
          </Tip>
          <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
            Direct link: <code>/help#tutorial-view-billings</code>
          </p>
        </article>

        <article id="tutorial-email-thread" className="scroll-mt-4 border-t border-gray-200 dark:border-gray-700 pt-4">
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-2">
            5. Read email chains from customers (and reply)
          </h3>
          <p className="text-sm text-gray-700 dark:text-gray-300 mb-3">
            Inbound and outbound emails are auto-threaded by Gmail&rsquo;s thread ID and
            attached to the matching contact, so you see one conversation per thread instead
            of a flat dump.
          </p>
          <ol className="space-y-2.5">
            <Step n={1}>
              Open the contact in <strong>Contacts</strong>.
            </Step>
            <Step n={2}>
              Click the <strong>Emails</strong> tab on their detail page.
            </Step>
            <Step n={3}>
              Each thread shows newest message at the top with previous replies stacked
              below. Inline attachments appear with their filenames; click to download.
            </Step>
            <Step n={4}>
              Click <em>Reply</em> on any message to open the compose modal — your reply is
              quoted automatically and stays in the same thread on the customer&rsquo;s side.
            </Step>
            <Step n={5}>
              <strong>First-time setup:</strong> if you don&rsquo;t see emails, go to{' '}
              <strong>Settings</strong> → <em>Integrations</em> and click{' '}
              <em>Connect Gmail</em> (OAuth, takes ~30 seconds). The CRM polls Gmail
              every 90 seconds and links new messages to the right contact by sender /
              recipient address or thread ID.
            </Step>
          </ol>
          <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
            Direct link: <code>/help#tutorial-email-thread</code>
          </p>
        </article>

        <article id="tutorial-email-campaign" className="scroll-mt-4 border-t border-gray-200 dark:border-gray-700 pt-4">
          <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100 mb-2">
            6. Send an email campaign
          </h3>
          <ol className="space-y-2.5">
            <Step n={1}>
              Go to <strong>Email Campaigns</strong> in the sidebar and click <em>New Campaign</em>.
            </Step>
            <Step n={2}>
              Pick <em>Type = Email</em>, give it a name, and save.
            </Step>
            <Step n={3}>
              On the campaign detail page, click <em>Add Members</em> — pick contacts or
              leads to enroll. You can also bulk-add from the Contacts or Leads list page
              (multi-select → <em>Add to campaign</em>).
            </Step>
            <Step n={4}>
              Click <em>Add Step</em> to build the sequence. Each step is one email
              template with a delay in days from enrollment (e.g. Day 0, Day 3, Day 7).
              Reorder by drag-and-drop.
            </Step>
            <Step n={5}>
              When ready, click <strong>Send Campaign</strong>. The system enrolls every
              member and starts walking each one through the steps as their delays mature.
            </Step>
            <Step n={6}>
              Track results on the same page: sent count, opens, clicks, replies, ROI, and
              the per-member status.
            </Step>
          </ol>
          <p className="mt-3 text-xs text-gray-500 dark:text-gray-400">
            Direct link: <code>/help#tutorial-email-campaign</code>
          </p>
        </article>
      </div>
    ),
  },
  {
    id: 'core-flow',
    title: 'The Core Flow (Read This First)',
    icon: ArrowRightIcon,
    searchText:
      'flow funnel lead contact company proposal payment conversion convert process journey',
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
            The conversion modal creates a Contact (and optionally a Company) from the lead. The
            new contact id is stored on the lead record (<code>converted_contact_id</code>) and the
            lead&apos;s status flips to <em>converted</em>.
          </Step>
          <Step n={3}>
            <strong>The Contact lives in Contacts and Companies.</strong> If the lead's company name
            was set, the converter can create a Company too and link the contact to it. From here on
            you'll see the contact's full history on the Contact detail page.
          </Step>
          <Step n={4}>
            <strong>You build a Proposal.</strong> It links to a Contact and a Company and
            holds longer-form sections (cover letter, scope, pricing, timeline, terms).
            Each has a public share URL you send to the client.
          </Step>
          <Step n={5}>
            <strong>The client accepts or rejects.</strong> The public proposal page
            captures the decision, drawn signature, ESIGN consent, signer email, IP,
            user-agent, and signed timestamp. Status flips to <em>accepted</em> or
            <em> rejected</em>, and signed PDFs are stamped and emailed to the signer.
          </Step>
          <Step n={6}>
            <strong>You collect Payment manually.</strong> The Payments tab creates and tracks
            Stripe payment intents, checkout sessions, invoices, and subscriptions. Proposal
            signing does not create billing.
          </Step>
          <Step n={7}>
            <strong>Activities follow the record everywhere.</strong> Calls, emails, meetings, tasks,
            and notes are logged against whichever entity they belong to. They show up on the
            timeline of every detail page and in the Activities tab.
          </Step>
        </ol>

        <Tip>
          You don't have to follow the funnel strictly. You can create Contacts and Companies
          directly without ever having a Lead — useful for inbound referrals or accounts you
          already know.
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
            <strong>KPI cards:</strong> Total Contacts, Total Leads, Total Revenue — each with a
            trend indicator and a click-through to the relevant tab.
          </Bullet>
          <Bullet>
            <strong>Sales KPIs:</strong> Proposals Sent, Payments Collected, and
            Proposal Conversion Rate.
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
      'contacts contact create edit detail tabs notes activities emails proposals documents attachments history sharing smart list filter search company link',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          A Contact is a person you do business with. Contacts can be linked to a Company, and most
          other records (activities, proposals) hang off a contact.
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
          Open any contact and you&rsquo;ll see tabs for: <em>Details, Activities, Notes, Emails,
          Proposals, Payments, Documents, Attachments, History, Sharing</em>.
          Each is a self-contained view of just the records that belong to this contact —
          including the <strong>Payments</strong> tab, which lists every Stripe charge and
          subscription tied to this customer.
        </p>
      </div>
    ),
  },
  {
    id: 'companies',
    title: 'Companies',
    icon: BuildingOfficeIcon,
    searchText:
      'companies company industry size status prospect customer churned segment custom fields tier sow account manager proposals expenses meta',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Companies group contacts together and act as the parent for proposals
          and expenses tied to that account.
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
          <em>Overview, Proposals, Payments, Activities, Notes, Attachments, History,
          Sharing, Meta (custom fields), Expenses.</em> The Overview tab lists all linked contacts
          as cards.
        </p>
      </div>
    ),
  },
  {
    id: 'leads',
    title: 'Leads',
    icon: FunnelIcon,
    searchText:
      'leads lead score status new contacted qualified unqualified converted lost source pipeline list view bulk actions assign campaign convert contact company budget',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Leads are unqualified prospects you haven't yet converted. They live in their own table
          (separate from Contacts) and have extra fields specific to qualification.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">List view</h4>
        <ul className="space-y-1.5">
          <Bullet>
            The Leads page is the operational list for search, status filtering, bulk actions,
            assignment, campaign enrollment, inline stage updates, and conversion.
          </Bullet>
          <Bullet>
            Search by name, email, or company and filter by status (new, contacted, qualified,
            unqualified, converted, lost). Use the <strong>Pipeline</strong> button for the
            stage-based board.
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
            The modal creates a Contact from the lead&apos;s name, email, phone, address, and job
            title.
          </Step>
          <Step n={3}>
            Tick <em>Also create Company</em> (default on) to create a new Company from the
            lead&apos;s company info and link it to the contact.
          </Step>
          <Step n={4}>
            On submit, the lead&apos;s status flips to <em>converted</em> and the new contact id is
            stored on the lead so you can always trace it back.
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
      'pipeline kanban leads stages drag drop owner filter manager admin board promoted leads probability won lost',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Pipeline is the kanban board for leads that have been promoted into a pipeline stage.
          It is separate from the Leads list so stage movement stays fast and visual.
        </p>
        <ul className="space-y-1.5">
          <Bullet>
            Drag a lead card between columns to update its stage. New leads stay off-board until
            you set a stage from the Leads page or another lead workflow.
          </Bullet>
          <Bullet>
            Search filters visible cards by name, email, or company without losing drag-and-drop.
          </Bullet>
          <Bullet>
            Managers and admins can scope the board by owner; sales reps see the records allowed
            by their data access.
          </Bullet>
          <Bullet>
            Pipeline stage names, colors, probabilities, and won/lost flags are managed in
            <strong> Settings → Pipeline Stages</strong>.
          </Bullet>
        </ul>
      </div>
    ),
  },
  // Quotes help section removed 2026-05-14 — quotes router unmounted;
  // replaced by one-off Payment invoices with optional PDF attachments.
  {
    id: 'proposals',
    title: 'Proposals',
    icon: DocumentDuplicateIcon,
    searchText:
      'proposals proposal cover letter executive summary scope of work pricing timeline terms templates template gallery public link view tracking',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Proposals are long-form sales documents. They support rich content sections
          and reusable templates. Pricing is shown for customer reference; billing is created
          manually from Payments after signing.
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
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Templates</h4>
        <ul className="space-y-1.5">
          <Bullet>
            The Proposals page has two tabs: <em>Proposals</em> and <em>Templates</em>. Use the
            <em> Template Gallery</em> to start a new proposal from a reusable template with merge
            variables.
          </Bullet>
        </ul>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Sharing, e-signature &amp; tracking</h4>
        <ul className="space-y-1.5">
          <Bullet>
            Public URL pattern: <code>/proposals/public/&#123;public_token&#125;</code>.
            The token is an unguessable 32-byte string (not the sequential proposal
            number). Send the link to the client; they don&rsquo;t need an account.
          </Bullet>
          <Bullet>
            The public page lets the designated signer review the proposal, draw a signature,
            confirm their locked signer email, consent to ESIGN/T&amp;C terms, and accept
            (or reject with a reason). Name, email, IP, user-agent, timestamp, and the
            signature image are captured on the proposal record.
          </Bullet>
          <Bullet>
            Uploaded signing PDFs require staff to place a signing area before send. On acceptance,
            the CRM stamps signature and date onto the placed areas and emails the signer a signed copy.
          </Bullet>
          <Bullet>
            Each view is logged with timestamp and IP, so you can see view count and last-viewed
            time on the proposal record.
          </Bullet>
          <Bullet>
            Status flow: <em>draft → sent → viewed → accepted / rejected</em>. Accepting a
            proposal does not create Stripe invoices or checkout sessions.
          </Bullet>
        </ul>
      </div>
    ),
  },
  // Contracts section removed 2026-05-14 — contracts router unmounted;
  // contract terms now fold into the Proposal T&C inline.
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
            Links back to the originating Proposal and CRM contact via the StripeCustomer
            mapping.
          </Bullet>
          <Bullet>
            Receipt URL is captured when available so you can jump to the Stripe receipt directly.
          </Bullet>
        </ul>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Sending an invoice</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Use the <em>Send Invoice</em> button to create a Stripe invoice for a customer after
          you are ready to bill. It opens a modal where you pick the customer, amount, description,
          and due date, then sends the Stripe-hosted invoice link to the customer. Step-by-step in
          <em> Tutorials</em> #2.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Per-customer view</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          To see every payment + subscription for one contact or company, open the contact /
          company detail page and click the <strong>Payments</strong> tab — see{' '}
          <em>Tutorials</em> #4. The global Payments page is for searching across all customers.
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
          attach polymorphically to whatever entity they belong to (contact, lead, or company).
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
          Activities also appear inside the Activities tab of every Contact, Company, and Lead
          detail page — so you don&apos;t have to come back here to see them in context.
        </Tip>
      </div>
    ),
  },
  {
    id: 'calendar',
    title: 'Calendar',
    icon: CalendarDaysIcon,
    searchText:
      'calendar google calendar sync activities meetings tasks scheduled events connect integrations',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Calendar shows scheduled CRM activities alongside synced Google Calendar events.
        </p>
        <ul className="space-y-1.5">
          <Bullet>
            If Google Calendar is connected, use <strong>Sync from Google</strong> to refresh events.
          </Bullet>
          <Bullet>
            If it is not connected, the page links to <strong>Settings → Integrations</strong> so
            you can complete OAuth setup.
          </Bullet>
          <Bullet>
            Activities created in the CRM can also be pushed to Google Calendar from activity
            workflows when the integration is connected.
          </Bullet>
        </ul>
      </div>
    ),
  },
  {
    id: 'campaigns',
    title: 'Email Campaigns',
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
    id: 'inbox',
    title: 'Inbox',
    icon: EnvelopeIcon,
    searchText:
      'inbox email gmail sync received sent thread reply compose contact link unread mark read filter search recent volume stats',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          The Inbox is a unified finder for every email the CRM has synced from Gmail. It is
          intentionally not a Gmail clone — its job is to surface the message you're looking for
          and hand you off to the entity (contact, proposal) where the full
          thread and the reply composer already live.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">What you can do here</h4>
        <ul className="space-y-1.5">
          <Bullet>
            <strong>Filter & paginate.</strong> Filter state is in the URL — share a /inbox link
            with a teammate and they see exactly your view.
          </Bullet>
          <Bullet>
            <strong>Jump to the thread.</strong> Click any row to open the message on its
            related contact, company, or proposal — the reply composer there
            threads correctly into Gmail via the original Message-ID.
          </Bullet>
          <Bullet>
            <strong>Spot unlinked mail.</strong> Emails that haven't been matched to a CRM
            record yet show an amber "Not linked to a contact yet" warning so you can fix the
            link before replying.
          </Bullet>
          <Bullet>
            <strong>Daily send volume</strong> at the top tracks today's outbound count against
            your Gmail daily limit (plus warmup-day budget when applicable) so you can spot a
            sending-cap problem before it becomes a deliverability one.
          </Bullet>
        </ul>
        <Tip>
          Proposals have an <strong>Email Activity</strong> panel on the
          detail page that shows that record's emails specifically, including queue status
          (sent / retry / failed) so you can self-diagnose deliverability.
        </Tip>
      </div>
    ),
  },
  {
    id: 'admin-duplicate-cleanup',
    title: 'Admin Duplicate Cleanup',
    icon: DocumentMagnifyingGlassIcon,
    searchText:
      'duplicates dedup detection scan merge primary record contacts companies leads email phone name match similarity',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          <strong>Admin → Duplicate Cleanup</strong> is admin-only. It finds
          and merges records that already slipped into the CRM. The old <code>/duplicates</code>{' '}
          bookmark redirects here.
        </p>
        <ol className="space-y-3">
          <Step n={1}>
            Pick the entity type to scan: contacts, companies, or leads, then choose the match key
            available for that entity (email, phone, or normalized name).
          </Step>
          <Step n={2}>
            The scanner groups duplicate clusters and shows how many redundant records would be
            removed.
          </Step>
          <Step n={3}>
            For each cluster, choose the winner — usually the most complete or most recently active
            record — and confirm the merge.
          </Step>
          <Step n={4}>
            Activities, proposals, and linked records repoint to the winner. Losing records become
            merged tombstones for audit history and stop appearing in list views.
          </Step>
          <Step n={5}>
            Merge failures are shown inline so you can refresh stale clusters without guessing what
            happened.
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
            Upload a CSV (max 10MB). The importer auto-detects columns from a
            curated alias list (~50 mappings + a few special-case header sets) — for
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
      'reports custom builder templates saved metrics count sum avg min max group by date day week month quarter year chart bar line pie table export csv schedule share',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          The Reports page is where you slice your CRM data. There are two ways to build a
          report.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">1. From a template</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          The template gallery has pre-built reports for every entity (contacts, companies, leads,
          payments, activities, campaigns). Click <em>Run</em> on any template to view
          the result instantly.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">2. With the builder</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Pick an entity, a metric (count, sum, avg, min, max), an optional metric field, an
          optional group-by field, an optional date grouping (day/week/month/quarter/year),
          filters, and a chart type (bar, line, pie, or table).
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
    id: 'settings',
    title: 'Settings',
    icon: Cog6ToothIcon,
    searchText:
      'settings profile branding white label colors logo footer preferences notifications timezone locale currency density navigation signature pipeline stages lead sources integrations google calendar meta facebook instagram email warmup webhooks roles permissions assignment rules account status',
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
            logo URL, favicon URL, footer text. Applied tenant-wide and visible on
            proposals you send.
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
            <strong>Integrations:</strong> connect Gmail (email sync), Google Calendar (event
            sync), and Meta (Facebook/Instagram pages). Token expiry is visible per integration.
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
          <Bullet>
            <strong>Notifications:</strong> manage in-app/email channels, event-level preferences,
            digest behavior, and quiet hours.
          </Bullet>
          <Bullet>
            <strong>Preferences:</strong> set timezone, locale, date/time format, currency, theme,
            default landing page, density, default record tabs, sidebar visibility, and signature.
          </Bullet>
        </ul>
        <Tip>
          Account sign-in is Google-based, so password and 2FA controls are not exposed in this
          build.
        </Tip>
      </div>
    ),
  },
  {
    id: 'admin',
    title: 'Admin (admins only)',
    icon: ShieldCheckIcon,
    searchText:
      'admin dashboard system stats users active total contacts companies leads proposals payments user management team overview activity feed audit',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Only users with the admin role see this tab. It's the operational view across the whole
          tenant.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">System stats grid</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Seven top-line numbers: Total Users, Active Users (last 7 days), Total Contacts, Total
          Companies, Total Leads, Total Proposals, Total Payments.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">User management</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Create, edit, and deactivate users. Change roles. This is the only place new users get
          provisioned.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Team overview</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          Per-user breakdown table: name, role, lead count, total pipeline value, and won deals.
          Sortable by any column.
        </p>
        <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">Activity feed</h4>
        <p className="text-sm text-gray-700 dark:text-gray-300">
          A 30-day chronological log of every action across the system: who did it, what they did
          (create/update/delete), which entity, when. Color-coded so you can spot anything unusual.
        </p>
      </div>
    ),
  },
  {
    id: 'user-approvals',
    title: 'User Approvals',
    icon: UserPlusIcon,
    searchText:
      'user approvals google sign in pending users approve reject unblock rejected emails assign role admin',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          New Google sign-ins do not become active users until an admin approves them.
          Use <strong>Admin → User Approvals</strong> to review pending requests.
        </p>
        <ul className="space-y-1.5">
          <Bullet>
            Pending requests show email, name, requested date, role selector, and approve/reject
            actions.
          </Bullet>
          <Bullet>
            Approving as <strong>admin</strong> has an extra confirmation because it grants full
            tenant access.
          </Bullet>
          <Bullet>
            Rejecting a user can optionally store a reason and adds the email to the rejected list.
            Unblock an email from the same page if the decision changes.
          </Bullet>
        </ul>
      </div>
    ),
  },
  {
    id: 'admin-sharing',
    title: 'Admin Sharing',
    icon: ShareIcon,
    searchText:
      'admin sharing shares audit record access revoke shared with shared by permission manager admin filters',
    body: (
      <div className="space-y-3">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          <strong>Admin → Sharing</strong> is the admin audit surface for record-level
          shares. Use it when you need to inspect or revoke access without opening every record.
        </p>
        <ul className="space-y-1.5">
          <Bullet>
            Filter by entity type, recipient, sharer, or permission level.
          </Bullet>
          <Bullet>
            Each row links back to the shared record and shows who shared it, who received it, and
            when access was granted.
          </Bullet>
          <Bullet>
            Admins and managers can revoke stale shares directly from the table.
          </Bullet>
        </ul>
      </div>
    ),
  },
  {
    id: 'team-collaboration',
    title: 'Team Collaboration',
    icon: ShareIcon,
    searchText:
      'team collaboration sharing share record access permission view edit owner assignee private visibility shared with me notifications admin sharing',
    body: (
      <div className="space-y-4">
        <p className="text-sm text-gray-700 dark:text-gray-300">
          By default, each record belongs to the rep who created it. Sales reps see only their own
          records and records explicitly shared with them. Admins and managers see everything.
        </p>

        <div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Sharing a record
          </h4>
          <ul className="space-y-1.5">
            <Bullet>
              Open any record detail page (
              <a href="/leads" className="text-primary-600 hover:underline dark:text-primary-400">Lead</a>,{' '}
              Proposal,{' '}
              <a href="/contacts" className="text-primary-600 hover:underline dark:text-primary-400">Contact</a>, or{' '}
              <a href="/companies" className="text-primary-600 hover:underline dark:text-primary-400">Company</a>
              ) and click the <strong>Sharing</strong> tab.
            </Bullet>
            <Bullet>
              Click <em>Share</em>, pick a teammate from the dropdown, choose a permission level,
              and confirm.
            </Bullet>
            <Bullet>
              All three permission levels currently grant read + edit access. The
              <strong> View / Edit / Assignee</strong> labels are recorded for future
              differential enforcement and for use in the &ldquo;Shared with me&rdquo;
              widget &mdash; pick whichever best describes the teammate&rsquo;s role.
            </Bullet>
            <Bullet>
              <strong>Assignee</strong> additionally surfaces the record in the teammate&rsquo;s
              &ldquo;my&rdquo; list (e.g. &ldquo;my leads&rdquo;) as if they owned it.
              Use this when two reps are working a deal together.
            </Bullet>
            <Bullet>
              To remove access, click the trash icon next to the share entry. The person who
              shared the record, the recipient, or any admin/manager can revoke it.
            </Bullet>
          </ul>
        </div>

        <div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Shared with me
          </h4>
          <ul className="space-y-1.5">
            <Bullet>
              The{' '}
              <a href="/" className="text-primary-600 hover:underline dark:text-primary-400">Dashboard</a>{' '}
              has a <strong>Shared with me</strong> card listing records other reps have given you
              access to, grouped by type. Click any row to jump straight to the record.
            </Bullet>
          </ul>
        </div>

        <div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Notifications
          </h4>
          <ul className="space-y-1.5">
            <Bullet>
              You get a notification when a teammate shares a record with you, when they assign
              you to a record, and when a proposal you own is signed.
            </Bullet>
            <Bullet>
              In-app notifications appear in the bell icon in the header. Email mirrors follow your
              global notification setting.
            </Bullet>
          </ul>
        </div>

        <div>
          <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-2">
            Admin visibility
          </h4>
          <ul className="space-y-1.5">
            <Bullet>
              Admins and managers see and edit all records regardless of owner or share state.
              They do not need an explicit share to access anything.
            </Bullet>
            <Bullet>
              Admins and managers can audit every share in the system from{' '}
              <a href="/admin/sharing" className="text-primary-600 hover:underline dark:text-primary-400">Admin → Sharing</a>:
              filter by entity type, by who shared, by who received, or by permission level, and
              revoke any share with one click.
            </Bullet>
          </ul>
        </div>

        <Tip>
          Sharing is per-record, not per-folder. If you want a rep to see all your leads, you need
          to share each one individually — or change their role to manager/admin.
        </Tip>
      </div>
    ),
  },
];
