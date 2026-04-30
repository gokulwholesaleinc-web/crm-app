import { describe, it, expect } from 'vitest';
import { renderWithProviders, screen, fireEvent } from '../../test-utils/renderWithProviders';
import { EntityLink } from './EntityLink';

describe('EntityLink', () => {
  it('renders a link to the matching detail route', () => {
    renderWithProviders(<EntityLink type="contact" id={42}>Jane Doe</EntityLink>);
    const link = screen.getByRole('link', { name: 'Jane Doe' });
    expect(link).toHaveAttribute('href', '/contacts/42');
  });

  it.each([
    ['company', 7, '/companies/7'],
    ['lead', 3, '/leads/3'],
    ['opportunity', 11, '/opportunities/11'],
    ['quote', 'abc', '/quotes/abc'],
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
});
