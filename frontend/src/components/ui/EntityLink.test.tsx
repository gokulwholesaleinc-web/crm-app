import { describe, it, expect } from 'vitest';
import { renderWithProviders, screen, fireEvent } from '../../test-utils/renderWithProviders';
import { EntityLink } from './EntityLink';
import {
  normalizeEntityType,
  LEGACY_CONTRACT_TYPE,
  LEGACY_OPPORTUNITY_TYPE,
  LEGACY_QUOTE_TYPE,
} from './EntityLink.utils';

describe('EntityLink', () => {
  it('renders a link to the matching detail route', () => {
    renderWithProviders(<EntityLink type="contact" id={42}>Jane Doe</EntityLink>);
    const link = screen.getByRole('link', { name: 'Jane Doe' });
    expect(link).toHaveAttribute('href', '/contacts/42');
  });

  it.each([
    ['company', 7, '/companies/7'],
    ['lead', 3, '/leads/3'],
    ['proposal', 5, '/proposals/5'],
    ['payment', 9, '/payments/9'],
    ['campaign', 4, '/campaigns/4'],
    ['activity', 1, '/activities/1'],
  ] as const)('routes %s/%s to %s', (type, id, expected) => {
    renderWithProviders(<EntityLink type={type} id={id}>Name</EntityLink>);
    expect(screen.getByRole('link', { name: 'Name' })).toHaveAttribute('href', expected);
  });

  it('renders plain text (no link) when id is missing', () => {
    renderWithProviders(<EntityLink type="contact" id={null}>Unknown</EntityLink>);
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText('Unknown')).toBeInTheDocument();
  });

  it('stops click propagation by default so row handlers do not fire', () => {
    let bubbled = false;
    renderWithProviders(
      <div onClick={() => { bubbled = true; }}>
        <EntityLink type="contact" id={1}>Click</EntityLink>
      </div>,
    );
    fireEvent.click(screen.getByRole('link', { name: 'Click' }));
    expect(bubbled).toBe(false);
  });

  it('lets clicks bubble when stopPropagation is false', () => {
    let bubbled = false;
    renderWithProviders(
      <div onClick={() => { bubbled = true; }}>
        <EntityLink type="contact" id={1} stopPropagation={false}>Click</EntityLink>
      </div>,
    );
    fireEvent.click(screen.getByRole('link', { name: 'Click' }));
    expect(bubbled).toBe(true);
  });

  // Regression guard: PR3 (#333) initially shipped LEGACY_CONTRACT_TYPE
  // without onClick={legacyClickHandler}, repeating the silent-click-
  // bubble bug PR2 trio (12d31f59) fixed for the other two kinds. The
  // LegacyEntityLabel helper in PR #334 centralized the wiring; this
  // parametrized test makes sure all three sentinels stay covered.
  it.each([
    ['opportunity', LEGACY_OPPORTUNITY_TYPE, /legacy opportunity/i],
    ['quote', LEGACY_QUOTE_TYPE, /legacy quote/i],
    ['contract', LEGACY_CONTRACT_TYPE, /legacy contract/i],
  ])('stops click propagation on the legacy %s chip', (_label, sentinel, chipRe) => {
    let bubbled = false;
    renderWithProviders(
      <div onClick={() => { bubbled = true; }}>
        <EntityLink type={sentinel} id={1}>Click</EntityLink>
      </div>,
    );
    fireEvent.click(screen.getByText(chipRe));
    expect(bubbled).toBe(false);
  });

  describe('legacy opportunity', () => {
    it('normalizes "opportunity" and "opportunities" to the legacy sentinel', () => {
      expect(normalizeEntityType('opportunity')).toBe(LEGACY_OPPORTUNITY_TYPE);
      expect(normalizeEntityType('opportunities')).toBe(LEGACY_OPPORTUNITY_TYPE);
      expect(normalizeEntityType('OPPORTUNITIES')).toBe(LEGACY_OPPORTUNITY_TYPE);
    });

    it('renders a non-clickable muted label for legacy opportunity rows', () => {
      renderWithProviders(
        <EntityLink type={LEGACY_OPPORTUNITY_TYPE} id={42}>
          Old Deal
        </EntityLink>,
      );
      expect(screen.queryByRole('link')).toBeNull();
      expect(screen.getByText('Old Deal')).toBeInTheDocument();
      expect(screen.getByText(/legacy opportunity/i)).toBeInTheDocument();
    });
  });

  describe('legacy quote', () => {
    it('normalizes "quote" and "quotes" to the legacy sentinel', () => {
      expect(normalizeEntityType('quote')).toBe(LEGACY_QUOTE_TYPE);
      expect(normalizeEntityType('quotes')).toBe(LEGACY_QUOTE_TYPE);
      expect(normalizeEntityType('QUOTES')).toBe(LEGACY_QUOTE_TYPE);
    });

    it('renders a non-clickable muted label for legacy quote rows', () => {
      renderWithProviders(
        <EntityLink type={LEGACY_QUOTE_TYPE} id={11}>
          Old Quote
        </EntityLink>,
      );
      expect(screen.queryByRole('link')).toBeNull();
      expect(screen.getByText('Old Quote')).toBeInTheDocument();
      expect(screen.getByText(/legacy quote/i)).toBeInTheDocument();
    });
  });

  describe('legacy contract', () => {
    it('normalizes "contract" and "contracts" to the legacy sentinel', () => {
      expect(normalizeEntityType('contract')).toBe(LEGACY_CONTRACT_TYPE);
      expect(normalizeEntityType('contracts')).toBe(LEGACY_CONTRACT_TYPE);
      expect(normalizeEntityType('CONTRACTS')).toBe(LEGACY_CONTRACT_TYPE);
    });

    it('renders a non-clickable muted label for legacy contract rows', () => {
      renderWithProviders(
        <EntityLink type={LEGACY_CONTRACT_TYPE} id={7}>
          Old Contract
        </EntityLink>,
      );
      expect(screen.queryByRole('link')).toBeNull();
      expect(screen.getByText('Old Contract')).toBeInTheDocument();
      expect(screen.getByText(/legacy contract/i)).toBeInTheDocument();
    });
  });
});
