import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusTimeline } from './StatusTimeline';
import type { TimelineStep } from './StatusTimeline';

const MIXED_STEPS: TimelineStep[] = [
  { key: 'draft', label: 'Draft', at: '2024-01-10T10:00:00Z', state: 'completed' },
  { key: 'sent', label: 'Sent', at: '2024-01-15T12:00:00Z', state: 'current' },
  { key: 'signed', label: 'Signed', at: null, state: 'upcoming' },
  { key: 'rejected', label: 'Rejected', at: null, state: 'skipped' },
];

describe('StatusTimeline', () => {
  it('renders 4 steps with mixed states', () => {
    render(<StatusTimeline steps={MIXED_STEPS} />);
    expect(screen.getByText('Draft')).toBeTruthy();
    expect(screen.getByText('Sent')).toBeTruthy();
    expect(screen.getByText('Signed')).toBeTruthy();
    expect(screen.getByText('Rejected')).toBeTruthy();
  });

  it('marks the current step with aria-current="step"', () => {
    render(<StatusTimeline steps={MIXED_STEPS} />);
    const items = screen.getAllByRole('listitem');
    const currentItem = items.find((li: HTMLElement) => li.getAttribute('aria-current') === 'step');
    expect(currentItem).toBeTruthy();
    expect(currentItem?.textContent).toContain('Sent');
  });

  it('renders date when at is set, no date when null', () => {
    const { container } = render(<StatusTimeline steps={MIXED_STEPS} />);

    // Two steps have at set (draft + sent), so two <time> elements
    const times = container.querySelectorAll('time');
    expect(times.length).toBe(2);

    // Upcoming step has no <time>
    const signedEl = screen.getByText('Signed');
    const signedItem = signedEl.closest('li');
    expect(signedItem?.querySelector('time')).toBeNull();

    // Skipped step has no <time>
    const rejectedEl = screen.getByText('Rejected');
    const rejectedItem = rejectedEl.closest('li');
    expect(rejectedItem?.querySelector('time')).toBeNull();
  });

  it('applies flex-row class for horizontal variant', () => {
    const { container } = render(<StatusTimeline steps={MIXED_STEPS} variant="horizontal" />);
    const ol = container.querySelector('ol');
    expect(ol?.className).toContain('flex-row');
  });

  it('applies flex-col class for vertical variant', () => {
    const { container } = render(<StatusTimeline steps={MIXED_STEPS} variant="vertical" />);
    const ol = container.querySelector('ol');
    expect(ol?.className).toContain('flex-col');
  });

  it('applies auto variant classes with both flex-col and sm:flex-row', () => {
    const { container } = render(<StatusTimeline steps={MIXED_STEPS} variant="auto" />);
    const ol = container.querySelector('ol');
    expect(ol?.className).toContain('flex-col');
    expect(ol?.className).toContain('sm:flex-row');
  });

  it('uses motion-safe:animate-ping on current step pulse for reduced-motion support', () => {
    const { container } = render(<StatusTimeline steps={MIXED_STEPS} />);
    const pings = container.querySelectorAll('.motion-safe\\:animate-ping');
    expect(pings.length).toBe(1);
  });

  it('renders tooltip via title attribute when provided', () => {
    const steps: TimelineStep[] = [
      {
        key: 'draft',
        label: 'Draft',
        at: '2024-01-10T10:00:00Z',
        state: 'completed',
        tooltip: 'Document created by admin',
      },
    ];
    const { container } = render(<StatusTimeline steps={steps} />);
    const el = container.querySelector('[title="Document created by admin"]');
    expect(el).toBeTruthy();
  });

  it('renders as an ordered list with listitem roles', () => {
    render(<StatusTimeline steps={MIXED_STEPS} />);
    const list = screen.getByRole('list');
    expect(list.tagName.toLowerCase()).toBe('ol');
    const items = screen.getAllByRole('listitem');
    expect(items.length).toBe(4);
  });
});
