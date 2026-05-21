import type {
  PaymentType,
  ProposalPackage,
  ProposalPackagePublic,
  ProposalPackagePublicItem,
  RecurringInterval,
  SelectedPackageSnapshot,
} from '../../types';

export type DisplayableProposalPackage =
  | ProposalPackage
  | ProposalPackagePublic
  | SelectedPackageSnapshot;

export function moneyToNumber(value: string | number | null | undefined): number {
  if (value == null || value === '') return 0;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function isZeroMoney(value: string | number | null | undefined): boolean {
  return Math.abs(moneyToNumber(value)) < 0.005;
}

export function formatPackageCurrency(
  value: string | number | null | undefined,
  currency: string | null | undefined,
): string {
  const normalizedCurrency = (currency || 'USD').toUpperCase();
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: normalizedCurrency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(moneyToNumber(value));
}

export function formatPackageCadence(
  paymentType: PaymentType,
  interval?: RecurringInterval | null,
  intervalCount?: number | null,
): string {
  if (paymentType !== 'subscription') return 'One-time';
  const unit = interval ?? 'month';
  const count = intervalCount && intervalCount > 0 ? intervalCount : 1;
  if (count === 1) return `Every ${unit}`;
  return `Every ${count} ${unit}s`;
}

export function sortPackages<T extends { sort_order?: number; id?: number }>(
  packages: T[],
): T[] {
  return [...packages].sort(
    (a, b) =>
      (a.sort_order ?? 0) - (b.sort_order ?? 0) ||
      (a.id ?? 0) - (b.id ?? 0),
  );
}

export function getActivePackages(
  packages: ProposalPackage[] | undefined,
): ProposalPackage[] {
  return sortPackages((packages ?? []).filter((pkg) => pkg.is_active));
}

export function hasPackageRows(proposal: { packages?: ProposalPackage[] }): boolean {
  return Boolean(proposal.packages && proposal.packages.length > 0);
}

export function isPackageItemValid(item: ProposalPackagePublicItem): boolean {
  return (
    item.description.trim().length > 0 &&
    moneyToNumber(item.quantity) > 0 &&
    moneyToNumber(item.unit_price) >= 0 &&
    moneyToNumber(item.discount_amount) >= 0
  );
}
