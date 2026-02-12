import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { TrashIcon, PlusIcon } from '@heroicons/react/24/outline';
import { Button } from '../../components/ui';
import { useContacts } from '../../hooks/useContacts';
import { useCompanies } from '../../hooks/useCompanies';
import { useOpportunities, useOpportunity } from '../../hooks/useOpportunities';
import type { QuoteCreate, QuoteLineItemCreate } from '../../types';

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

export function QuoteForm({ onSubmit, onCancel, isLoading, initialData }: QuoteFormProps) {
  const [searchParams] = useSearchParams();
  const urlOpportunityId = searchParams.get('opportunity_id');

  const [title, setTitle] = useState(initialData?.title ?? '');
  const [description, setDescription] = useState(initialData?.description ?? '');
  const [contactId, setContactId] = useState<number | null>(initialData?.contact_id ?? null);
  const [companyId, setCompanyId] = useState<number | null>(initialData?.company_id ?? null);
  const [opportunityId, setOpportunityId] = useState<number | null>(
    initialData?.opportunity_id ?? (urlOpportunityId ? parseInt(urlOpportunityId, 10) : null)
  );

  // Fetch entity lists for dropdowns
  const { data: contactsData } = useContacts({ page_size: 100 });
  const { data: companiesData } = useCompanies({ page_size: 100 });
  const { data: opportunitiesData } = useOpportunities({ page_size: 100 });
  const { data: urlOpportunity } = useOpportunity(
    urlOpportunityId ? parseInt(urlOpportunityId, 10) : undefined
  );

  const contacts = contactsData?.items ?? [];
  const companies = companiesData?.items ?? [];
  const opportunities = opportunitiesData?.items ?? [];

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

  const [currency, setCurrency] = useState(initialData?.currency ?? 'USD');
  const [validUntil, setValidUntil] = useState(initialData?.valid_until ?? '');
  const [discountType, setDiscountType] = useState(initialData?.discount_type ?? '');
  const [discountValue, setDiscountValue] = useState(initialData?.discount_value ?? 0);
  const [taxRate, setTaxRate] = useState(initialData?.tax_rate ?? 0);
  const [termsAndConditions, setTermsAndConditions] = useState(initialData?.terms_and_conditions ?? '');
  const [notes, setNotes] = useState(initialData?.notes ?? '');
  const [paymentType, setPaymentType] = useState(initialData?.payment_type ?? 'one_time');
  const [recurringInterval, setRecurringInterval] = useState(initialData?.recurring_interval ?? '');
  const [lineItems, setLineItems] = useState<QuoteLineItemCreate[]>(
    initialData?.line_items ?? [{ ...EMPTY_LINE_ITEM }]
  );

  const addLineItem = () => {
    setLineItems((curr) => [...curr, { ...EMPTY_LINE_ITEM, sort_order: curr.length }]);
  };

  const removeLineItem = (index: number) => {
    setLineItems((curr) => curr.filter((_, i) => i !== index));
  };

  const updateLineItem = (index: number, field: keyof QuoteLineItemCreate, value: string | number) => {
    setLineItems((curr) =>
      curr.map((item, i) => (i === index ? { ...item, [field]: value } : item))
    );
  };

  const calculateItemTotal = (item: QuoteLineItemCreate): number => {
    return ((item.quantity ?? 1) * (item.unit_price ?? 0)) - (item.discount ?? 0);
  };

  const subtotal = lineItems.reduce((sum, item) => sum + calculateItemTotal(item), 0);
  const discountAmount = discountType === 'percent'
    ? subtotal * (discountValue / 100)
    : discountType === 'fixed'
      ? discountValue
      : 0;
  const afterDiscount = subtotal - discountAmount;
  const taxAmount = afterDiscount * (taxRate / 100);
  const total = afterDiscount + taxAmount;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const data: QuoteCreate = {
      title,
      description: description || null,
      currency,
      valid_until: validUntil || null,
      discount_type: discountType || null,
      discount_value: discountValue,
      tax_rate: taxRate,
      terms_and_conditions: termsAndConditions || null,
      notes: notes || null,
      status: 'draft',
      contact_id: contactId,
      company_id: companyId,
      opportunity_id: opportunityId,
      payment_type: paymentType,
      recurring_interval: paymentType === 'subscription' ? recurringInterval : null,
      line_items: lineItems.filter((item) => item.description.trim() !== ''),
    };

    onSubmit(data);
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Basic Info */}
      <div className="space-y-4">
        <div>
          <label htmlFor="quote-title" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
            Title *
          </label>
          <input
            type="text"
            id="quote-title"
            required
            value={title}
            onChange={(e) => setTitle(e.target.value)}
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
            rows={2}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
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
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
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
              value={validUntil}
              onChange={(e) => setValidUntil(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            />
          </div>
        </div>
      </div>

      {/* Payment Type */}
      <div className="space-y-4">
        <fieldset>
          <legend className="block text-sm font-medium text-gray-700 dark:text-gray-300">Payment Type</legend>
          <div className="mt-2 flex gap-4">
            <label className="inline-flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="payment_type"
                value="one_time"
                checked={paymentType === 'one_time'}
                onChange={() => {
                  setPaymentType('one_time');
                  setRecurringInterval('');
                }}
                className="text-primary-600 focus-visible:ring-primary-500"
              />
              <span className="text-sm text-gray-700 dark:text-gray-300">One-Time Payment</span>
            </label>
            <label className="inline-flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="payment_type"
                value="subscription"
                checked={paymentType === 'subscription'}
                onChange={() => {
                  setPaymentType('subscription');
                  if (!recurringInterval) setRecurringInterval('monthly');
                }}
                className="text-primary-600 focus-visible:ring-primary-500"
              />
              <span className="text-sm text-gray-700 dark:text-gray-300">Subscription</span>
            </label>
          </div>
        </fieldset>

        {paymentType === 'subscription' && (
          <div className="sm:w-1/2">
            <label htmlFor="quote-recurring-interval" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Billing Interval
            </label>
            <select
              id="quote-recurring-interval"
              value={recurringInterval}
              onChange={(e) => setRecurringInterval(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            >
              <option value="monthly">Monthly</option>
              <option value="quarterly">Quarterly</option>
              <option value="yearly">Yearly</option>
            </select>
          </div>
        )}
      </div>

      {/* Related Records */}
      <div className="space-y-4">
        <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Related Records</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label htmlFor="quote-opportunity" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Opportunity
            </label>
            <select
              id="quote-opportunity"
              value={opportunityId ?? ''}
              onChange={(e) => {
                const val = e.target.value ? parseInt(e.target.value, 10) : null;
                setOpportunityId(val);
                if (val) {
                  const opp = opportunities.find((o) => o.id === val);
                  if (opp?.contact_id) setContactId(opp.contact_id);
                  if (opp?.company_id) setCompanyId(opp.company_id);
                }
              }}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            >
              <option value="">-- None --</option>
              {opportunities.map((opp) => (
                <option key={opp.id} value={opp.id}>{opp.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="quote-contact" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Contact
            </label>
            <select
              id="quote-contact"
              value={contactId ?? ''}
              onChange={(e) => setContactId(e.target.value ? parseInt(e.target.value, 10) : null)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            >
              <option value="">-- None --</option>
              {contacts.map((c) => (
                <option key={c.id} value={c.id}>{c.full_name}</option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="quote-company" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
              Company
            </label>
            <select
              id="quote-company"
              value={companyId ?? ''}
              onChange={(e) => setCompanyId(e.target.value ? parseInt(e.target.value, 10) : null)}
              className="mt-1 block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
            >
              <option value="">-- None --</option>
              {companies.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Line Items */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300">Line Items</h3>
          <button
            type="button"
            onClick={addLineItem}
            className="inline-flex items-center text-sm text-primary-600 hover:text-primary-900 dark:hover:text-primary-300"
          >
            <PlusIcon className="h-4 w-4 mr-1" aria-hidden="true" />
            Add Item
          </button>
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
                    type="number"
                    id={`item-qty-${index}`}
                    value={item.quantity}
                    onChange={(e) => updateLineItem(index, 'quantity', parseFloat(e.target.value) || 0)}
                    min="0"
                    step="any"
                    placeholder="Qty"
                    className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
                  />
                </div>
                <div className="w-28">
                  <label htmlFor={`item-price-${index}`} className="sr-only">Unit Price</label>
                  <input
                    type="number"
                    id={`item-price-${index}`}
                    value={item.unit_price}
                    onChange={(e) => updateLineItem(index, 'unit_price', parseFloat(e.target.value) || 0)}
                    min="0"
                    step="any"
                    placeholder="Price"
                    className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
                  />
                </div>
                <div className="w-24">
                  <label htmlFor={`item-discount-${index}`} className="sr-only">Discount</label>
                  <input
                    type="number"
                    id={`item-discount-${index}`}
                    value={item.discount}
                    onChange={(e) => updateLineItem(index, 'discount', parseFloat(e.target.value) || 0)}
                    min="0"
                    step="any"
                    placeholder="Disc."
                    className="block w-full rounded-md border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 dark:text-gray-100 shadow-sm focus-visible:border-primary-500 focus-visible:ring-primary-500 sm:text-sm"
                  />
                </div>
                <div className="flex items-center w-20 text-sm font-medium text-gray-700 dark:text-gray-300" style={{ fontVariantNumeric: 'tabular-nums' }}>
                  {calculateItemTotal(item).toFixed(2)}
                </div>
                <button
                  type="button"
                  onClick={() => removeLineItem(index)}
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
            value={discountType}
            onChange={(e) => setDiscountType(e.target.value)}
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
            type="number"
            id="quote-discount-value"
            value={discountValue}
            onChange={(e) => setDiscountValue(parseFloat(e.target.value) || 0)}
            min="0"
            step="any"
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
            value={taxRate}
            onChange={(e) => setTaxRate(parseFloat(e.target.value) || 0)}
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
          <span>{subtotal.toFixed(2)}</span>
        </div>
        {discountAmount > 0 && (
          <div className="flex justify-between text-gray-600 dark:text-gray-400">
            <span>Discount</span>
            <span>-{discountAmount.toFixed(2)}</span>
          </div>
        )}
        {taxAmount > 0 && (
          <div className="flex justify-between text-gray-600 dark:text-gray-400">
            <span>Tax ({taxRate}%)</span>
            <span>{taxAmount.toFixed(2)}</span>
          </div>
        )}
        <div className="flex justify-between font-medium text-gray-900 dark:text-gray-100 pt-1 border-t border-gray-200 dark:border-gray-700">
          <span>Total</span>
          <span>{total.toFixed(2)}</span>
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
            value={termsAndConditions}
            onChange={(e) => setTermsAndConditions(e.target.value)}
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
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
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
        <Button type="submit" disabled={isLoading || !title.trim()}>
          {isLoading ? 'Creating...' : 'Create Quote'}
        </Button>
      </div>
    </form>
  );
}
