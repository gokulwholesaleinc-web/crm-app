import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderWithProviders, screen, fireEvent } from '../../test-utils/renderWithProviders';
import { EmailThread } from './EmailThread';
import type { ThreadEmailItem, ThreadResponse } from '../../types/email';

const mockUseEmailThread = vi.fn();

vi.mock('../../hooks/useEmail', () => ({
  useEmailThread: (...args: unknown[]) => mockUseEmailThread(...args),
}));

function makeEmail(overrides: Partial<ThreadEmailItem>): ThreadEmailItem {
  return {
    id: 1,
    direction: 'outbound',
    from_email: 'me@example.com',
    to_email: 'them@example.com',
    cc: null,
    subject: 'test',
    body: 'body',
    body_html: null,
    timestamp: '2026-04-15T21:40:00Z',
    status: 'sent',
    open_count: 0,
    attachments: null,
    thread_id: 'thread-abc',
    ...overrides,
  };
}

function threadResponse(items: ThreadEmailItem[]): ThreadResponse {
  return { items, total: items.length, page: 1, page_size: 50, pages: 1 };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('EmailThread', () => {
  it('renders a thread-level Reply button even when the thread is outbound-only', () => {
    mockUseEmailThread.mockReturnValue({
      data: threadResponse([
        makeEmail({ id: 1, direction: 'outbound', timestamp: '2026-04-17T10:55:00Z' }),
        makeEmail({ id: 2, direction: 'outbound', timestamp: '2026-04-15T21:40:00Z' }),
      ]),
      isLoading: false,
    });

    const onReply = vi.fn();
    renderWithProviders(
      <EmailThread entityType="contacts" entityId={1883} onReply={onReply} />
    );

    expect(screen.getByRole('button', { name: /Reply to thread: test/i })).toBeInTheDocument();
  });

  it('clicking thread-level Reply fires onReply with the newest message', () => {
    const newest = makeEmail({ id: 2, direction: 'outbound', timestamp: '2026-04-17T10:55:00Z' });
    const older = makeEmail({ id: 1, direction: 'outbound', timestamp: '2026-04-15T21:40:00Z' });

    mockUseEmailThread.mockReturnValue({
      data: threadResponse([newest, older]),
      isLoading: false,
    });

    const onReply = vi.fn();
    renderWithProviders(
      <EmailThread entityType="contacts" entityId={1883} onReply={onReply} />
    );

    fireEvent.click(screen.getByRole('button', { name: /Reply to thread/i }));

    expect(onReply).toHaveBeenCalledTimes(1);
    expect(onReply).toHaveBeenCalledWith(newest);
  });

  it('thread-level Reply picks the newest message across mixed directions', () => {
    const inboundFirst = makeEmail({
      id: 1,
      direction: 'inbound',
      from_email: 'them@example.com',
      to_email: 'me@example.com',
      timestamp: '2026-04-15T21:40:00Z',
    });
    const outboundReply = makeEmail({
      id: 2,
      direction: 'outbound',
      timestamp: '2026-04-17T10:55:00Z',
    });

    mockUseEmailThread.mockReturnValue({
      data: threadResponse([outboundReply, inboundFirst]),
      isLoading: false,
    });

    const onReply = vi.fn();
    renderWithProviders(
      <EmailThread entityType="contacts" entityId={1883} onReply={onReply} />
    );

    fireEvent.click(screen.getByRole('button', { name: /Reply to thread/i }));

    expect(onReply).toHaveBeenCalledWith(outboundReply);
  });

  it('does not render Reply button when onReply is not provided', () => {
    mockUseEmailThread.mockReturnValue({
      data: threadResponse([makeEmail({})]),
      isLoading: false,
    });

    renderWithProviders(<EmailThread entityType="contacts" entityId={1883} />);

    expect(screen.queryByRole('button', { name: /Reply to thread/i })).not.toBeInTheDocument();
  });

  it('clicking Reply does not toggle the thread expansion', () => {
    mockUseEmailThread.mockReturnValue({
      data: threadResponse([makeEmail({ id: 1 })]),
      isLoading: false,
    });

    const onReply = vi.fn();
    renderWithProviders(
      <EmailThread entityType="contacts" entityId={1883} onReply={onReply} />
    );

    const header = screen.getByRole('button', { name: /test/i, expanded: true });
    fireEvent.click(screen.getByRole('button', { name: /Reply to thread/i }));

    // Header remains expanded because Reply click does not propagate to the toggle.
    expect(header).toHaveAttribute('aria-expanded', 'true');
  });

  it('renders inline data: image URIs through DOMPurify (regression for Giancarlo)', () => {
    // 1x1 transparent PNG as a real, browser-renderable data URI. The
    // backend Gmail sync substitutes cid: refs with these before we
    // ever see the body. DOMPurify's default data-URI allowlist
    // already includes <img>, so the URI passes through to the
    // rendered DOM without any extra config.
    const tinyPng =
      'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';
    const html =
      '<p>Logo: <img src="' +
      tinyPng +
      '" alt="brand-logo" data-testid="inline-img"></p>';
    mockUseEmailThread.mockReturnValue({
      data: threadResponse([makeEmail({ id: 1, body_html: html })]),
      isLoading: false,
    });

    renderWithProviders(<EmailThread entityType="contacts" entityId={1883} />);

    const img = screen.getByAltText('brand-logo') as HTMLImageElement;
    expect(img.getAttribute('src')).toBe(tinyPng);
  });

  it('trims gmail_quote + gmail_signature from inbound HTML by default and exposes a toggle', async () => {
    const html =
      '<p>Approved — please proceed.</p>' +
      '<div class="gmail_quote">' +
      '<div>On Mon, Apr 28 Daisy &lt;daisy@example.com&gt; wrote:</div>' +
      '<blockquote>can you confirm?</blockquote>' +
      '</div>' +
      '<div class="gmail_signature">' +
      '<table><tr><td>Giancarlo · CEO · Link Creative</td></tr></table>' +
      '</div>';
    mockUseEmailThread.mockReturnValue({
      data: threadResponse([
        makeEmail({
          id: 1,
          direction: 'inbound',
          from_email: 'them@example.com',
          to_email: 'me@example.com',
          body_html: html,
        }),
      ]),
      isLoading: false,
    });

    renderWithProviders(<EmailThread entityType="contacts" entityId={1883} />);

    const body = document.querySelector('.email-html-content');
    expect(body).not.toBeNull();
    expect(body!.textContent).toContain('Approved');
    expect(body!.textContent).not.toContain('can you confirm?');
    expect(body!.textContent).not.toContain('Giancarlo');

    // Toggle label names *both* cuts since the body had a quote AND a sig.
    const toggle = screen.getByRole('button', { name: /Show quoted history & signature/i });
    fireEvent.click(toggle);

    const expanded = document.querySelector('.email-html-content');
    expect(expanded!.textContent).toContain('can you confirm?');
    expect(expanded!.textContent).toContain('Giancarlo');
  });

  it('trims outbound HTML when explicit Gmail/Outlook markers are present (Gmail-synced sent mail)', () => {
    // Outbound is no longer skipped: users replying from their own Gmail
    // client produce EmailQueue rows via the history sync that carry the
    // same gmail_quote / blockquote[type="cite"] markers as inbound. The
    // trim utility cuts ONLY at those explicit markers — a CRM-composed
    // branded template (no marker) still passes through untouched, which
    // is guarded by the next test.
    const html =
      '<p>New reply text</p>' +
      '<blockquote type="cite">Previous message in the thread</blockquote>';
    mockUseEmailThread.mockReturnValue({
      data: threadResponse([makeEmail({ id: 1, direction: 'outbound', body_html: html })]),
      isLoading: false,
    });

    renderWithProviders(<EmailThread entityType="contacts" entityId={1883} />);

    const body = document.querySelector('.email-html-content');
    expect(body!.textContent).toContain('New reply text');
    expect(body!.textContent).not.toContain('Previous message in the thread');
    expect(screen.getByRole('button', { name: /Show quoted history/i })).toBeInTheDocument();
  });

  it('passes outbound HTML through unchanged when no quote/signature markers are present (branded templates)', () => {
    // CRM-composed branded emails (proposal send, quote send, contract
    // send) carry no Gmail markers, so the trim utility returns the
    // body verbatim. Tests that a future template can include a real
    // <blockquote> (e.g. testimonial) without surprise stripping —
    // detection requires the gmail_quote class or blockquote[type="cite"].
    const html =
      '<p>Thanks for your purchase!</p>' +
      '<blockquote>"Their service is amazing." — Jane</blockquote>';
    mockUseEmailThread.mockReturnValue({
      data: threadResponse([makeEmail({ id: 1, direction: 'outbound', body_html: html })]),
      isLoading: false,
    });

    renderWithProviders(<EmailThread entityType="contacts" entityId={1883} />);

    const body = document.querySelector('.email-html-content');
    expect(body!.textContent).toContain('Their service is amazing');
    expect(screen.queryByRole('button', { name: /Show quoted history/i })).not.toBeInTheDocument();
  });

  it('strips <svg> and <image> from inbound HTML (no profile escape)', () => {
    // Adversarial inbound: USE_PROFILES.html doesn't load the SVG
    // profile, so <svg> and <image> are stripped entirely — no
    // SVG-script-execution surface even though data: URIs are
    // permitted on real <img>. Regression guard so future config
    // tweaks don't accidentally widen the surface.
    const html =
      '<p>safe</p>' +
      '<svg><image href="data:image/svg+xml,<svg onload=alert(1)></svg>" data-testid="svg-image"></svg>';
    mockUseEmailThread.mockReturnValue({
      data: threadResponse([makeEmail({ id: 1, body_html: html })]),
      isLoading: false,
    });

    renderWithProviders(<EmailThread entityType="contacts" entityId={1883} />);

    // The page itself renders chrome SVGs (Reply icon, etc.), so the
    // assertion is scoped to the .email-html-content wrapper holding
    // the sanitized inbound body.
    const bodyContainer = document.querySelector('.email-html-content');
    expect(bodyContainer).not.toBeNull();
    expect(bodyContainer!.querySelector('svg')).toBeNull();
    expect(bodyContainer!.querySelector('image')).toBeNull();
    expect(screen.getByText('safe')).toBeInTheDocument();
  });
});
