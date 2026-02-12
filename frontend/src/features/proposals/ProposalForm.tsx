import { useState, useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Button, SearchableSelect } from '../../components/ui';
import { useContacts } from '../../hooks/useContacts';
import { useCompanies } from '../../hooks/useCompanies';
import { useOpportunities, useOpportunity } from '../../hooks/useOpportunities';
import { useQuotes } from '../../hooks/useQuotes';
import type { ProposalCreate } from '../../types';

interface ProposalFormProps {
  onSubmit: (data: ProposalCreate) => void;
  onCancel: () => void;
  isLoading?: boolean;
  initialData?: Partial<ProposalCreate>;
}

export function ProposalForm({ onSubmit, onCancel, isLoading, initialData }: ProposalFormProps) {
  const [searchParams] = useSearchParams();
  const urlOpportunityId = searchParams.get('opportunity_id');

  const [title, setTitle] = useState(initialData?.title ?? '');
  const [content, setContent] = useState(initialData?.content ?? '');
  const [opportunityId, setOpportunityId] = useState<number | null>(
    initialData?.opportunity_id ?? (urlOpportunityId ? parseInt(urlOpportunityId, 10) : null)
  );
  const [contactId, setContactId] = useState<number | null>(initialData?.contact_id ?? null);
  const [companyId, setCompanyId] = useState<number | null>(initialData?.company_id ?? null);
  const [quoteId, setQuoteId] = useState<number | null>(initialData?.quote_id ?? null);

  // Fetch entity lists for dropdowns
  const { data: contactsData } = useContacts({ page_size: 100 });
  const { data: companiesData } = useCompanies({ page_size: 100 });
  const { data: opportunitiesData } = useOpportunities({ page_size: 100 });
  const { data: quotesData } = useQuotes({ page_size: 100 });
  const { data: urlOpportunity } = useOpportunity(
    urlOpportunityId ? parseInt(urlOpportunityId, 10) : undefined
  );

  const contacts = contactsData?.items ?? [];
  const companies = companiesData?.items ?? [];
  const opportunities = opportunitiesData?.items ?? [];
  const quotes = quotesData?.items ?? [];

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
      if (urlOpportunity.contact_id && !contactId) {
        setContactId(urlOpportunity.contact_id);
      }
      if (urlOpportunity.company_id && !companyId) {
        setCompanyId(urlOpportunity.company_id);
      }
    }
  }, [urlOpportunity]); // eslint-disable-line react-hooks/exhaustive-deps

  const [executiveSummary, setExecutiveSummary] = useState(initialData?.executive_summary ?? '');
  const [scopeOfWork, setScopeOfWork] = useState(initialData?.scope_of_work ?? '');
  const [pricingSection, setPricingSection] = useState(initialData?.pricing_section ?? '');
  const [timelineField, setTimelineField] = useState(initialData?.timeline ?? '');
  const [terms, setTerms] = useState(initialData?.terms ?? '');
  const [validUntil, setValidUntil] = useState(initialData?.valid_until ?? '');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const data: ProposalCreate = {
      title,
      content: content || null,
      executive_summary: executiveSummary || null,
      scope_of_work: scopeOfWork || null,
      pricing_section: pricingSection || null,
      timeline: timelineField || null,
      terms: terms || null,
      valid_until: validUntil || null,
      status: 'draft',
      opportunity_id: opportunityId,
      contact_id: contactId,
      company_id: companyId,
      quote_id: quoteId,
    };

    onSubmit(data);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="space-y-4">
        <div>
          <label htmlFor="proposal-title" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Title *
          </label>
          <input
            type="text"
            id="proposal-title"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
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
            rows={3}
            value={content}
            onChange={(e) => setContent(e.target.value)}
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
            rows={3}
            value={executiveSummary}
            onChange={(e) => setExecutiveSummary(e.target.value)}
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
            rows={3}
            value={scopeOfWork}
            onChange={(e) => setScopeOfWork(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Scope of work details..."
          />
        </div>

        <div>
          <label htmlFor="proposal-pricing" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Pricing Section
          </label>
          <textarea
            id="proposal-pricing"
            rows={3}
            value={pricingSection}
            onChange={(e) => setPricingSection(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Pricing details..."
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="proposal-timeline" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Timeline
            </label>
            <textarea
              id="proposal-timeline"
              rows={2}
              value={timelineField}
              onChange={(e) => setTimelineField(e.target.value)}
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
              value={validUntil}
              onChange={(e) => setValidUntil(e.target.value)}
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
            rows={2}
            value={terms}
            onChange={(e) => setTerms(e.target.value)}
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
            value={opportunityId}
            onChange={(val) => {
              setOpportunityId(val);
              if (val) {
                const opp = opportunities.find((o) => o.id === val);
                if (opp?.contact_id) setContactId(opp.contact_id);
                if (opp?.company_id) setCompanyId(opp.company_id);
              }
            }}
            options={opportunityOptions}
            placeholder="Search opportunities..."
          />
          <SearchableSelect
            label="Quote"
            id="proposal-quote"
            name="quote_id"
            value={quoteId}
            onChange={setQuoteId}
            options={quoteOptions}
            placeholder="Search quotes..."
          />
          <SearchableSelect
            label="Contact"
            id="proposal-contact"
            name="contact_id"
            value={contactId}
            onChange={setContactId}
            options={contactOptions}
            placeholder="Search contacts..."
          />
          <SearchableSelect
            label="Company"
            id="proposal-company"
            name="company_id"
            value={companyId}
            onChange={setCompanyId}
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
        <Button type="submit" disabled={isLoading || !title.trim()}>
          {isLoading ? 'Creating...' : 'Create Proposal'}
        </Button>
      </div>
    </form>
  );
}
