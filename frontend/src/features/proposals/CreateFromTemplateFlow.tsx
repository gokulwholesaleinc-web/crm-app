import { useState, useMemo } from 'react';
import { Button, SearchableSelect } from '../../components/ui';
import { useContacts } from '../../hooks/useContacts';
import { useCompanies } from '../../hooks/useCompanies';
import { useCreateFromTemplate } from '../../hooks/useProposals';
import { showSuccess, showError } from '../../utils/toast';
import type { ProposalTemplate } from '../../types';

interface CreateFromTemplateFlowProps {
  template: ProposalTemplate;
  onCancel: () => void;
  onCreated: (proposalId: number) => void;
}

const MERGE_VARIABLE_REGEX = /\{\{(\w+)\}\}/g;

export function CreateFromTemplateFlow({ template, onCancel, onCreated }: CreateFromTemplateFlowProps) {
  const [contactId, setContactId] = useState<number | null>(null);
  const [companyId, setCompanyId] = useState<number | null>(null);
  const [step, setStep] = useState<'select' | 'preview'>('select');

  const { data: contactsData } = useContacts({ page_size: 100 });
  const { data: companiesData } = useCompanies({ page_size: 100 });
  const createFromTemplateMutation = useCreateFromTemplate();

  const contacts = contactsData?.items ?? [];
  const companies = companiesData?.items ?? [];

  const contactOptions = useMemo(
    () => contacts.map((c) => ({ value: c.id, label: c.full_name })),
    [contacts]
  );
  const companyOptions = useMemo(
    () => companies.map((c) => ({ value: c.id, label: c.name })),
    [companies]
  );

  const selectedContact = contacts.find((c) => c.id === contactId);
  const selectedCompany = companies.find((c) => c.id === companyId);

  const previewBody = useMemo(() => {
    if (!selectedContact) return template.body;
    const variables: Record<string, string> = {
      contact_name: selectedContact.full_name,
      company_name: selectedCompany?.name ?? '',
      date: new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }),
      contact_email: selectedContact.email ?? '',
      contact_phone: selectedContact.phone ?? '',
      company_address: selectedCompany
        ? [selectedCompany.address_line1, selectedCompany.city, selectedCompany.state, selectedCompany.country]
            .filter(Boolean)
            .join(', ')
        : '',
    };
    return template.body.replace(MERGE_VARIABLE_REGEX, (match, key) => variables[key] ?? match);
  }, [template.body, selectedContact, selectedCompany]);

  const previewLegal = useMemo(() => {
    if (!template.legal_terms || !selectedContact) return template.legal_terms ?? '';
    const variables: Record<string, string> = {
      contact_name: selectedContact.full_name,
      company_name: selectedCompany?.name ?? '',
      date: new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' }),
      contact_email: selectedContact.email ?? '',
      contact_phone: selectedContact.phone ?? '',
      company_address: selectedCompany
        ? [selectedCompany.address_line1, selectedCompany.city, selectedCompany.state, selectedCompany.country]
            .filter(Boolean)
            .join(', ')
        : '',
    };
    return template.legal_terms.replace(MERGE_VARIABLE_REGEX, (match, key) => variables[key] ?? match);
  }, [template.legal_terms, selectedContact, selectedCompany]);

  const handleCreate = async () => {
    if (!contactId) return;
    try {
      const proposal = await createFromTemplateMutation.mutateAsync({
        template_id: template.id,
        contact_id: contactId,
        company_id: companyId,
      });
      showSuccess('Proposal created from template');
      onCreated(proposal.id);
    } catch {
      showError('Failed to create proposal from template');
    }
  };

  if (step === 'select') {
    return (
      <div className="space-y-5">
        <div>
          <SearchableSelect
            label="Contact *"
            id="from-template-contact"
            name="contact_id"
            value={contactId}
            onChange={(val) => setContactId(val)}
            options={contactOptions}
            placeholder="Select a contact..."
          />
        </div>
        <div>
          <SearchableSelect
            label="Company"
            id="from-template-company"
            name="company_id"
            value={companyId}
            onChange={(val) => setCompanyId(val)}
            options={companyOptions}
            placeholder="Select a company (optional)..."
          />
        </div>

        <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
          <Button type="button" variant="secondary" onClick={onCancel}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={!contactId}
            onClick={() => setStep('preview')}
          >
            Preview
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Preview</h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
          Merge variables have been filled with the selected contact/company data.
        </p>
      </div>

      <div>
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
          Body
        </label>
        <div className="bg-gray-50 dark:bg-gray-900 rounded-md border border-gray-200 dark:border-gray-700 p-3 text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap max-h-60 overflow-y-auto">
          {previewBody}
        </div>
      </div>

      {previewLegal && (
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Legal Terms
          </label>
          <div className="bg-amber-50 dark:bg-amber-900/10 rounded-md border border-amber-200 dark:border-amber-700 p-3 text-sm text-gray-800 dark:text-gray-200 whitespace-pre-wrap max-h-40 overflow-y-auto">
            {previewLegal}
          </div>
        </div>
      )}

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button type="button" variant="secondary" onClick={() => setStep('select')}>
          Back
        </Button>
        <Button
          type="button"
          onClick={handleCreate}
          disabled={createFromTemplateMutation.isPending}
        >
          {createFromTemplateMutation.isPending ? 'Creating...' : 'Create Proposal'}
        </Button>
      </div>
    </div>
  );
}
