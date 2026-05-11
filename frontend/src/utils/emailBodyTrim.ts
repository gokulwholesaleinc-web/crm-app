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
 */

export interface TrimResult {
  body: string;
  trimmed: boolean;
  /** What the trimmer cut. Lets the caller render an accurate label. */
  cut: TrimCut;
}

export type TrimCut = 'none' | 'quote' | 'signature' | 'both';

/** Selectors that mark quoted reply history. */
const QUOTE_SELECTORS = [
  'div.gmail_quote',
  'blockquote.gmail_quote',
  'blockquote[type="cite"]',
  'div#divRplyFwdMsg',
  'div#x_divRplyFwdMsg',
  'div.OutlookMessageHeader',
];

/** Selectors that mark explicit signature wrappers. */
const SIGNATURE_SELECTORS = [
  'div.gmail_signature',
  '[data-smartmail="gmail_signature"]',
];

/**
 * Heuristic sign-off line patterns. When a single line (or the first
 * non-empty line of a top-level block element) matches this regex, we
 * treat it as the start of an unmarked signature and cut from there.
 *
 * Anchored to start/end-of-line so "Best laid plans..." or "thanks again
 * for sending" mid-sentence don't trip it. The trailing punctuation is
 * optional to catch "Thanks" / "Regards" without a comma.
 */
const SIGNOFF_REGEX =
  /^(?:best(?:\s+regards)?|kind\s+regards|warm\s+regards|regards|thanks(?:\s+again)?|thank\s+you|cheers|sincerely|talk\s+soon|sent\s+from\s+my\s+[a-z]+(?:\s+[a-z]+)?|get\s+outlook\s+for\s+[a-z]+)[,.!]?\s*$/i;

/**
 * Cut a node and everything that follows it (within `<body>`) using the
 * Range API. The Range correctly preserves any wrapping ancestors that
 * contain legitimate content before the marker — Gmail wraps both the
 * new message and the quote in a single `<div dir="ltr">`, and a naive
 * "remove cursor and walk up" would erase that wrapper. Returns true if
 * a cut happened.
 */
function cutFromHere(doc: Document, node: Element): boolean {
  const body = doc.body;
  if (!body || !body.lastChild) return false;
  const range = doc.createRange();
  range.setStartBefore(node);
  range.setEndAfter(body.lastChild);
  range.deleteContents();
  return true;
}

/**
 * After cutting, the previous-sibling chain often ends with a stray
 * Outlook `<hr>` divider, a trailing `<br>`, or pure-whitespace text
 * nodes. They visually orphan once the content beneath them is gone.
 * Walk back from `<body>`'s last child and drop them.
 */
function trimDanglingTrailers(body: HTMLElement): void {
  let last = body.lastChild;
  while (last) {
    const isWhitespaceText =
      last.nodeType === 3 /* TEXT_NODE */ && (last.textContent ?? '').trim() === '';
    const isOrphanRule =
      last.nodeType === 1 /* ELEMENT_NODE */ &&
      ['HR', 'BR'].includes((last as Element).tagName);
    if (!isWhitespaceText && !isOrphanRule) break;
    const prev = last.previousSibling;
    last.parentNode?.removeChild(last);
    last = prev;
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
  if (!html) return { body: html, trimmed: false, cut: 'none' };

  // SSR / non-browser: no DOMParser. Skip — better than crashing.
  if (typeof DOMParser === 'undefined') {
    return { body: html, trimmed: false, cut: 'none' };
  }

  const doc = new DOMParser().parseFromString(html, 'text/html');

  // Snapshot whether each marker type *existed in the original tree*,
  // before any cut. If the quote sits before the signature, the first
  // cut takes both with it — but the user will see both restored on
  // toggle, so the label should be 'both'.
  const hadQuote = QUOTE_SELECTORS.some((s) => doc.body.querySelector(s) !== null);
  const heuristicSigNode = findHeuristicSignatureNode(doc.body);
  const hadSig =
    SIGNATURE_SELECTORS.some((s) => doc.body.querySelector(s) !== null) ||
    heuristicSigNode !== null;

  let didCut = false;
  for (const selector of [...QUOTE_SELECTORS, ...SIGNATURE_SELECTORS]) {
    const node = doc.body.querySelector(selector);
    if (!node) continue;
    if (cutFromHere(doc, node)) didCut = true;
  }
  // Heuristic sign-off cut runs last so an explicit selector match takes
  // precedence — if a gmail_signature wrapper already swallowed the
  // sign-off line, the node is gone from the tree and findHeuristic…
  // won't fire a second cut.
  if (heuristicSigNode?.isConnected && cutFromHere(doc, heuristicSigNode)) {
    didCut = true;
  }

  if (didCut) trimDanglingTrailers(doc.body);

  const cut: TrimCut =
    hadQuote && hadSig ? 'both' : hadQuote ? 'quote' : hadSig ? 'signature' : 'none';

  return {
    body: didCut ? doc.body.innerHTML : html,
    trimmed: didCut,
    cut,
  };
}

/**
 * Find a top-level child of <body> whose visible text starts with a
 * known sign-off line ("Best,", "Thanks,", "Sent from my iPhone", …).
 * Returns null when no candidate is found.
 *
 * Requires at least one earlier top-level child with non-empty content,
 * so a one-paragraph reply like ``<div>Thanks,</div>`` (a common one-word
 * acknowledgement) doesn't get cut to an empty body. The "trimmed" toggle
 * would restore it, but the default render would otherwise show nothing
 * and the user would assume the email arrived empty.
 *
 * Only top-level children are scanned to avoid cutting inside a quoted
 * reply that itself ended with a sign-off ("…Best, Daisy" inside the
 * <blockquote>). The quote-selector cut runs first and removes the
 * <blockquote>, so by the time we get here the only remaining sign-off
 * candidates are in the new message.
 */
function findHeuristicSignatureNode(body: HTMLElement): Element | null {
  let seenContent = false;
  for (const child of Array.from(body.children)) {
    const firstLine = firstNonEmptyLine(child.textContent ?? '');
    if (firstLine === '') continue;
    if (seenContent && SIGNOFF_REGEX.test(firstLine)) return child;
    seenContent = true;
  }
  return null;
}

function firstNonEmptyLine(text: string): string {
  return text.split('\n').find((line) => line.trim() !== '')?.trim() ?? '';
}

/**
 * Trim a plain-text email body. RFC 3676 says a "-- " line on its own
 * ends the message (signature); Gmail/Outlook also plant an
 * "On <date>, X wrote:" line above the quoted reply.
 */
export function trimQuotedText(text: string): TrimResult {
  if (!text) return { body: text, trimmed: false, cut: 'none' };

  const lines = text.split('\n');
  let cutAt = -1;
  let cut: TrimCut = 'none';

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? '';

    // RFC 3676 signature delimiter: "-- " (with trailing space) on its own.
    if (line === '-- ' || line === '--') {
      cutAt = i;
      cut = 'signature';
      break;
    }

    // Heuristic sign-off: "Best,", "Thanks,", "Sent from my iPhone",
    // etc. on a line by itself. Requires (a) an earlier non-empty
    // content line — so a one-word reply "Thanks!" doesn't get cut to
    // an empty body — AND (b) the immediately preceding line to be
    // blank, so "Best regards always" mid-paragraph doesn't trip.
    if (
      i > 0 &&
      SIGNOFF_REGEX.test(line) &&
      (lines[i - 1] ?? '').trim() === '' &&
      lines.slice(0, i).some((l) => l.trim() !== '')
    ) {
      cutAt = i;
      cut = 'signature';
      break;
    }

    // Gmail/Outlook "On <date>, <name> wrote:" reply intro on its own
    // line. Anchored end-of-line on `wrote:` so mid-paragraph mentions
    // ("Last week I wrote my report.") don't trip the cut.
    if (/^\s*On\s+.+\s+wrote:\s*$/.test(line)) {
      cutAt = i;
      cut = 'quote';
      break;
    }

    // Outlook desktop "From: ... Sent: ..." block.
    const nextLine = lines[i + 1] ?? '';
    if (/^From:\s/.test(line) && /^Sent:\s|^Date:\s/.test(nextLine)) {
      cutAt = i;
      cut = 'quote';
      break;
    }
  }

  if (cutAt === -1) return { body: text, trimmed: false, cut: 'none' };

  // Strip trailing whitespace lines from the kept portion.
  let end = cutAt;
  while (end > 0 && (lines[end - 1] ?? '').trim() === '') end--;

  return {
    body: lines.slice(0, end).join('\n'),
    trimmed: true,
    cut,
  };
}

/** Localized button label that names what was actually trimmed. */
export function trimToggleLabel(cut: TrimCut, expanded: boolean): string {
  if (cut === 'none') return '';
  const noun =
    cut === 'both'
      ? 'quoted history & signature'
      : cut === 'quote'
        ? 'quoted history'
        : 'signature';
  return expanded ? `Hide ${noun}` : `Show ${noun}`;
}
