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

  const [formData, setFormData] = useState({
    title: initialData?.title ?? '',
    content: initialData?.content ?? '',
    opportunityId: initialData?.opportunity_id ?? (urlOpportunityId ? parseInt(urlOpportunityId, 10) : null) as number | null,
    contactId: initialData?.contact_id ?? null as number | null,
    companyId: initialData?.company_id ?? null as number | null,
    quoteId: initialData?.quote_id ?? null as number | null,
    executiveSummary: initialData?.executive_summary ?? '',
    scopeOfWork: initialData?.scope_of_work ?? '',
    pricingSection: initialData?.pricing_section ?? '',
    timelineField: initialData?.timeline ?? '',
    terms: initialData?.terms ?? '',
    validUntil: initialData?.valid_until ?? '',
  });

  const updateField = <K extends keyof typeof formData>(field: K, value: typeof formData[K]) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  // Fetch entity lists for dropdowns
  const { data: contactsData } = useContacts({ page_size: 100 });
  const { data: companiesData } = useCompanies({ page_size: 100 });
  const { data: opportunitiesData } = useOpportunities({ page_size: 100 });
  const { data: quotesData } = useQuotes({ page_size: 100 });
  const { data: urlOpportunity } = useOpportunity(
    urlOpportunityId ? parseInt(urlOpportunityId, 10) : undefined
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
            name="title"
            required
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

        <div>
          <label htmlFor="proposal-pricing" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Pricing Section
          </label>
          <textarea
            id="proposal-pricing"
            name="pricing_section"
            rows={3}
            value={formData.pricingSection}
            onChange={(e) => updateField('pricingSection', e.target.value)}
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
        <Button type="submit" disabled={isLoading || !formData.title.trim()}>
          {isLoading ? 'Creating...' : 'Create Proposal'}
        </Button>
      </div>
    </form>
  );
}
