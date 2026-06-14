import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ActivityCard } from './ActivityCard';
import type { Activity } from '../../../types';

function makeTaskActivity(overrides: Partial<Activity> = {}): Activity {
  return {
    id: 1,
    activity_type: 'task',
    subject: 'asdf',
    description: 'adfffffff',
    entity_type: 'contact',
    entity_id: 1,
    scheduled_at: '2026-05-22T17:10:00Z',
    due_date: '2026-05-27',
    priority: 'normal',
    is_completed: false,
    created_at: '2026-05-22T17:10:00Z',
    updated_at: '2026-05-22T17:10:00Z',
    ...overrides,
  } as Activity;
}

describe('ActivityCard due_date rendering', () => {
  it('renders due_date as a bare date with no phantom time, regardless of local timezone', () => {
    render(<ActivityCard activity={makeTaskActivity()} />);

    const due = screen.getByText(/Due:/);
    // The bare 2026-05-27 must always read as May 27 — never May 26 (UTC-west)
    // and never with a 7:00 PM clock component bled in from a UTC-midnight parse.
    expect(due.textContent).toContain('May 27, 2026');
    expect(due.textContent).not.toMatch(/\d{1,2}:\d{2}/);
    expect(due.textContent).not.toContain('May 26');
  });

  it('renders scheduled_at with a clock component (real datetime)', () => {
    const { container } = render(
      <ActivityCard
        activity={makeTaskActivity({
          // 17:10 UTC == 12:10 PM CDT == 1:10 PM EDT, etc.
          scheduled_at: '2026-05-22T17:10:00Z',
        })}
      />,
    );

    // scheduled_at is a true timestamp, so a HH:MM clock is expected.
    expect(container.textContent).toMatch(/\d{1,2}:\d{2}/);
  });
});
