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
 * Additional signature-block markers that trigger a cut even when the
 * message doesn't carry an explicit Gmail/Outlook wrapper and the
 * author skips the conventional sign-off.
 *
 * - ``[image: <alt>]`` is Gmail's plain-text alternative for an inline
 *   image — it only appears in signatures or branded marketing
 *   footers, never in body copy.
 * - The corporate confidentiality boilerplate ("This email and any
 *   files transmitted with it are confidential...", "This message
 *   contains confidential information...") is essentially universal
 *   in B2B mail and lives at the end of the body block under the
 *   signature.
 */
// ``[image: ...]`` alt-text is unbounded user text in Gmail's emitter
// — ``[image: image001.png]`` (Outlook-forwarded), ``[image: Link
// Creative Logo]`` (multi-word alts), ``[image: image_1.png]`` (forward
// chains) all appear in real mail. ``[^\]\n]+`` accepts anything but
// the closing bracket or a newline. The leading ``[image:`` literal is
// the load-bearing signal; the alt is just incidental.
const SIGNATURE_BLOCK_REGEX =
  /^(?:\[image:\s+[^\]\n]+\]|this\s+(?:e-?mail|message|email)\s+(?:and\s+any\s+files\s+transmitted\s+with\s+it\s+)?(?:are|is|contains)\s+confidential)/i;

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
  const children = Array.from(body.children);
  let seenContent = false;
  for (let i = 0; i < children.length; i++) {
    const child = children[i];
    const firstLine = firstNonEmptyLine(child.textContent ?? '');
    if (firstLine === '') continue;
    if (
      seenContent &&
      (SIGNOFF_REGEX.test(firstLine) || SIGNATURE_BLOCK_REGEX.test(firstLine))
    ) {
      // Walk back through preceding signature-shaped siblings so the
      // contact-card block above the marker (name / title / address)
      // is cut with the marker rather than left as 5+ lines of
      // vertical signature debris. The stop rule is a positive
      // ``looksLikeProse`` check, not a sentence-punctuation test —
      // address lines (``350 W Ontario St.``) end with periods, and
      // body content can be short (``See attached notes.``), so neither
      // signal alone is reliable.
      let start = i;
      while (start > 0) {
        const prev = children[start - 1];
        const prevText = (prev.textContent ?? '').trim();
        if (!prevText) {
          start--;
          continue;
        }
        if (looksLikeProse(prevText)) break;
        start--;
      }
      if (children.slice(0, start).some((c) => (c.textContent ?? '').trim() !== '')) {
        return children[start];
      }
      return child;
    }
    seenContent = true;
  }
  return null;
}

function firstNonEmptyLine(text: string): string {
  return text.split('\n').find((line) => line.trim() !== '')?.trim() ?? '';
}

/**
 * Explicit signature-card markers — patterns that effectively never
 * appear in legitimate body copy. The walk-back uses the negation
 * (``!isSignatureCard(text)``) as part of its prose detector so a
 * short ``350 W Ontario St.`` address line gets swallowed but a short
 * ``See attached notes.`` body acknowledgement doesn't.
 */
const _SIGNATURE_CARD_MARKERS = [
  /\b(?:phone|mobile|cell|tel|telephone|email|e-?mail|office|address|fax)\s*:/i,
  /\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}/, // phone number shapes
  /\b(?:st|ave|blvd|rd|dr|ln|ct|pl|hwy|pkwy|ste|suite|fl|floor)\.?\s*,?\s*(?:[A-Za-z]+|\d|$)/i,
  /\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b/, // US ZIP w/ state
  /\|\s*\*?[\w\s]+\*?$/, // "Title | Company" pattern
];

function isSignatureCard(text: string): boolean {
  return _SIGNATURE_CARD_MARKERS.some((re) => re.test(text));
}

/**
 * "Is this text real prose?" — used to gate the signature walk-back.
 *
 * Real prose stops the walk; signature-card material doesn't. The
 * test isn't punctuation alone because address lines (``350 W
 * Ontario St.``) end with periods, and body content can be short
 * (``See attached notes.``). The decision tree:
 *   1. Anything over 120 chars is prose by virtue of length.
 *   2. Anything matching a signature-card marker is NOT prose,
 *      regardless of punctuation.
 *   3. Otherwise, sentence-ending punctuation = prose.
 */
function looksLikeProse(text: string): boolean {
  if (text.length > 120) return true;
  if (isSignatureCard(text)) return false;
  return /[.!?]['")\]]?\s*$/.test(text);
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

    // Inline-image placeholder (Gmail plain-text alternative) or
    // corporate confidentiality footer — both are high-signal
    // signature-block markers. No blank-line precondition because
    // these patterns never appear in legitimate body copy (unlike
    // "Best,", which mid-paragraph users sometimes type). Same
    // earlier-content guard so a one-line legal-disclaimer email
    // isn't cut to empty.
    //
    // Once the marker hits, walk BACK through the contiguous
    // non-empty block so the contact-card lines that sit above it
    // (name / title / address / Phone: / Email:) are cut with the
    // marker — otherwise we'd trim only the trailing icons and leave
    // 5–10 lines of vertical contact-card noise behind.
    if (
      i > 0 &&
      SIGNATURE_BLOCK_REGEX.test(line) &&
      lines.slice(0, i).some((l) => l.trim() !== '')
    ) {
      let blockStart = i;
      while (blockStart > 0 && (lines[blockStart - 1] ?? '').trim() !== '') {
        blockStart--;
      }
      // Don't collapse the whole body — keep walking only if we're
      // sure earlier content remains.
      if (lines.slice(0, blockStart).some((l) => l.trim() !== '')) {
        cutAt = blockStart;
        cut = 'signature';
        break;
      }
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
