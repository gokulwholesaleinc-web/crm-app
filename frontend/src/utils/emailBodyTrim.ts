/**
 * Trim the noisy parts off email bodies before rendering.
 *
 * Real-world inbound HTML stuffs three things into one blob:
 *   1. The actual new message the sender wrote.
 *   2. Their signature (logo + contact card + social icons).
 *   3. The quoted history of every prior reply in the thread.
 *
 * The thread view already groups messages chronologically, so #3 is pure
 * duplication. Signatures (#2) are usually 4–10 lines of layout-table
 * markup that renders poorly without inline `style` and adds zero
 * conversational value. We strip both, leaving the actual message.
 *
 * Detection is intentionally conservative — we only cut at *explicitly
 * marked* boundaries from the major mail clients (Gmail, Outlook, Apple
 * Mail). Unmarked signatures pass through untouched; better to over-show
 * than to truncate a real message body.
 *
 * Returns the trimmed body and a flag so callers can render a
 * "Show original" affordance.
 */

export interface TrimResult {
  body: string;
  trimmed: boolean;
}

/**
 * Selectors whose matching elements (and everything after them) are
 * dropped from the rendered HTML. Order doesn't matter — we cut at the
 * earliest match to avoid keeping the signature when only the quote was
 * marked.
 */
const HTML_CUT_SELECTORS = [
  // Gmail web compose — quoted reply history
  'div.gmail_quote',
  'blockquote.gmail_quote',
  // Gmail signature — explicit marker, otherwise we'd never know
  'div.gmail_signature',
  '[data-smartmail="gmail_signature"]',
  // Apple Mail / generic — quoted reply
  'blockquote[type="cite"]',
  // Outlook web — divider above quoted history
  'div#divRplyFwdMsg',
  'div#x_divRplyFwdMsg',
  // Outlook desktop — "From: ... Sent: ..." header marker
  'div.OutlookMessageHeader',
];

/** Remove every later sibling of `node` from its parent. */
function removeFollowing(node: Node): void {
  let next: Node | null = node.nextSibling;
  while (next) {
    const after = next.nextSibling;
    next.parentNode?.removeChild(next);
    next = after;
  }
}

/**
 * Trim an HTML email body. Uses DOMParser so we operate on a real tree —
 * regex-stripping nested HTML reliably is not a thing.
 *
 * Note: `parseFromString` is famously lenient on malformed input; the
 * resulting `doc.body.innerHTML` may differ slightly from the source
 * (auto-closed tags, re-quoted attrs). DOMPurify normalizes downstream
 * so the difference is invisible to the user.
 */
export function trimQuotedHtml(html: string): TrimResult {
  if (!html) return { body: html, trimmed: false };

  // SSR / non-browser: no DOMParser. Skip — better than crashing.
  if (typeof DOMParser === 'undefined') return { body: html, trimmed: false };

  const doc = new DOMParser().parseFromString(html, 'text/html');
  let trimmed = false;

  // Gmail wraps replies in <blockquote>. Cut the *first* matching element
  // and every later sibling at every ancestor level, since the quoted
  // block is usually a single child of <body>.
  for (const selector of HTML_CUT_SELECTORS) {
    const node = doc.body.querySelector(selector);
    if (!node) continue;

    trimmed = true;

    // Cut the marker + everything that follows it within its parent,
    // then walk up and cut every later sibling at each ancestor up to
    // (but not including) <body>. Removing the ancestors themselves
    // would wipe legitimate new content that lives in the same wrapper
    // — Gmail emits `<div dir="ltr">new text<br><div class="gmail_quote">…</div></div>`.
    const markerParent: Node | null = node.parentNode;
    removeFollowing(node);
    node.parentNode?.removeChild(node);

    let cursor: Node | null = markerParent;
    while (cursor && cursor !== doc.body) {
      removeFollowing(cursor);
      cursor = cursor.parentNode;
    }
  }

  return {
    body: trimmed ? doc.body.innerHTML : html,
    trimmed,
  };
}

/**
 * Trim a plain-text email body. RFC 3676 says a "-- " line on its own
 * ends the message; Gmail/Outlook also plant an "On <date>, X wrote:"
 * line immediately above the quoted reply.
 */
export function trimQuotedText(text: string): TrimResult {
  if (!text) return { body: text, trimmed: false };

  const lines = text.split('\n');

  // Find the earliest cut point.
  let cutAt = -1;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? '';

    // RFC 3676 signature delimiter: "-- " (with trailing space) on its own.
    if (line === '-- ' || line === '--') {
      cutAt = i;
      break;
    }

    // Gmail/Outlook "On <date>, <name> wrote:" reply intro on its own
    // line. Anchored end-of-line on `wrote:` so mid-paragraph mentions
    // ("Last week I wrote my report.") don't trip the cut.
    if (/^\s*On\s+.+\s+wrote:\s*$/.test(line)) {
      cutAt = i;
      break;
    }

    // Outlook desktop "From: ... Sent: ..." block.
    const nextLine = lines[i + 1] ?? '';
    if (/^From:\s/.test(line) && /^Sent:\s|^Date:\s/.test(nextLine)) {
      cutAt = i;
      break;
    }
  }

  if (cutAt === -1) return { body: text, trimmed: false };

  // Strip trailing whitespace lines from the kept portion.
  let end = cutAt;
  while (end > 0 && (lines[end - 1] ?? '').trim() === '') end--;

  return {
    body: lines.slice(0, end).join('\n'),
    trimmed: true,
  };
}
