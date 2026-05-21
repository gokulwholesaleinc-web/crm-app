export type PackageFormItem = {
  id?: number;
  description: string;
  quantity: string;
  unit_price: string;
  discount_amount: string;
  sort_order: number;
};

export type PackageFormState = {
  name: string;
  description: string;
  currency: string;
  payment_type: 'one_time' | 'subscription';
  recurring_interval: 'month' | 'year';
  recurring_interval_count: number;
  is_recommended: boolean;
  is_active: boolean;
  sort_order: number;
  items: PackageFormItem[];
};

function parsePackageNumber(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function getPackageFormValidationError(form: PackageFormState): string | null {
  if (!form.name.trim()) return 'Package name is required';
  const currency = form.currency.trim().toUpperCase();
  if (!/^[A-Z]{3}$/.test(currency)) return 'Currency must be a 3-letter ISO code';
  if (form.payment_type === 'subscription' && form.recurring_interval_count < 1) {
    return 'Subscription packages require recurring_interval_count >= 1';
  }
  if (form.items.length === 0) return 'Package must include at least one item';

  let subtotal = 0;
  let discount = 0;
  for (const item of form.items) {
    if (!item.description.trim()) return 'Package item description is required';
    const quantity = parsePackageNumber(item.quantity);
    const unitPrice = parsePackageNumber(item.unit_price);
    const itemDiscount = parsePackageNumber(item.discount_amount);
    if (quantity === null || unitPrice === null || itemDiscount === null) {
      return 'Package item amounts must be valid numbers';
    }
    if (quantity <= 0) return 'Package item quantity must be greater than 0';
    if (unitPrice < 0 || itemDiscount < 0) {
      return 'Package item money amounts must be non-negative';
    }
    const gross = quantity * unitPrice;
    if (itemDiscount > gross) return 'Package item discount cannot exceed line amount';
    subtotal += gross;
    discount += itemDiscount;
  }

  if (form.is_active && subtotal - discount <= 0) {
    return 'Active package total must be greater than 0';
  }
  return null;
}
