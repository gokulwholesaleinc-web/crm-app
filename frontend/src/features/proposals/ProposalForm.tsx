import { useCallback, useState, useEffect, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Button, SearchableSelect } from '../../components/ui';
import BillingTermsField, { type BillingTermsValue } from '../../components/forms/BillingTermsField';
import { useContacts } from '../../hooks/useContacts';
import { useCompanies } from '../../hooks/useCompanies';
import { useOpportunities, useOpportunity } from '../../hooks/useOpportunities';
import { useQuotes } from '../../hooks/useQuotes';
import { useSubmitShortcut } from '../../hooks/useSubmitShortcut';
import { useUnsavedChangesWarning } from '../../hooks/useUnsavedChangesWarning';
import type { ProposalCreate } from '../../types';

interface ProposalFormProps {
  onSubmit: (data: ProposalCreate) => void;
  onCancel: () => void;
  isLoading?: boolean;
  initialData?: Partial<ProposalCreate>;
}

export function ProposalForm({ onSubmit, onCancel, isLoading, initialData }: ProposalFormProps) {
  const [searchParams] = useSearchParams();
  // Pre-fill any of the four Related Records from URL query params so
  // navigating "Create Proposal" from a contact / company / opportunity
  // / quote detail page lands the user on a form with that link
  // already selected.
  const parseUrlId = (key: string): number | null => {
    const raw = searchParams.get(key);
    if (!raw) return null;
    const n = parseInt(raw, 10);
    return Number.isFinite(n) ? n : null;
  };
  const urlOpportunityId = parseUrlId('opportunity_id');
  const urlContactId = parseUrlId('contact_id');
  const urlCompanyId = parseUrlId('company_id');
  const urlQuoteId = parseUrlId('quote_id');

  const [formData, setFormData] = useState({
    title: initialData?.title ?? '',
    content: initialData?.content ?? '',
    opportunityId: (initialData?.opportunity_id ?? urlOpportunityId) as number | null,
    contactId: (initialData?.contact_id ?? urlContactId) as number | null,
    companyId: (initialData?.company_id ?? urlCompanyId) as number | null,
    quoteId: (initialData?.quote_id ?? urlQuoteId) as number | null,
    executiveSummary: initialData?.executive_summary ?? '',
    scopeOfWork: initialData?.scope_of_work ?? '',
    pricingSection: initialData?.pricing_section ?? '',
    timelineField: initialData?.timeline ?? '',
    terms: initialData?.terms ?? '',
    validUntil: initialData?.valid_until ?? '',
  });

  // Billing terms (pre-cast amount to string for the controlled input).
  const [billing, setBilling] = useState<BillingTermsValue>({
    payment_type: initialData?.payment_type ?? 'one_time',
    recurring_interval: initialData?.recurring_interval ?? null,
    recurring_interval_count: initialData?.recurring_interval_count ?? null,
    amount: initialData?.amount != null ? String(initialData.amount) : '',
    currency: initialData?.currency ?? 'USD',
  });

  // `touched` flips true on first edit; drives the beforeunload warning.
  // ProposalForm uses `useState` so we can't lean on react-hook-form's
  // `formState.isDirty`. Auto-fill from URL opportunity does NOT count.
  const [touched, setTouched] = useState(false);
  useUnsavedChangesWarning(touched);

  // Today (YYYY-MM-DD) for `min` on Valid Until — stable for form lifetime.
  const todayDate = useMemo(() => new Date().toISOString().slice(0, 10), []);

  const formRef = useRef<HTMLFormElement>(null);
  const submitForm = useCallback(() => {
    formRef.current?.requestSubmit();
  }, []);
  useSubmitShortcut(formRef, submitForm);

  const updateField = <K extends keyof typeof formData>(field: K, value: typeof formData[K]) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    setTouched(true);
  };

  // Fetch entity lists for dropdowns
  const { data: contactsData } = useContacts({ page_size: 100 });
  const { data: companiesData } = useCompanies({ page_size: 100 });
  const { data: opportunitiesData } = useOpportunities({ page_size: 100 });
  const { data: quotesData } = useQuotes({ page_size: 100 });
  const { data: urlOpportunity } = useOpportunity(
    urlOpportunityId ?? undefined,
  );

  const contacts = useMemo(() => contactsData?.items ?? [], [contactsData]);
  const companies = useMemo(() => companiesData?.items ?? [], [companiesData]);
  const opportunities = useMemo(() => opportunitiesData?.items ?? [], [opportunitiesData]);
  const quotes = useMemo(() => quotesData?.items ?? [], [quotesData]);

  const opportunityOptions = useMemo(
    () => opportunities.map((o) => ({ value: o.id, label: o.name })),
    [opportunities]
  );
  const quoteOptions = useMemo(
    () => quotes.map((q) => ({ value: q.id, label: `${q.title} (${q.quote_number})` })),
    [quotes]
  );
  const contactOptions = useMemo(
    () => contacts.map((c) => ({ value: c.id, label: c.full_name })),
    [contacts]
  );
  const companyOptions = useMemo(
    () => companies.map((c) => ({ value: c.id, label: c.name })),
    [companies]
  );

  // Auto-fill contact/company from URL opportunity
  useEffect(() => {
    if (urlOpportunity) {
      setFormData((prev) => ({
        ...prev,
        contactId: urlOpportunity.contact_id && !prev.contactId ? urlOpportunity.contact_id : prev.contactId,
        companyId: urlOpportunity.company_id && !prev.companyId ? urlOpportunity.company_id : prev.companyId,
      }));
    }
  }, [urlOpportunity]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const amountTrimmed = billing.amount.trim();
    const amountValue = amountTrimmed === '' ? null : amountTrimmed;

    const data: ProposalCreate = {
      title: formData.title,
      content: formData.content || null,
      executive_summary: formData.executiveSummary || null,
      scope_of_work: formData.scopeOfWork || null,
      pricing_section: formData.pricingSection || null,
      timeline: formData.timelineField || null,
      terms: formData.terms || null,
      valid_until: formData.validUntil || null,
      status: 'draft',
      opportunity_id: formData.opportunityId,
      contact_id: formData.contactId,
      company_id: formData.companyId,
      quote_id: formData.quoteId,
      payment_type: billing.payment_type,
      recurring_interval: billing.recurring_interval,
      recurring_interval_count: billing.recurring_interval_count,
      amount: amountValue,
      currency: billing.currency,
    };

    onSubmit(data);
  };

  const handleBillingChange = (next: BillingTermsValue) => {
    setBilling(next);
    setTouched(true);
  };

  return (
    <form ref={formRef} onSubmit={handleSubmit} className="space-y-6">
      <div className="space-y-4">
        <div>
          <label htmlFor="proposal-title" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Title *
          </label>
          <input
            type="text"
            id="proposal-title"
            name="title"
            required
            autoFocus
            value={formData.title}
            onChange={(e) => updateField('title', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Proposal title..."
          />
        </div>

        <div>
          <label htmlFor="proposal-content" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Content
          </label>
          <textarea
            id="proposal-content"
            name="content"
            rows={3}
            value={formData.content}
            onChange={(e) => updateField('content', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Overall proposal content..."
          />
        </div>

        <div>
          <label htmlFor="proposal-exec-summary" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Executive Summary
          </label>
          <textarea
            id="proposal-exec-summary"
            name="executive_summary"
            rows={3}
            value={formData.executiveSummary}
            onChange={(e) => updateField('executiveSummary', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Executive summary..."
          />
        </div>

        <div>
          <label htmlFor="proposal-scope" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Scope of Work
          </label>
          <textarea
            id="proposal-scope"
            name="scope_of_work"
            rows={3}
            value={formData.scopeOfWork}
            onChange={(e) => updateField('scopeOfWork', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Scope of work details..."
          />
        </div>

        <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-800/40 space-y-4">
          <div>
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              Billing
            </h3>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
              Controls what gets charged when the client accepts. Leave amount
              blank to skip automatic invoicing.
            </p>
          </div>
          <BillingTermsField
            value={billing}
            onChange={handleBillingChange}
            amountHelpText="Total invoice amount (one-time) or per-period amount (subscription)."
          />
        </div>

        <div>
          <label htmlFor="proposal-pricing" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Pricing Notes
          </label>
          <textarea
            id="proposal-pricing"
            name="pricing_section"
            rows={3}
            value={formData.pricingSection}
            onChange={(e) => updateField('pricingSection', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Additional pricing context shown to the client (line-item breakdowns, assumptions, etc.)"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="proposal-timeline" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Timeline
            </label>
            <textarea
              id="proposal-timeline"
              name="timeline"
              rows={2}
              value={formData.timelineField}
              onChange={(e) => updateField('timelineField', e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
              placeholder="Project timeline..."
            />
          </div>
          <div>
            <label htmlFor="proposal-valid-until" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Valid Until
            </label>
            <input
              type="date"
              id="proposal-valid-until"
              name="valid_until"
              min={todayDate}
              value={formData.validUntil}
              onChange={(e) => updateField('validUntil', e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            />
          </div>
        </div>

        <div>
          <label htmlFor="proposal-terms" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Terms
          </label>
          <textarea
            id="proposal-terms"
            name="terms"
            rows={2}
            value={formData.terms}
            onChange={(e) => updateField('terms', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Terms and conditions..."
          />
        </div>
      </div>

      {/* Related Records */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Related Records</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <SearchableSelect
            label="Opportunity"
            id="proposal-opportunity"
            name="opportunity_id"
            value={formData.opportunityId}
            onChange={(val) => {
              setFormData((prev) => {
                const updates: Partial<typeof prev> = { opportunityId: val };
                if (val) {
                  const opp = opportunities.find((o) => o.id === val);
                  if (opp?.contact_id) updates.contactId = opp.contact_id;
                  if (opp?.company_id) updates.companyId = opp.company_id;
                }
                return { ...prev, ...updates };
              });
              setTouched(true);
            }}
            options={opportunityOptions}
            placeholder="Search opportunities..."
          />
          <SearchableSelect
            label="Quote"
            id="proposal-quote"
            name="quote_id"
            value={formData.quoteId}
            onChange={(val) => updateField('quoteId', val)}
            options={quoteOptions}
            placeholder="Search quotes..."
          />
          <SearchableSelect
            label="Contact"
            id="proposal-contact"
            name="contact_id"
            value={formData.contactId}
            onChange={(val) => updateField('contactId', val)}
            options={contactOptions}
            placeholder="Search contacts..."
          />
          <SearchableSelect
            label="Company"
            id="proposal-company"
            name="company_id"
            value={formData.companyId}
            onChange={(val) => updateField('companyId', val)}
            options={companyOptions}
            placeholder="Search companies..."
          />
        </div>
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={!formData.title.trim()} isLoading={isLoading}>
          Create Proposal
        </Button>
      </div>
    </form>
  );
}
