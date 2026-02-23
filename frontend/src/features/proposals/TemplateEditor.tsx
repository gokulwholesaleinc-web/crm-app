import { useState } from 'react';
import { Button } from '../../components/ui';
import type { ProposalTemplateCreate } from '../../types';

const MERGE_VARIABLES = [
  { key: 'contact_name', label: 'Contact Name' },
  { key: 'company_name', label: 'Company Name' },
  { key: 'date', label: 'Date' },
  { key: 'contact_email', label: 'Contact Email' },
  { key: 'contact_phone', label: 'Contact Phone' },
  { key: 'company_address', label: 'Company Address' },
];

const CATEGORY_OPTIONS = [
  { value: '', label: 'No Category' },
  { value: 'service', label: 'Service' },
  { value: 'product', label: 'Product' },
  { value: 'consulting', label: 'Consulting' },
  { value: 'retainer', label: 'Retainer' },
];

interface TemplateEditorProps {
  onSubmit: (data: ProposalTemplateCreate) => void;
  onCancel: () => void;
  isLoading?: boolean;
  initialData?: Partial<ProposalTemplateCreate>;
  submitLabel?: string;
}

export function TemplateEditor({
  onSubmit,
  onCancel,
  isLoading,
  initialData,
  submitLabel = 'Create Template',
}: TemplateEditorProps) {
  const [name, setName] = useState(initialData?.name ?? '');
  const [description, setDescription] = useState(initialData?.description ?? '');
  const [body, setBody] = useState(initialData?.body ?? '');
  const [legalTerms, setLegalTerms] = useState(initialData?.legal_terms ?? '');
  const [category, setCategory] = useState(initialData?.category ?? '');
  const [isDefault, setIsDefault] = useState(initialData?.is_default ?? false);

  const insertVariable = (variable: string, target: 'body' | 'legal') => {
    const tag = `{{${variable}}}`;
    const textarea = document.getElementById(
      target === 'body' ? 'template-body' : 'template-legal-terms'
    ) as HTMLTextAreaElement | null;

    if (textarea) {
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const currentValue = target === 'body' ? body : legalTerms;
      const newValue = currentValue.substring(0, start) + tag + currentValue.substring(end);
      if (target === 'body') {
        setBody(newValue);
      } else {
        setLegalTerms(newValue);
      }
      requestAnimationFrame(() => {
        textarea.focus();
        textarea.setSelectionRange(start + tag.length, start + tag.length);
      });
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      name,
      body,
      description: description || null,
      legal_terms: legalTerms || null,
      category: category || null,
      is_default: isDefault,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div>
        <label htmlFor="template-name" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          Template Name *
        </label>
        <input
          type="text"
          id="template-name"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
          placeholder="e.g., Standard Consulting Proposal..."
        />
      </div>

      <div>
        <label htmlFor="template-description" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          Description
        </label>
        <input
          type="text"
          id="template-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
          placeholder="Brief description of the template..."
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label htmlFor="template-category" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Category
          </label>
          <select
            id="template-category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
          >
            {CATEGORY_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-end pb-1">
          <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
            <input
              type="checkbox"
              checked={isDefault}
              onChange={(e) => setIsDefault(e.target.checked)}
              className="rounded border-gray-300 dark:border-gray-600 text-primary-600 focus:ring-primary-500"
            />
            Set as default template
          </label>
        </div>
      </div>

      {/* Merge variable toolbar */}
      <div>
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
          Insert Merge Variable into Body:
        </p>
        <div className="flex flex-wrap gap-1.5">
          {MERGE_VARIABLES.map((v) => (
            <button
              key={v.key}
              type="button"
              onClick={() => insertVariable(v.key, 'body')}
              className="inline-flex items-center px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-primary-50 dark:hover:bg-primary-900/20 hover:border-primary-300 dark:hover:border-primary-600 transition-colors"
            >
              {`{{${v.key}}}`}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label htmlFor="template-body" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          Body *
        </label>
        <textarea
          id="template-body"
          required
          rows={8}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm font-mono text-sm"
          placeholder="Dear {{contact_name}},&#10;&#10;We are pleased to present this proposal to {{company_name}}..."
        />
      </div>

      {/* Legal terms merge variable toolbar */}
      <div>
        <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">
          Insert Merge Variable into Legal Terms:
        </p>
        <div className="flex flex-wrap gap-1.5">
          {MERGE_VARIABLES.map((v) => (
            <button
              key={v.key}
              type="button"
              onClick={() => insertVariable(v.key, 'legal')}
              className="inline-flex items-center px-2 py-1 text-xs rounded border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-primary-50 dark:hover:bg-primary-900/20 hover:border-primary-300 dark:hover:border-primary-600 transition-colors"
            >
              {`{{${v.key}}}`}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label htmlFor="template-legal-terms" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          Legal Terms
        </label>
        <textarea
          id="template-legal-terms"
          rows={5}
          value={legalTerms}
          onChange={(e) => setLegalTerms(e.target.value)}
          className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm font-mono text-sm"
          placeholder="Legal language and terms of service..."
        />
      </div>

      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={isLoading || !name.trim() || !body.trim()}>
          {isLoading ? 'Saving...' : submitLabel}
        </Button>
      </div>
    </form>
  );
}
