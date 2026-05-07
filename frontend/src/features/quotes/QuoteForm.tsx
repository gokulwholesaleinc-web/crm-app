import { useState, useEffect, useRef, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';
import { TrashIcon, PlusIcon, CubeIcon } from '@heroicons/react/24/outline';
import { Button, SearchableSelect } from '../../components/ui';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import BillingTermsField, { type BillingTermsValue } from '../../components/forms/BillingTermsField';
import { useContacts } from '../../hooks/useContacts';
import { useCompanies } from '../../hooks/useCompanies';
import { useOpportunities, useOpportunity } from '../../hooks/useOpportunities';
import { useBundles } from '../../hooks/useQuotes';
import { useFormSubmitShortcut } from '../../hooks/useSubmitShortcut';
import { useUnsavedChangesWarning } from '../../hooks/useUnsavedChangesWarning';
import { clampNumberInput } from '../../utils/inputNormalize';
import type { QuoteCreate, QuoteLineItemCreate, ProductBundle } from '../../types';

interface QuoteFormProps {
  onSubmit: (data: QuoteCreate) => void;
  onCancel: () => void;
  isLoading?: boolean;
  initialData?: Partial<QuoteCreate>;
}

const EMPTY_LINE_ITEM: QuoteLineItemCreate = {
  description: '',
  quantity: 1,
  unit_price: 0,
  discount: 0,
  sort_order: 0,
};

const DEFAULT_FORM_STATE = {
  title: '',
  description: '',
  contactId: null as number | null,
  companyId: null as number | null,
  opportunityId: null as number | null,
  currency: 'USD',
  validUntil: '',
  discountType: '',
  discountValue: 0,
  taxRate: 0,
  termsAndConditions: '',
  notes: '',
};

function initialBillingValue(initialData?: Partial<QuoteCreate>): BillingTermsValue {
  // Translate legacy `recurring_interval` values ('monthly', 'quarterly',
  // 'yearly') coming from a quote that was stored before the Stripe-
  // native split. The component expects 'month'/'year' + count.
  const LEGACY: Record<string, { interval: 'month' | 'year'; count: number }> = {
    monthly: { interval: 'month', count: 1 },
    quarterly: { interval: 'month', count: 3 },
    bi_yearly: { interval: 'month', count: 6 },
    yearly: { interval: 'year', count: 1 },
  };
  const raw = initialData?.recurring_interval ?? null;
  if (raw && LEGACY[raw]) {
    return {
      payment_type: 'subscription',
      recurring_interval: LEGACY[raw].interval,
      recurring_interval_count: initialData?.recurring_interval_count ?? LEGACY[raw].count,
      amount: '',
      currency: initialData?.currency ?? 'USD',
    };
  }
  return {
    payment_type: (initialData?.payment_type as 'one_time' | 'subscription') ?? 'one_time',
    recurring_interval: (raw as 'month' | 'year' | null) ?? null,
    recurring_interval_count: initialData?.recurring_interval_count ?? null,
    amount: '',
    currency: initialData?.currency ?? 'USD',
  };
}

export function QuoteForm({ onSubmit, onCancel, isLoading, initialData }: QuoteFormProps) {
  const [searchParams] = useSearchParams();
  const urlOpportunityId = searchParams.get('opportunity_id');

  const [formData, setFormData] = useState(() => ({
    ...DEFAULT_FORM_STATE,
    title: initialData?.title ?? DEFAULT_FORM_STATE.title,
    description: initialData?.description ?? DEFAULT_FORM_STATE.description,
    contactId: initialData?.contact_id ?? DEFAULT_FORM_STATE.contactId,
    companyId: initialData?.company_id ?? DEFAULT_FORM_STATE.companyId,
    opportunityId: initialData?.opportunity_id ?? (urlOpportunityId ? parseInt(urlOpportunityId, 10) : null),
    currency: initialData?.currency ?? DEFAULT_FORM_STATE.currency,
    validUntil: initialData?.valid_until ?? DEFAULT_FORM_STATE.validUntil,
    discountType: initialData?.discount_type ?? DEFAULT_FORM_STATE.discountType,
    discountValue: initialData?.discount_value ?? DEFAULT_FORM_STATE.discountValue,
    taxRate: initialData?.tax_rate ?? DEFAULT_FORM_STATE.taxRate,
    termsAndConditions: initialData?.terms_and_conditions ?? DEFAULT_FORM_STATE.termsAndConditions,
    notes: initialData?.notes ?? DEFAULT_FORM_STATE.notes,
  }));

  const [billing, setBilling] = useState<BillingTermsValue>(() => initialBillingValue(initialData));

  const handleBillingChange = (next: BillingTermsValue) => {
    setBilling(next);
    setTouched(true);
  };

  // `touched` is a one-way sentinel that flips true the first time the
  // user edits any field or line item. Drives the beforeunload warning
  // — the form uses `useState` instead of react-hook-form so we can't
  // lean on `formState.isDirty` the way the other forms do.
  const [touched, setTouched] = useState(false);
  useUnsavedChangesWarning(touched);

  const [pendingDeleteIndex, setPendingDeleteIndex] = useState<number | null>(null);

  const formRef = useFormSubmitShortcut();

  const updateField = <K extends keyof typeof formData>(field: K, value: typeof formData[K]) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
    setTouched(true);
  };

  // Fetch entity lists for dropdowns
  const { data: contactsData } = useContacts({ page_size: 100 });
  const { data: companiesData } = useCompanies({ page_size: 100 });
  const { data: opportunitiesData } = useOpportunities({ page_size: 100 });
  const { data: urlOpportunity } = useOpportunity(
    urlOpportunityId ? parseInt(urlOpportunityId, 10) : undefined
  );

  const contacts = useMemo(() => contactsData?.items ?? [], [contactsData]);
  const companies = useMemo(() => companiesData?.items ?? [], [companiesData]);
  const opportunities = useMemo(() => opportunitiesData?.items ?? [], [opportunitiesData]);

  const opportunityOptions = useMemo(
    () => opportunities.map((o) => ({ value: o.id, label: o.name })),
    [opportunities]
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

  const [lineItems, setLineItems] = useState<QuoteLineItemCreate[]>(
    initialData?.line_items ?? [{ ...EMPTY_LINE_ITEM }]
  );

  const [showBundleMenu, setShowBundleMenu] = useState(false);
  const bundleMenuRef = useRef<HTMLDivElement>(null);
  const { data: bundlesData } = useBundles({ is_active: true });
  const activeBundles = bundlesData?.items ?? [];

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (bundleMenuRef.current && !bundleMenuRef.current.contains(event.target as Node)) {
        setShowBundleMenu(false);
      }
    }
    if (showBundleMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showBundleMenu]);

  const addBundleItems = (bundle: ProductBundle) => {
    const newItems: QuoteLineItemCreate[] = bundle.items.map((item, idx) => ({
      description: item.description,
      quantity: item.quantity,
      unit_price: item.unit_price,
      discount: 0,
      sort_order: lineItems.length + idx,
    }));
    setLineItems((curr) => [...curr.filter((i) => i.description.trim() !== '' || curr.length === 1), ...newItems]);
    setShowBundleMenu(false);
    setTouched(true);
  };

  const addLineItem = () => {
    setLineItems((curr) => [...curr, { ...EMPTY_LINE_ITEM, sort_order: curr.length }]);
    setTouched(true);
  };

  const removeLineItem = (index: number) => {
    setLineItems((curr) => curr.filter((_, i) => i !== index));
    setTouched(true);
  };

  const updateLineItem = (index: number, field: keyof QuoteLineItemCreate, value: string | number) => {
    setLineItems((curr) =>
      curr.map((item, i) => (i === index ? { ...item, [field]: value } : item))
    );
    setTouched(true);
  };

  const calculateItemTotal = (item: QuoteLineItemCreate): number => {
    return ((item.quantity ?? 1) * (item.unit_price ?? 0)) - (item.discount ?? 0);
  };

  const subtotal = lineItems.reduce((sum, item) => sum + calculateItemTotal(item), 0);
  const discountAmount = formData.discountType === 'percent'
    ? subtotal * (formData.discountValue / 100)
    : formData.discountType === 'fixed'
      ? formData.discountValue
      : 0;
  const afterDiscount = subtotal - discountAmount;
  const taxAmount = afterDiscount * (formData.taxRate / 100);
  const total = afterDiscount + taxAmount;

  const fmt = useMemo(
    () => new Intl.NumberFormat(undefined, { style: 'currency', currency: formData.currency || 'USD' }),
    [formData.currency]
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (isLoading) return;

    const data: QuoteCreate = {
      title: formData.title,
      description: formData.description || null,
      currency: formData.currency,
      valid_until: formData.validUntil || null,
      discount_type: formData.discountType || null,
      discount_value: formData.discountValue,
      tax_rate: formData.taxRate,
      terms_and_conditions: formData.termsAndConditions || null,
      notes: formData.notes || null,
      status: 'draft',
      contact_id: formData.contactId,
      company_id: formData.companyId,
      opportunity_id: formData.opportunityId,
      payment_type: billing.payment_type,
      recurring_interval: billing.payment_type === 'subscription' ? billing.recurring_interval : null,
      recurring_interval_count: billing.payment_type === 'subscription' ? billing.recurring_interval_count : null,
      line_items: lineItems.filter((item) => item.description.trim() !== ''),
    };

    onSubmit(data);
  };

  return (
    <form ref={formRef} onSubmit={handleSubmit} className="space-y-6">
      {/* Basic Info */}
      <div className="space-y-4">
        <div>
          <label htmlFor="quote-title" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Title *
          </label>
          <input
            type="text"
            id="quote-title"
            name="title"
            required
            autoFocus
            value={formData.title}
            onChange={(e) => updateField('title', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Quote title..."
          />
        </div>

        <div>
          <label htmlFor="quote-description" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Description
          </label>
          <textarea
            id="quote-description"
            name="description"
            rows={2}
            value={formData.description}
            onChange={(e) => updateField('description', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Optional description..."
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label htmlFor="quote-currency" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Currency
            </label>
            <select
              id="quote-currency"
              name="currency"
              value={formData.currency}
              onChange={(e) => updateField('currency', e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            >
              <option value="USD">USD</option>
              <option value="EUR">EUR</option>
              <option value="GBP">GBP</option>
              <option value="CAD">CAD</option>
              <option value="AUD">AUD</option>
            </select>
          </div>
          <div>
            <label htmlFor="quote-valid-until" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Valid Until
            </label>
            <input
              type="date"
              id="quote-valid-until"
              name="valid_until"
              value={formData.validUntil}
              onChange={(e) => updateField('validUntil', e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            />
          </div>
        </div>
      </div>

      {/* Billing type + cadence. Amount is hidden here because quote
          line items drive the total; only the cadence lands on the quote. */}
      <div className="rounded-lg border border-gray-200 dark:border-gray-700 p-4 bg-gray-50 dark:bg-gray-800/40">
        <BillingTermsField
          value={billing}
          onChange={handleBillingChange}
          amountMode="hidden"
        />
      </div>

      {/* Related Records */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Related Records</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <SearchableSelect
            label="Opportunity"
            id="quote-opportunity"
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
            label="Contact"
            id="quote-contact"
            name="contact_id"
            value={formData.contactId}
            onChange={(val) => updateField('contactId', val)}
            options={contactOptions}
            placeholder="Search contacts..."
          />
          <SearchableSelect
            label="Company"
            id="quote-company"
            name="company_id"
            value={formData.companyId}
            onChange={(val) => updateField('companyId', val)}
            options={companyOptions}
            placeholder="Search companies..."
          />
        </div>
      </div>

      {/* Line Items */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Line Items</h3>
          <div className="flex items-center gap-2">
            {activeBundles.length > 0 && (
              <div className="relative" ref={bundleMenuRef}>
                <button
                  type="button"
                  onClick={() => setShowBundleMenu(!showBundleMenu)}
                  className="inline-flex items-center text-sm text-primary-600 hover:text-primary-900 dark:hover:text-primary-300"
                >
                  <CubeIcon className="h-4 w-4 mr-1" aria-hidden="true" />
                  Add Bundle
                </button>
                {showBundleMenu && (
                  <div className="absolute right-0 z-10 mt-1 w-56 origin-top-right rounded-md bg-white dark:bg-gray-800 shadow-lg ring-1 ring-black/5 dark:ring-gray-700">
                    <div className="py-1">
                      {activeBundles.map((bundle: ProductBundle) => (
                        <button
                          key={bundle.id}
                          type="button"
                          onClick={() => addBundleItems(bundle)}
                          className="block w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                        >
                          <span className="font-medium">{bundle.name}</span>
                          <span className="ml-1 text-gray-400 dark:text-gray-500">
                            ({bundle.items.length} item{bundle.items.length !== 1 ? 's' : ''})
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
            <button
              type="button"
              onClick={addLineItem}
              className="inline-flex items-center text-sm text-primary-600 hover:text-primary-900 dark:hover:text-primary-300"
            >
              <PlusIcon className="h-4 w-4 mr-1" aria-hidden="true" />
              Add Item
            </button>
          </div>
        </div>

        <div className="space-y-3">
          {lineItems.map((item, index) => (
            <div key={index} className="flex flex-col sm:flex-row gap-2 p-3 bg-gray-50 dark:bg-gray-900 rounded-lg">
              <div className="flex-1">
                <label htmlFor={`item-desc-${index}`} className="sr-only">Description</label>
                <input
                  type="text"
                  id={`item-desc-${index}`}
                  value={item.description}
                  onChange={(e) => updateLineItem(index, 'description', e.target.value)}
                  placeholder="Description..."
                  className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
                />
              </div>
              <div className="flex gap-2">
                <div className="w-20">
                  <label htmlFor={`item-qty-${index}`} className="sr-only">Quantity</label>
                  <input
                    type="text"
                    inputMode="decimal"
                    id={`item-qty-${index}`}
                    value={item.quantity}
                    onChange={(e) => {
                      const cleaned = clampNumberInput(e.target.value, { min: 0, allowDecimal: true });
                      updateLineItem(index, 'quantity', parseFloat(cleaned) || 0);
                    }}
                    placeholder="Qty"
                    className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
                  />
                </div>
                <div className="w-28">
                  <label htmlFor={`item-price-${index}`} className="sr-only">Unit Price</label>
                  <input
                    type="text"
                    inputMode="decimal"
                    id={`item-price-${index}`}
                    value={item.unit_price}
                    onChange={(e) => {
                      const cleaned = clampNumberInput(e.target.value, { min: 0, allowDecimal: true });
                      updateLineItem(index, 'unit_price', parseFloat(cleaned) || 0);
                    }}
                    placeholder="Price"
                    className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
                  />
                </div>
                <div className="w-24">
                  <label htmlFor={`item-discount-${index}`} className="sr-only">Discount</label>
                  <input
                    type="text"
                    inputMode="decimal"
                    id={`item-discount-${index}`}
                    value={item.discount}
                    onChange={(e) => {
                      const cleaned = clampNumberInput(e.target.value, { min: 0, max: 100, allowDecimal: true });
                      updateLineItem(index, 'discount', parseFloat(cleaned) || 0);
                    }}
                    placeholder="Disc."
                    className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
                  />
                </div>
                <div className="flex items-center w-20 text-sm font-medium text-gray-700 dark:text-gray-300" style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {fmt.format(calculateItemTotal(item))}
                </div>
                <button
                  type="button"
                  onClick={() => setPendingDeleteIndex(index)}
                  className="p-1 text-gray-400 hover:text-red-600 dark:hover:text-red-400"
                  aria-label={`Remove line item ${index + 1}`}
                  disabled={lineItems.length <= 1}
                >
                  <TrashIcon className="h-5 w-5" aria-hidden="true" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Discount & Tax */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div>
          <label htmlFor="quote-discount-type" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Discount Type
          </label>
          <select
            id="quote-discount-type"
            value={formData.discountType}
            onChange={(e) => updateField('discountType', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
          >
            <option value="">None</option>
            <option value="percent">Percentage</option>
            <option value="fixed">Fixed Amount</option>
          </select>
        </div>
        <div>
          <label htmlFor="quote-discount-value" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Discount Value
          </label>
          <input
            type="text"
            inputMode="decimal"
            id="quote-discount-value"
            value={formData.discountValue}
            onChange={(e) => {
              const opts = formData.discountType === 'percent'
                ? { min: 0, max: 100, allowDecimal: true }
                : { min: 0, allowDecimal: true };
              const cleaned = clampNumberInput(e.target.value, opts);
              updateField('discountValue', parseFloat(cleaned) || 0);
            }}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
          />
        </div>
        <div>
          <label htmlFor="quote-tax-rate" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Tax Rate (%)
          </label>
          <input
            type="number"
            id="quote-tax-rate"
            value={formData.taxRate}
            onChange={(e) => updateField('taxRate', parseFloat(e.target.value) || 0)}
            min="0"
            step="any"
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
          />
        </div>
      </div>

      {/* Totals Preview */}
      <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-4 space-y-1 text-sm" style={{ fontVariantNumeric: 'tabular-nums' }}>
        <div className="flex justify-between text-gray-600 dark:text-gray-400">
          <span>Subtotal</span>
          <span>{fmt.format(subtotal)}</span>
        </div>
        {discountAmount > 0 && (
          <div className="flex justify-between text-gray-600 dark:text-gray-400">
            <span>Discount</span>
            <span>-{fmt.format(discountAmount)}</span>
          </div>
        )}
        {taxAmount > 0 && (
          <div className="flex justify-between text-gray-600 dark:text-gray-400">
            <span>Tax ({formData.taxRate}%)</span>
            <span>{fmt.format(taxAmount)}</span>
          </div>
        )}
        <div className="flex justify-between font-medium text-gray-900 dark:text-gray-100 pt-1 border-t border-gray-200 dark:border-gray-700">
          <span>Total</span>
          <span>{fmt.format(total)}</span>
        </div>
      </div>

      {/* Terms & Notes */}
      <div className="space-y-4">
        <div>
          <label htmlFor="quote-terms" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Terms and Conditions
          </label>
          <textarea
            id="quote-terms"
            rows={3}
            value={formData.termsAndConditions}
            onChange={(e) => updateField('termsAndConditions', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Payment terms, delivery conditions..."
          />
        </div>
        <div>
          <label htmlFor="quote-notes" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Notes
          </label>
          <textarea
            id="quote-notes"
            rows={2}
            value={formData.notes}
            onChange={(e) => updateField('notes', e.target.value)}
            className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            placeholder="Internal notes..."
          />
        </div>
      </div>

      {/* Actions */}
      <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-700">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" disabled={!formData.title.trim()} isLoading={isLoading}>
          Create Quote
        </Button>
      </div>

      <ConfirmDialog
        isOpen={pendingDeleteIndex !== null}
        onClose={() => setPendingDeleteIndex(null)}
        onConfirm={() => {
          if (pendingDeleteIndex !== null) {
            removeLineItem(pendingDeleteIndex);
          }
          setPendingDeleteIndex(null);
        }}
        title="Remove line item?"
        message={
          pendingDeleteIndex !== null && lineItems[pendingDeleteIndex]?.description.trim()
            ? `Remove "${lineItems[pendingDeleteIndex].description}"? This action cannot be undone.`
            : 'This action cannot be undone.'
        }
        confirmLabel="Remove"
        variant="danger"
      />
    </form>
  );
}
